"""Review facts, bounded by creation time in the requested Moscow calendar period."""
from datetime import date,timedelta
from ._common import tenant_query,pages,period,number,product_titles,DataUnavailableError
FIELDS='id,feedback_id,product_key,rating,text,pros,cons,tags,has_photo,has_answer,created_at'

def get_reviews(user_id,shop_id,marketplace='wb',product_key=None,period_days=None,start_date=None,end_date=None,rating_min=None,rating_max=None,include_topics=False,*,supabase=None):
    if type(include_topics) is not bool:raise ValueError('include_topics must be boolean')
    start,end=(None,None) if all(v is None for v in (period_days,start_date,end_date)) else period(period_days,start_date,end_date)
    low=1 if rating_min is None else rating_min;high=5 if rating_max is None else rating_max
    if type(low) is not int or type(high) is not int or not 1<=low<=high<=5:raise ValueError('Invalid rating range')
    q=tenant_query(supabase,'normalized_feedbacks',FIELDS,user_id,shop_id,marketplace)
    if product_key is not None:q=q.eq('product_key',product_key)
    if start is not None:
        upper=(date.fromisoformat(end)+timedelta(days=1)).isoformat()
        q=q.gte('created_at',start+'T00:00:00+03:00').lt('created_at',upper+'T00:00:00+03:00')
    rows=pages(q.order('created_at').order('id'))
    unique={}
    for row in rows:
        key=row.get('feedback_id')
        if not key:raise ValueError('Missing review identity')
        rating=number(row.get('rating'),integer=True)
        if not 1<=rating<=5:raise ValueError('Invalid recorded rating')
        if not low<=rating<=high:continue
        item={k:row.get(k) for k in FIELDS.split(',') if k!='id'}
        item['rating']=int(rating)
        if key in unique and unique[key]!=item:raise ValueError('Conflicting review records')
        unique[key]=item
    if not rows:raise DataUnavailableError('No review facts')
    reviews=product_titles(supabase,list(unique.values()),user_id,shop_id,marketplace)
    if include_topics:
        from db.text_analysis_store import attach_analyses
        reviews=attach_analyses(supabase,reviews,'review',user_id,shop_id,marketplace)
    return {'start_date':start,'end_date':end,'reviews_count':len(reviews),'reviews':reviews}
