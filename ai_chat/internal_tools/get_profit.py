"""Recorded finance and marketplace-expense facts. No invented cost or profit."""
from ._common import tenant_query,pages,period,sum_rows,product_titles,DataUnavailableError
PROFIT_FIELDS=('sales_count','returns_count','net_sales_count','sales_amount','returns_amount','net_sales_amount','cogs_amount','marketplace_expense_amount','commission_amount','logistics_amount','storage_amount','acquiring_amount','deduction_amount','gross_profit','net_profit')
EXPENSE_FIELDS=('wb_commission_amount','logistics_amount','storage_amount','acquiring_amount','penalty_amount','deduction_amount','acceptance_amount','other_income_amount','other_expense_amount','seller_payout','total_income_amount','total_expense_amount','gross_margin_before_cost','wb_net_result','compensation_amount','reimbursement_amount')

def get_profit(user_id,shop_id,marketplace='wb',product_key=None,period_days=None,start_date=None,end_date=None,view='profit',*,supabase=None):
    if view not in {'profit','expenses'}:raise ValueError('view must be profit or expenses')
    start,end=period(period_days,start_date,end_date)
    table='metrics_financial_daily' if view=='profit' else 'metrics_realization_daily'
    fields=PROFIT_FIELDS if view=='profit' else EXPENSE_FIELDS
    q=tenant_query(supabase,table,'id,snapshot_date,product_key,'+','.join(fields),user_id,shop_id,marketplace)
    if product_key is not None:q=q.eq('product_key',product_key)
    rows=pages(q.gte('snapshot_date',start).lte('snapshot_date',end).order('snapshot_date').order('product_key').order('id'))
    if not rows:raise DataUnavailableError('No recorded finance facts')
    totals,products=sum_rows(rows,fields,['product_key'],integer_fields=("sales_count","returns_count","net_sales_count"),signed_fields=fields,optional_fields=fields)
    products=product_titles(supabase,products,user_id,shop_id,marketplace)
    return {'start_date':start,'end_date':end,'view':view,**totals,'products':products}
