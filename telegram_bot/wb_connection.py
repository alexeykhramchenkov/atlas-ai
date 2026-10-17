"""Credential messages are intercepted before analytics and question logging."""
import asyncio
import time
from integrations.wb import validate_token, save_account, looks_like_token, ConnectionError

async def begin(update,context):
    if update.effective_chat.type!='private':
        await update.callback_query.answer('Подключение доступно только в личном чате.',show_alert=True);return
    context.user_data['wb_connect']={'chat_id':update.effective_chat.id,'expires':time.time()+600}
    await update.callback_query.answer()
    await update.callback_query.message.reply_text('Отправь ключ WB только для чтения: Контент, Статистика и Аналитика. Ключ будет зашифрован, сообщение удалено после обработки. Он проходит через Telegram. Для отмены напиши «отмена». На ввод есть 10 минут.')

async def intercept(update,context):
    text=update.message.text.strip()
    pending=context.user_data.get('wb_connect')
    if not pending and not looks_like_token(text):return False
    if update.effective_chat.type!='private':
        await update.message.reply_text('Ключи принимаются только в личном чате.');return True
    if pending and pending['chat_id']!=update.effective_chat.id:return True
    if text.lower() in ('отмена','/cancel'):
        context.user_data.pop('wb_connect',None);await update.message.reply_text('Подключение отменено.');return True
    context.user_data.pop('wb_connect',None)
    try:
        if not pending or pending['expires']<time.time():
            answer='Сначала нажми «Подключить Wildberries» в /start.'
        else:
            seller,token=await asyncio.to_thread(validate_token,text)
            result=await asyncio.to_thread(save_account,update.effective_user.id,seller,token)
            answer=f"Wildberries подключён: {result['name']}. Ключ сохранён зашифрованным. Данные этого нового подключения ещё не загружены."
    except ConnectionError as error:answer=str(error)
    except Exception:answer='Не удалось сохранить подключение. Повтори через /start.'
    finally:
        try:await update.message.delete()
        except Exception:
            await update.message.reply_text('Не удалось удалить сообщение. Удали сообщение с ключом вручную.')
    await update.message.reply_text(answer)
    return True
