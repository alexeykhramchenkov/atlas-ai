"""One registered background runner for reviews and buyer questions."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from itertools import groupby
from db.client import supabase
from db.text_analysis_store import load_sources,load_topics,load_analyses,save_batch
from core.text_analysis import text_payload
from ai_chat.analysis.text_annotation import annotate

BATCH_SIZE=20
MAX_IN_FLIGHT=3


def run_metric_job(job,state,registry_entry):
    user_id,shop_id=int(job['user_id']),int(job['shop_id'])
    marketplace=job.get('marketplace','wb')
    existing={(r['source_type'],r['source_id']):r for r in load_analyses(supabase,user_id,shop_id,marketplace)}
    sources=load_sources(supabase,user_id,shop_id,marketplace)
    pending=[]
    for item in sources:
        old=existing.get((item['source_type'],item['source_id']))
        if old and old['status'] in ('ready','no_text') and old['text_hash']==item['text_hash'] and old.get('product_key')==item.get('product_key'):
            continue
        pending.append(item)
    written=0;calls=0
    empty=[{**r,'status':'no_text','topics':[]} for r in pending if not any(text_payload(r['source_type'],r).values())]
    for start in range(0,len(empty),200):
        written+=save_batch(supabase,user_id,shop_id,marketplace,empty[start:start+200])
    nonempty=[r for r in pending if any(text_payload(r['source_type'],r).values())]
    batches=[]
    for category,group in groupby(sorted(nonempty,key=lambda r:r.get('category','')),key=lambda r:r.get('category','')):
        same_category=list(group)
        batches.extend(same_category[start:start+BATCH_SIZE] for start in range(0,len(same_category),BATCH_SIZE))
    with ThreadPoolExecutor(max_workers=MAX_IN_FLIGHT) as pool:
        for start in range(0,len(batches),MAX_IN_FLIGHT):
            dictionary=load_topics(supabase,user_id,shop_id,marketplace)
            futures={pool.submit(annotate,batch,dictionary):batch for batch in batches[start:start+MAX_IN_FLIGHT]}
            failures=[]
            for future in as_completed(futures):
                batch=futures[future]
                try:
                    annotations=future.result();calls+=1
                    prepared=[{**r,'status':'ready','topics':aspects} for r,aspects in zip(batch,annotations)]
                    written+=save_batch(supabase,user_id,shop_id,marketplace,prepared)
                    print(f'Buyer text topics: processed={written}/{len(pending)} llm_batches={calls}',flush=True)
                except Exception as error:
                    save_batch(supabase,user_id,shop_id,marketplace,[{**r,'status':'error',
                               'error_code':type(error).__name__,'topics':[]} for r in batch])
                    failures.append(error)
            if failures:raise failures[0]
    print(f'Buyer text topics: sources={len(sources)} changed={len(pending)} llm_batches={calls}',flush=True)
    dates=[r['source_created_at'][:10] for r in sources if r.get('source_created_at')]
    return {'rows_read':len(sources),'rows_upserted':written,'last_processed_date':max(dates) if dates else None}
