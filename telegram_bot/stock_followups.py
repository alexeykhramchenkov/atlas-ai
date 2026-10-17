"""Bind each keyboard to its original tenant, actor, chat, and product result."""
import json
import secrets
import time
from pathlib import Path
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

STORE=Path(__file__).resolve().parents[1]/'.runtime'/'stock-contexts'
LABELS={'priority':'Что пополнить первым?', 'sizes':'Показать остатки по размерам', 'sales':'Как продавались эти товары?'}


def save_context(request,result):
    STORE.mkdir(parents=True,exist_ok=True,mode=0o700)
    token=secrets.token_hex(8)
    path=STORE/(token+'.json')
    path.write_text(json.dumps({'request':request,'result':result,'created_at':time.time()},ensure_ascii=False))
    path.chmod(0o600)
    return token


def load_context(token,actor,chat,current):
    if len(token)!=16 or any(c not in '0123456789abcdef' for c in token):return None
    try:payload=json.loads((STORE/(token+'.json')).read_text())
    except (OSError,ValueError):return None
    req=payload['request']
    if time.time()-payload['created_at']>86400:return None
    if req.get('telegram_user_id')!=actor or req.get('telegram_chat_id')!=chat:return None
    if not current or any(req.get(k)!=current.get(k) for k in ('user_id','shop_id','marketplace')):return None
    return payload


def keyboard(token):
    return InlineKeyboardMarkup([[InlineKeyboardButton(label,callback_data=f'stock:{token}:{action}')] for action,label in LABELS.items()])


def formatted(answer,result):
    from html import escape
    text=escape(answer)
    first=text.split('\n',1)[0]
    text=text.replace(first,'<b>'+first+'</b>',1)
    for name in {r.get('title') or r['product_key'] for r in result.get('rows',[])}:
        safe=escape(name)
        text=text.replace(safe,'<b>'+safe+'</b>')
    return text



def card_rows(result):
    return sorted(result['rows'],key=lambda r:r['stock_qty']==0)


def card_caption(result,index):
    from html import escape
    row=card_rows(result)[index]
    title=escape(row.get('title') or row['product_key'])
    state='🔴 Уже закончился · 0 шт.' if row['stock_qty']==0 else f"🟠 Осталась {row['stock_qty']:g} шт. · запас ≈ {round(row['days_left'],1):g} дн."
    text=f"<b>{title}</b>\nАртикул WB: {escape(str(row.get('marketplace_product_id') or row['product_key']))}\n\n{state}"
    if result.get('stale'):text+='\n⚠️ Архивный срез.'
    return text


def card_keyboard(token,result,index):
    count=len(card_rows(result))
    nav=[InlineKeyboardButton('← Назад',callback_data=f'stock:{token}:page:{(index-1)%count}'),
         InlineKeyboardButton(f'{index+1} из {count}',callback_data=f'stock:{token}:noop:{index}'),
         InlineKeyboardButton('Далее →',callback_data=f'stock:{token}:page:{(index+1)%count}')]
    return InlineKeyboardMarkup([nav,
        [InlineKeyboardButton('Остатки по размерам',callback_data=f'stock:{token}:sizes:{index}')],
        [InlineKeyboardButton('Как заказывали этот товар?',callback_data=f'stock:{token}:sales:{index}')],
        [InlineKeyboardButton('Что пополнить первым?',callback_data=f'stock:{token}:priority')]])


async def send_card(message,token,result,index=0):
    from telegram.error import BadRequest
    row=card_rows(result)[index]
    caption=card_caption(result,index)
    markup=card_keyboard(token,result,index)
    if row.get('main_photo_url'):
        try:
            return await message.reply_photo(row['main_photo_url'],caption=caption,parse_mode='HTML',reply_markup=markup)
        except BadRequest:
            pass
    return await message.reply_text(caption,parse_mode='HTML',reply_markup=markup)
