"""Count saved, current annotations. No DB calls or LLM in the request path."""
from ai_chat.analysis.analysis_type.rank import run as rank
from core.text_analysis import normalize_topic


def summarize(rows, *, source_type, sentiment=None):
    key='feedback_id' if source_type=='review' else 'question_id'
    count_field='reviews_count' if source_type=='review' else 'questions_count'
    membership='feedback_ids' if source_type=='review' else 'question_ids'
    grouped={};matched=set();statuses=[]
    for row in rows:
        analysis=row.get('topic_analysis') or {'status':'pending','topics':[]}
        statuses.append(analysis['status'])
        if analysis['status']!='ready':continue
        for aspect in analysis['topics']:
            if sentiment is not None and aspect['sentiment']!=sentiment:continue
            topic=grouped.setdefault(normalize_topic(aspect['title']),{'topic_id':aspect['topic_id'],
                'topic':aspect['title'],'ids':set()})
            topic['ids'].add(row[key]);matched.add(row[key])
    prepared=[{'topic_id':r['topic_id'],'topic':r['topic'],count_field:len(r['ids']),
               membership:sorted(r['ids'])} for r in grouped.values()]
    ranked=rank(rows=prepared,metric=count_field,direction='desc',limit=max(len(prepared),1))['rows']
    status='incomplete' if any(s in ('pending','error') for s in statuses) else 'no_text' if statuses and all(s=='no_text' for s in statuses) else 'ok'
    return {'status':status,'rows':ranked,'matched_sources_count':len(matched),
            'analyzed_sources_count':sum(s in ('ready','no_text') for s in statuses)}
