"""Full, tenant-scoped stock snapshots; never merge a current snapshot with history."""
from datetime import date

STOCK_TABLES = {
    'normalized_stocks', 'snapshots_stocks_variants_daily',
    'snapshots_stocks_daily', 'metrics_stocks_variants_daily', 'metrics_stocks_daily',
}


def load_raw_snapshot(db, user_id, shop_id, marketplace='wb', snapshot_date=None):
    def query():
        return (db.table('raw_wb_stocks').select('*').eq('user_id', user_id)
                .eq('shop_id', shop_id).eq('marketplace', marketplace))
    if snapshot_date is None:
        latest = query().order('snapshot_date', desc=True).limit(1).execute().data or []
        if not latest or not latest[0].get('snapshot_date'):
            raise ValueError('No complete dated stock source')
        snapshot_date = str(latest[0]['snapshot_date'])[:10]
    snapshot_date = date.fromisoformat(str(snapshot_date)[:10]).isoformat()
    rows = []
    while True:
        batch = (query().eq('snapshot_date', snapshot_date).order('id')
                 .range(len(rows), len(rows) + 999).execute().data or [])
        rows.extend(batch)
        if len(batch) < 1000:
            break
    if not rows:
        raise ValueError('Missing stock source for requested snapshot date')
    return snapshot_date, rows


def replace_stock_rows(db, table, rows, *, user_id, shop_id, marketplace='wb', snapshot_date=None):
    if table not in STOCK_TABLES or not user_id or not shop_id or not marketplace:
        raise ValueError('Invalid stock replacement scope')
    if table == 'normalized_stocks':
        if snapshot_date is not None:
            raise ValueError('Current normalized state has no snapshot date')
    else:
        snapshot_date = date.fromisoformat(str(snapshot_date)[:10]).isoformat()
    for row in rows:
        if (row.get('user_id'), row.get('shop_id'), row.get('marketplace')) != (user_id, shop_id, marketplace):
            raise ValueError('Stock row crosses tenant boundary')
        if snapshot_date is not None and str(row.get('snapshot_date'))[:10] != snapshot_date:
            raise ValueError('Stock row crosses snapshot date')
    # One database transaction: validation/insert failure rolls back the deletion.
    return db.rpc('replace_stock_snapshot_rows', {
        'p_table': table, 'p_user_id': user_id, 'p_shop_id': shop_id,
        'p_marketplace': marketplace, 'p_snapshot_date': snapshot_date,
        'p_rows': rows,
    }).execute().data


def replace_stock_metric_dates(db, table, rows, dates, *, user_id, shop_id, marketplace='wb'):
    return sum(replace_stock_rows(db, table,
        [r for r in rows if str(r['snapshot_date'])[:10] == str(day)[:10]],
        user_id=user_id, shop_id=shop_id, marketplace=marketplace,
        snapshot_date=str(day)[:10]) for day in dates)
