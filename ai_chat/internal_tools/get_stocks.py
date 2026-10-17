"""Single tenant-bound stock reader. Quantities include both movement directions."""
from datetime import date
from decimal import Decimal, InvalidOperation

PAGE_SIZE = 1000


from ._common import DataUnavailableError


class StockDataUnavailableError(DataUnavailableError):
    def __init__(self, as_of=None):
        self.as_of = as_of
        super().__init__(f"Stock facts are unavailable for requested selection at {as_of}")


def get_stocks(user_id, shop_id, marketplace="wb", product_key=None,
               variant_key=None, warehouse_key=None, as_of=None, level="product", *, supabase=None):
    if supabase is None or not user_id or not shop_id or not marketplace:
        raise ValueError("Database and complete tenant context are required")
    if level not in {"product", "variant"}:
        raise ValueError("level must be product or variant")
    if variant_key is not None and level != "variant":
        raise ValueError("variant_key requires variant detail")
    if as_of is not None:
        as_of = date.fromisoformat(as_of).isoformat()
    variant_source = level == "variant" or warehouse_key is not None
    table = "snapshots_stocks_variants_daily" if variant_source else "metrics_stocks_daily"
    def query(table_name, fields):
        return (supabase.table(table_name).select(fields).eq("user_id",user_id)
                .eq("shop_id",shop_id).eq("marketplace",marketplace))
    # Use one store snapshot, never an older date selected separately per product.
    if as_of is None:
        # A confirmed empty/new source must not resurrect an older positive snapshot.
        latest_table = 'raw_wb_stocks' if marketplace == 'wb' else table
        latest = query(latest_table,"snapshot_date").order("snapshot_date",desc=True).limit(1).execute().data or []
        if not latest:
            raise StockDataUnavailableError()
        as_of = str(latest[0]["snapshot_date"])[:10]
    fields = ("id,product_key,variant_key,size_name,warehouse_key,warehouse_name,quantity,in_way_to_client,in_way_from_client"
              if variant_source else "id,product_key,total_quantity,total_in_way_to_client,total_in_way_from_client")
    source=[];offset=0
    while True:
        q=query(table,fields).eq("snapshot_date",as_of)
        for key,value in (("product_key",product_key),("variant_key",variant_key),("warehouse_key",warehouse_key)):
            if value is not None:q=q.eq(key,value)
        batch=q.order("product_key").order("id").range(offset,offset+PAGE_SIZE-1).execute().data or []
        source.extend(batch)
        if len(batch)<PAGE_SIZE:break
        offset+=PAGE_SIZE
    if not source:
        raise StockDataUnavailableError(as_of)
    products={}
    for row in source:
        pk=row.get("product_key")
        if not pk:raise ValueError("Stock fact lacks product_key")
        key=(pk,row.get("variant_key"),row.get("warehouse_key")) if level=="variant" else (pk,)
        item=products.setdefault(key,{"product_key":pk,"title":None,"warehouse_quantity":0,
                                      "to_customer_quantity":0,"from_customer_quantity":0,"total_quantity":0})
        if level=="variant":
            for name in ("variant_key","size_name","warehouse_key","warehouse_name"):item[name]=row.get(name)
        columns = (("quantity","in_way_to_client","in_way_from_client") if variant_source else
                   ("total_quantity","total_in_way_to_client","total_in_way_from_client"))
        for dest,column in zip(("warehouse_quantity","to_customer_quantity","from_customer_quantity"),columns):
            value=row.get(column)
            if value is None or isinstance(value,bool):raise ValueError(f"Missing stock fact: {column}")
            try:number=Decimal(str(value))
            except InvalidOperation:raise ValueError(f"Invalid stock fact: {column}") from None
            if not number.is_finite() or number<0 or number!=number.to_integral_value():
                raise ValueError(f"Invalid stock fact: {column}")
            item[dest]+=int(number)
        item["total_quantity"]=item["warehouse_quantity"]+item["to_customer_quantity"]+item["from_customer_quantity"]
    keys=sorted({item["product_key"] for item in products.values()})
    names={};sizes={}
    for index in range(0,len(keys),200):
        batch_keys=keys[index:index+200];offset=0
        from .get_products import get_products
        catalog=get_products(user_id,shop_id,marketplace,product_keys=batch_keys,supabase=supabase)['products']
        names.update({row['product_key']:row.get('title') for row in catalog})
        if level=="variant" and any(not item.get("size_name") for item in products.values() if item["product_key"] in batch_keys):
            offset=0
            while True:
                batch=(query("normalized_product_variants","id,product_key,variant_key,size_name").in_("product_key",batch_keys)
                       .order("product_key").order("id").range(offset,offset+PAGE_SIZE-1).execute().data or [])
                sizes.update({(row["product_key"],row["variant_key"]):row.get("size_name") for row in batch})
                if len(batch)<PAGE_SIZE:break
                offset+=PAGE_SIZE
    rows=list(products.values())
    for item in rows:
        item["title"]=names.get(item["product_key"])
        if level=="variant":item["size_name"]=item.get("size_name") or sizes.get((item["product_key"],item.get("variant_key")))
    return {"as_of":as_of,**{field:sum(item[field] for item in rows)
            for field in ("warehouse_quantity","to_customer_quantity","from_customer_quantity","total_quantity")},"products":rows}
