"""Compatibility enrichment; catalog access belongs to get_products and is tenant bound."""
from ai_chat.internal_tools.get_products import get_products


def enrich_products(rows, supabase, *, user_id, shop_id, marketplace='wb'):
    if not rows:return rows
    keys=sorted({r['product_key'] for r in rows if r.get('product_key')})
    if not keys:return rows
    products=get_products(user_id,shop_id,marketplace,product_keys=keys,supabase=supabase)['products']
    by_key={p['product_key']:p for p in products}
    return [{**row,**{k:v for k,v in by_key.get(row.get('product_key'),{}).items() if v is not None}} for row in rows]
