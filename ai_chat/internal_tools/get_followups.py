"""Buyer question facts. No semantic grouping or implicit period."""
from datetime import date, timedelta

from ._common import tenant_query, pages, period, product_titles

FIELDS = ('id,question_id,product_key,product_name,question_text,question_created_at,'
          'is_answered,answer_text,answer_created_at')


def get_followups(user_id, shop_id, marketplace='wb', product_key=None,
                  is_answered=None, start_date=None, end_date=None, include_topics=False, *, supabase=None):
    if type(include_topics) is not bool:
        raise ValueError('include_topics must be boolean')
    if is_answered is not None and type(is_answered) is not bool:
        raise ValueError('is_answered must be boolean or null')
    query = tenant_query(supabase, 'normalized_questions', FIELDS,
                         user_id, shop_id, marketplace)
    if product_key is not None:
        query = query.eq('product_key', product_key)
    if is_answered is not None:
        query = query.eq('is_answered', is_answered)
    if start_date is not None or end_date is not None:
        start, end = period(start_date=start_date, end_date=end_date)
        upper = (date.fromisoformat(end) + timedelta(days=1)).isoformat()
        query = query.gte('question_created_at', start+'T00:00:00+03:00').lt(
            'question_created_at', upper+'T00:00:00+03:00')
    unique = {}
    for row in pages(query.order('question_created_at', desc=True).order('id')):
        key = row.get('question_id')
        if not key:
            raise ValueError('Missing question identity')
        item = {k: row.get(k) for k in FIELDS.split(',') if k != 'id'}
        if key in unique and unique[key] != item:
            raise ValueError('Conflicting question records')
        unique[key] = item
    questions = product_titles(supabase, list(unique.values()), user_id, shop_id, marketplace)
    for item in questions:
        item['title'] = item.get('title') or item.get('product_name')
        item.pop('product_name', None)
    if include_topics:
        from db.text_analysis_store import attach_analyses
        questions=attach_analyses(supabase,questions,'question',user_id,shop_id,marketplace)
    return {'questions_count': len(questions), 'questions': questions}
