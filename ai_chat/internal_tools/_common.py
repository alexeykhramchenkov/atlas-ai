"""Private DB primitives shared by get_*; no question routing or business formulas."""
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

PAGE_SIZE=1000

class DataUnavailableError(ValueError):
    """No recorded facts; must not be rendered as a measured zero."""


def tenant_query(db,table,fields,user_id,shop_id,marketplace):
    if db is None or not user_id or not shop_id or not marketplace:
        raise ValueError('Complete tenant context and Supabase client required')
    return db.table(table).select(fields).eq('user_id',user_id).eq('shop_id',shop_id).eq('marketplace',marketplace)


def period(period_days=None,start_date=None,end_date=None):
    explicit=start_date is not None or end_date is not None
    if (period_days is not None)==explicit:raise ValueError('Specify period_days OR both dates')
    completed=datetime.now(ZoneInfo('Europe/Moscow')).date()-timedelta(days=1)
    if explicit:
        if start_date is None or end_date is None:raise ValueError('Both dates required')
        start,end=date.fromisoformat(start_date),date.fromisoformat(end_date)
    else:
        if type(period_days) is not int or not 1<=period_days<=365:raise ValueError('period_days must be 1..365')
        end=completed;start=end-timedelta(days=period_days-1)
    if start>end or end>completed:raise ValueError('Invalid or unfinished period')
    return start.isoformat(),end.isoformat()


def pages(query):
    rows=[];offset=0
    while True:
        batch=query.range(offset,offset+PAGE_SIZE-1).execute().data or []
        rows.extend(batch)
        if len(batch)<PAGE_SIZE:return rows
        offset+=PAGE_SIZE


def number(value,*,integer=False,signed=False):
    if value is None or isinstance(value,bool):raise ValueError('Missing numeric fact')
    try:n=Decimal(str(value))
    except (InvalidOperation,ValueError):raise ValueError('Invalid numeric fact') from None
    if not n.is_finite() or (not signed and n<0) or (integer and n!=n.to_integral_value()):
        raise ValueError('Invalid numeric fact')
    return n


def json_number(n):
    return int(n) if n==n.to_integral_value() else float(n)


def sum_rows(rows,fields,keys,*,integer_fields=(),signed_fields=(),optional_fields=()):
    """Sum additive facts only. Missing optional facts propagate null, never zero."""
    grouped={}
    for row in rows:
        key=tuple(row.get(k) for k in keys)
        if any(v is None for v in key):raise ValueError('Missing group identity')
        item=grouped.setdefault(key,{**{k:row[k] for k in keys},**{f:Decimal(0) for f in fields}})
        for field in fields:
            value=row.get(field)
            if value is None and field in optional_fields:item[field]=None
            else:
                n=number(value,integer=field in integer_fields,signed=field in signed_fields)
                if item[field] is not None:item[field]+=n
    result=[]
    for key in sorted(grouped,key=lambda x:tuple(str(v) for v in x)):
        item=grouped[key]
        result.append({k:json_number(v) if isinstance(v,Decimal) else v for k,v in item.items()})
    totals={f:None if any(r[f] is None for r in result) else json_number(sum((Decimal(str(r[f])) for r in result),Decimal(0))) for f in fields}
    return totals,result


def product_titles(db,rows,user_id,shop_id,marketplace):
    from ai_chat.internal_tools.get_products import get_products
    keys=sorted({r['product_key'] for r in rows if r.get('product_key')})
    titles={}
    for i in range(0,len(keys),200):
        facts=get_products(user_id,shop_id,marketplace,product_keys=keys[i:i+200],supabase=db)
        titles.update({r['product_key']:r.get('title') for r in facts['products']})
    return [{**row,'title':titles.get(row.get('product_key'))} for row in rows]
