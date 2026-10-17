"""Tenant-scoped catalog facts. No sales/stock calculations."""
from ._common import tenant_query,pages

FIELDS='id,product_key,title,marketplace_product_id,seller_sku,brand,subject_name,category_name,main_photo_url,created_at'

def get_products(user_id,shop_id,marketplace='wb',product_key=None,*,product_keys=None,supabase=None):
    if product_key is not None and product_keys is not None:raise ValueError('Use one product selector')
    if product_keys is not None and (not isinstance(product_keys,list) or any(not isinstance(k,str) or not k for k in product_keys)):
        raise ValueError('product_keys must be a list of nonempty keys')
    query=tenant_query(supabase,'normalized_products',FIELDS,user_id,shop_id,marketplace)
    if product_keys==[]:return {'products_count':0,'products':[]}
    if product_key is not None:query=query.eq('product_key',product_key)
    rows=[]
    batches=[product_keys[i:i+200] for i in range(0,len(product_keys),200)] if product_keys is not None else [None]
    for keys in batches:
        q=tenant_query(supabase,'normalized_products',FIELDS,user_id,shop_id,marketplace)
        if product_key is not None:q=q.eq('product_key',product_key)
        if keys is not None:q=q.in_('product_key',keys)
        rows.extend(pages(q.order('product_key').order('id')))
    products={}
    for row in rows:
        key=row.get('product_key')
        if not key:raise ValueError('Missing product_key')
        clean={k:row.get(k) for k in FIELDS.split(',') if k!='id'}
        if key in products and products[key]!=clean:raise ValueError('Conflicting catalog records')
        products[key]=clean
    values=[products[k] for k in sorted(products)]
    return {'products_count':len(values),'products':values}
