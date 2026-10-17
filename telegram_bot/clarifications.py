"""Telegram presentation of the existing journal-backed clarification protocol."""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from ai_chat.routing.llm_fallback import validate_clarification_updates


def keyboard(request, journal_id):
    if request.get('action') != 'clarify':
        return None
    options=request.get('clarification',{}).get('options',[])
    if len(options)!=2:
        return None
    return InlineKeyboardMarkup([[InlineKeyboardButton(option['label'],callback_data=f'clarify:{journal_id}:{index}')
        for index,option in enumerate(options)]])


def select_request(pending, index, active):
    for field in ('telegram_user_id','telegram_chat_id','user_id','shop_id','marketplace','connection_id'):
        if pending.get(field)!=active.get(field):
            raise ValueError('Clarification context changed')
    clarification=pending.get('clarification') or {}
    options=clarification.get('options') or []
    if pending.get('action')!='clarify' or type(index) is not int or not 0<=index<len(options):
        raise ValueError('Invalid clarification choice')
    selected=validate_clarification_updates(options[index]['updates'],request=pending,memory=clarification.get('context',{}))
    if any(not selected.get(field) for field in ('dataset','metric','analysis')):
        raise ValueError('Clarification is not executable')
    for field in ('clarification','error_code','message'):
        selected.pop(field,None)
    return {**selected,**active,'action':'execute','is_valid_question':True},options[index]['label']
