"""Tenant-scoped persistence for background buyer-text annotations."""
from ai_chat.internal_tools._common import tenant_query, pages
from core.text_analysis import ANALYSIS_VERSION, text_hash, text_payload


def load_sources(db, user_id, shop_id, marketplace):
    catalog=pages(tenant_query(db,'normalized_products','product_key,category_name,subject_name',user_id,shop_id,marketplace).order('id'))
    categories={r['product_key']:r.get('category_name') or r.get('subject_name') or '' for r in catalog}
    specs=[('review','normalized_feedbacks','feedback_id','created_at','id,feedback_id,product_key,created_at,text,pros,cons'),
           ('question','normalized_questions','question_id','question_created_at','id,question_id,product_key,question_created_at,question_text')]
    result=[]
    for kind,table,key,created,fields in specs:
        unique={}
        for row in pages(tenant_query(db,table,fields,user_id,shop_id,marketplace).order('id')):
            sid=row.get(key)
            if not sid:raise ValueError('Missing buyer-text source identity')
            item={**row,'source_type':kind,'source_id':sid,'source_created_at':row.get(created),
                  'category':categories.get(row.get('product_key'),'')}
            item['text_hash']=text_hash(kind,item)
            if sid in unique and (unique[sid]['text_hash'],unique[sid]['product_key'])!=(item['text_hash'],item['product_key']):
                raise ValueError('Conflicting buyer-text sources')
            unique[sid]=item
        result.extend(unique.values())
    return result


def load_topics(db,user_id,shop_id,marketplace):
    return pages(tenant_query(db,'text_topics','topic_id,title,category,merged_into',user_id,shop_id,marketplace).order('topic_id'))


def load_analyses(db,user_id,shop_id,marketplace,source_type=None,source_ids=None):
    def query():
        q=tenant_query(db,'text_analyses','*',user_id,shop_id,marketplace).eq('analysis_version',ANALYSIS_VERSION)
        return q.eq('source_type',source_type) if source_type else q
    if source_ids is None:return pages(query().order('analysis_id'))
    result=[]
    for start in range(0,len(source_ids),200):
        result.extend(pages(query().in_('source_id',source_ids[start:start+200]).order('analysis_id')))
    return result


def save_batch(db,user_id,shop_id,marketplace,items):
    if not items:return 0
    payload=[{k:item.get(k) for k in ('source_type','source_id','product_key','source_created_at',
                                    'text_hash','status','error_code','topics')} for item in items]
    return db.rpc('save_text_analysis_batch',{'p_user_id':user_id,'p_shop_id':shop_id,
        'p_marketplace':marketplace,'p_version':ANALYSIS_VERSION,'p_items':payload}).execute().data


def attach_analyses(db,rows,source_type,user_id,shop_id,marketplace):
    if not rows:return rows
    key='feedback_id' if source_type=='review' else 'question_id'
    analyses=load_analyses(db,user_id,shop_id,marketplace,source_type,[r[key] for r in rows])
    by_source={r['source_id']:r for r in analyses}
    ids=[r['analysis_id'] for r in analyses]
    aspects=[]
    for start in range(0,len(ids),200):
        aspects.extend(pages(tenant_query(db,'text_analysis_topics','analysis_id,topic_id,summary,sentiment',
            user_id,shop_id,marketplace).in_('analysis_id',ids[start:start+200]).order('analysis_id').order('topic_id')))
    topics={r['topic_id']:r for r in load_topics(db,user_id,shop_id,marketplace)}
    def canonical(tid):
        seen=set()
        while True:
            if tid in seen or tid not in topics:raise ValueError('Invalid topic merge reference')
            seen.add(tid);topic=topics[tid]
            if not topic.get('merged_into'):return topic
            tid=topic['merged_into']
    grouped={}
    for aspect in aspects:
        topic=canonical(aspect['topic_id'])
        grouped.setdefault(aspect['analysis_id'],[]).append({
            'topic_id':topic['topic_id'],'title':topic['title'],
            'summary':aspect['summary'],'sentiment':aspect['sentiment']})
    result=[]
    for row in rows:
        record=by_source.get(row[key]);status='pending';annotations=[]
        if record and record['text_hash']==text_hash(source_type,row) and record.get('product_key')==row.get('product_key'):
            status=record['status']
            if status=='ready':annotations=grouped.get(record['analysis_id'],[])
        result.append({**row,'topic_analysis':{'status':status,'analysis_version':ANALYSIS_VERSION,'topics':annotations}})
    return result
