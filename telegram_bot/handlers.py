import traceback
from time import perf_counter

from telegram import Update
from telegram.ext import ContextTypes

from ai_chat.answer_builder import build_answer
from ai_chat.router import route
from ai_chat.memory import resolve_last_product_context
from ai_chat.executor import executor
from ai_chat.language import detect_language
from ai_chat.timing import log_timing
from db.client import supabase, supabase_admin
from telegram_bot.keyboards import (
    MARKETPLACE_LABELS,
    build_marketplace_accounts_keyboard,
    build_shopify_connection_keyboard,
)

TELEGRAM_MESSAGE_LIMIT = 3900
SHOPIFY_CONNECT_MESSAGE = (
    "Привет! Я Atlas AI — AI-аналитик для Shopify-магазинов.\n\n"
    "Сначала подключите Shopify, чтобы я мог получить доступ к данным магазина."
)
SHOPIFY_NOT_SYNCED_MESSAGE = (
    "Shopify подключен ✅\n"
    "Данные магазина еще не синхронизированы.\n"
    "Я сообщу, когда можно будет задавать вопросы по аналитике."
)
SHOPIFY_SYNC_NOT_READY_ERROR = "shopify_sync_not_ready"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("wb_connect", None)
    telegram_user_id = update.effective_user.id if update.effective_user else None
    telegram_chat_id = update.effective_chat.id if update.effective_chat else None
    args = context.args or []

    if args and args[0] == "shopify_connected":
        if telegram_user_id and has_connected_shopify_connection(telegram_user_id):
            await update.message.reply_text(
                SHOPIFY_NOT_SYNCED_MESSAGE,
                reply_markup=build_shopify_connection_keyboard(
                    telegram_user_id=telegram_user_id,
                    telegram_chat_id=telegram_chat_id,
                    shopify_connected=True,
                ),
            )
        else:
            await update.message.reply_text(
                "Не удалось подтвердить подключение Shopify. Попробуйте подключить снова."
            )
        return

    connections = get_marketplace_connections(telegram_user_id)
    active_context = (
        resolve_active_telegram_context(
            telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_chat_id,
        )
        if telegram_user_id is not None
        else None
    )
    journal_request = active_context or {"telegram_user_id": telegram_user_id, "telegram_chat_id": telegram_chat_id}
    journal_id = log_ai_question(question="/start", request=journal_request, result=None,
        status="blocked", error_message="dialogue_reset", memory_used={}, delivery_status="pending")
    active_connection_id = active_context.get("connection_id") if active_context else None
    text = (
        "Выберите магазин, данные которого нужно анализировать.\n\n"
        "Можно подключить несколько кабинетов на разных маркетплейсах."
        if connections
        else "Подключите первый магазин, чтобы начать аналитику."
    )

    keyboard = build_marketplace_accounts_keyboard(connections=connections,
        active_connection_id=active_connection_id, telegram_user_id=telegram_user_id,
        telegram_chat_id=telegram_chat_id)
    if journal_id is not None:
        await send_journal_reply(update, journal_id, text, request=journal_request, result=None,
            status="blocked", error_message="dialogue_reset", memory_used={}, reply_markup=keyboard)
    else:
        await update.message.reply_text(text, reply_markup=keyboard)



async def handle_integration_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return

    if query.data and query.data.startswith("clarify:"):
        from ai_chat.memory import latest_dialogue_row
        from telegram_bot.clarifications import select_request
        try:
            _,source,index=query.data.split(':')
            active=resolve_active_telegram_context(telegram_user_id=update.effective_user.id,
                telegram_chat_id=update.effective_chat.id)
            if not active:
                raise ValueError('No active shop')
            previous=latest_dialogue_row(telegram_user_id=active['telegram_user_id'],
                telegram_chat_id=active['telegram_chat_id'],user_id=active['user_id'],shop_id=active['shop_id'],
                marketplace=active['marketplace'],supabase=supabase)
            if not previous or previous['id']!=int(source) or previous.get('status')!='invalid_question' or previous.get('delivery_status')!='sent':
                raise ValueError('Expired clarification')
            selected,label=select_request(previous['router_request'],int(index),active)
        except (ValueError,KeyError,TypeError):
            await query.answer('Это уточнение уже неактуально. Задай вопрос заново.',show_alert=True)
            return
        await query.answer()
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        await handle_message(update,context,resolved_request=selected,question_text='Выбор: '+label)
        return

    if query.data and query.data.startswith("stock:"):
        await query.answer("Подсказки временно отключены. Напишите вопрос текстом.", show_alert=True)
        return

    if query.data and query.data.startswith("context:select:"):
        telegram_user_id = update.effective_user.id if update.effective_user else None
        if telegram_user_id is None:
            await query.answer("Не удалось определить пользователя.", show_alert=True)
            return
        try:
            connection_id = int(query.data.rsplit(":", 1)[-1])
        except ValueError:
            await query.answer("Некорректный магазин.", show_alert=True)
            return
        connection = set_active_marketplace_connection(
            telegram_user_id=telegram_user_id,
            connection_id=connection_id,
        )
        if not connection:
            await query.answer("Магазин не найден.", show_alert=True)
            return
        selected_context = resolve_active_telegram_context(telegram_user_id=telegram_user_id,
            telegram_chat_id=update.effective_chat.id)
        if selected_context:
            log_ai_question(question="Выбор магазина", request=selected_context, result=None,
                            status="blocked", error_message="dialogue_reset")
        label = MARKETPLACE_LABELS.get(connection["marketplace"], connection["marketplace"])
        account_name = (
            connection.get("external_account_name")
            or connection.get("external_account_id")
            or connection["shop_id"]
        )
        await query.answer(f"Выбран {label}")
        await query.edit_message_text(
            f"Активный магазин: {label} · {account_name}\n\n"
            "Теперь задайте вопрос об аналитике обычным сообщением."
        )
        return

    if query.data == "connection:planned:wb":
        from telegram_bot.wb_connection import begin
        await begin(update, context)
        return

    if query.data and query.data.startswith("connection:planned:"):
        marketplace = query.data.rsplit(":", 1)[-1]
        label = MARKETPLACE_LABELS.get(marketplace, marketplace)
        await query.answer(
            f"Подключение {label} будет добавлено следующим шагом.",
            show_alert=True,
        )
        return

    if query.data == "connection:shopify_connected":
        await query.answer("Shopify уже подключен.")
        return

    await query.answer("Откройте /start.")


def get_shopify_connection(telegram_user_id: int | None) -> dict | None:
    if telegram_user_id is None:
        return None

    user_response = (
        supabase
        .table("system_users")
        .select("id")
        .eq("tg_user_id", telegram_user_id)
        .limit(1)
        .execute()
    )
    users = user_response.data or []
    if not users:
        return None

    connection_response = (
        supabase
        .table("system_marketplace_connections")
        .select("id,external_account_id,last_sync_at,status")
        .eq("user_id", users[0]["id"])
        .eq("marketplace", "shopify")
        .eq("status", "connected")
        .limit(1)
        .execute()
    )
    rows = connection_response.data or []
    return rows[0] if rows else None


def get_marketplace_connections(telegram_user_id: int | None) -> list[dict]:
    if telegram_user_id is None:
        return []
    user_response = (
        supabase.table("system_users")
        .select("id")
        .eq("tg_user_id", telegram_user_id)
        .limit(1)
        .execute()
    )
    users = user_response.data or []
    if not users:
        return []
    response = (
        supabase.table("system_marketplace_connections")
        .select("id,user_id,shop_id,marketplace,external_account_id,external_account_name,status,last_sync_at")
        .eq("user_id", users[0]["id"])
        .in_("status", ["active", "connected"])
        .order("id")
        .execute()
    )
    return response.data or []


def set_active_marketplace_connection(
    *, telegram_user_id: int, connection_id: int
) -> dict | None:
    connections = get_marketplace_connections(telegram_user_id)
    connection = next((row for row in connections if int(row["id"]) == connection_id), None)
    if connection is None:
        return None
    supabase_admin.table("system_user_context").upsert(
        {
            "tg_user_id": telegram_user_id,
            "owner_user_id": connection["user_id"],
            "active_user_id": connection["user_id"],
            "active_shop_id": connection["shop_id"],
            "active_marketplace": connection["marketplace"],
            "active_connection_id": connection["id"],
        },
        on_conflict="tg_user_id",
    ).execute()
    return connection


def has_connected_shopify_connection(telegram_user_id: int) -> bool:
    return bool(get_shopify_connection(telegram_user_id))


def resolve_active_telegram_context(
    *,
    telegram_user_id: int,
    telegram_chat_id: int | None,
) -> dict | None:
    response = (
        supabase
        .table("system_user_context")
        .select("active_user_id,active_shop_id,active_marketplace,active_connection_id")
        .eq("tg_user_id", telegram_user_id)
        .limit(1)
        .execute()
    )
    rows = response.data or []

    if not rows:
        return None

    row = rows[0]
    return {
        "telegram_user_id": telegram_user_id,
        "telegram_chat_id": telegram_chat_id,
        "user_id": int(row["active_user_id"]),
        "shop_id": int(row["active_shop_id"]),
        "marketplace": row.get("active_marketplace") or "wb",
        "connection_id": row.get("active_connection_id"),
    }


def is_shopify_sync_ready(*, user_id: int, shop_id: int) -> bool:
    return False


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE, *, resolved_request=None, question_text=None) -> None:
    from telegram_bot.wb_connection import intercept
    if resolved_request is None and await intercept(update, context):
        return  # Credential messages must never enter the dialogue journal.
    from ai_chat.memory import latest_dialogue_row
    from ai_chat.routing.route import resolve_clarification_reply
    question = question_text if question_text is not None else (update.message.text or "")
    routing_question = question.strip()
    actor = update.effective_user.id if update.effective_user else None
    chat = update.effective_chat.id if update.effective_chat else None
    request = {"telegram_user_id": actor, "telegram_chat_id": chat}
    journal_id = log_ai_question(question=question, request=request, result=None,
        status="blocked", memory_used={}, delivery_status="pending")
    if journal_id is None:
        await update.message.reply_text("Не удалось сохранить вопрос в журнал. Попробуй позже.")
        return
    result = None
    used_memory = {}
    status = "blocked"
    error_message = None
    started = perf_counter()
    try:
        language = detect_language(routing_question)
        request["language"] = language
        if not routing_question:
            answer = "Напиши вопрос о магазине."
            error_message = "empty_question"
        elif actor is None:
            answer = "Не удалось определить Telegram пользователя."
            error_message = "missing_telegram_user"
        else:
            active = resolve_active_telegram_context(telegram_user_id=actor, telegram_chat_id=chat)
            if not active:
                answer = "Не найден активный магазин для этого Telegram пользователя."
                error_message = "missing_active_shop"
            elif active["marketplace"] == "shopify" and not is_shopify_sync_ready(user_id=active["user_id"], shop_id=active["shop_id"]):
                request.update(active)
                answer = SHOPIFY_NOT_SYNCED_MESSAGE
                error_message = SHOPIFY_SYNC_NOT_READY_ERROR
            else:
                request_context = {**active, "language": language}
                request = request_context
                previous = latest_dialogue_row(telegram_user_id=actor, telegram_chat_id=chat,
                    user_id=active["user_id"], shop_id=active["shop_id"], marketplace=active["marketplace"],
                    supabase=supabase, before_question_id=journal_id)
                memory = resolve_last_product_context(telegram_user_id=actor, telegram_chat_id=chat,
                    user_id=active["user_id"], shop_id=active["shop_id"], marketplace=active["marketplace"],
                    supabase=supabase, before_question_id=journal_id)
                resolved = resolved_request if resolved_request is not None else resolve_clarification_reply(question=routing_question, request_context=request_context,
                    supabase=supabase, before_question_id=journal_id)
                clarification = resolved is not None
                if resolved is None:
                    resolved = route(routing_question, memory=memory, request_context=request_context)
                request = {**request_context, **resolved}
                used_memory = journal_memory_used(routing_question, request, memory, previous, clarification)
                if request.get("action") == "clarify":
                    status = "invalid_question"
                    result = {"question":request["clarification"]["question"]}
                    answer = build_answer(question=question,request=request,result=result,supabase=supabase,language=language)
                elif not request.get("is_valid_question", True):
                    status = "invalid_question"
                    error_message = request.get("message") or request.get("error_code")
                    if request.get("error_code") in {"unclear_question", "unsupported_metric"}:
                        answer = build_answer(question=question, request=request, result=None, supabase=supabase, language=language)
                    else:
                        answer = ("Я не понял вопрос. Попробуй спросить, например:\n\n"
                                  "У каких товаров больше всего заказов?\n"
                                  "Какой товар дал больше всего выручки?\n"
                                  "У каких товаров меньше всего прибыли?")
                else:
                    result = executor.execute(request)
                    answer = build_answer(question=question, request=request, result=result, supabase=supabase, language=language)
                    result_status = (result or {}).get("status")
                    status = "blocked" if result_status in {"incomplete", "no_product"} else "success"
                    error_message = result_status if status == "blocked" else None
    except Exception as error:
        log_ai_error(question=question, request=request, error=error)
        status = "error"
        error_message = str(error)
        answer = "Не удалось получить данные магазина. Проверьте доступность базы и повторите вопрос."
    from telegram_bot.clarifications import keyboard
    await send_journal_reply(update, journal_id, answer, request=request, result=result,
                             status=status, error_message=error_message, memory_used=used_memory,
                             reply_markup=keyboard(request,journal_id))
    log_timing(stage="total_request", started_at=started, source="telegram")


def journal_memory_used(question, request, memory, previous, clarification=False):
    """Audit only the values selected into the request, never all available memory."""
    if not previous:
        return {}
    used = {}
    if request.get("action") == "clarify":
        return {"shown_product_keys":memory.get("shown_product_keys", []),"source_question_id":previous.get("id")}
    if (request.get("dataset") == "orders" and request.get("metric") == "orders_amount"
            and request.get("entity") == "product" and not request.get("product_keys")
            and memory.get("last_scope") == "store" and memory.get("last_metric") in {"orders_amount", "orders_revenue"}
            and request.get("date_from") and request.get("date_from") == memory.get("date_from")
            and request.get("date_to") == memory.get("date_to")):
        return {"metric":memory["last_metric"],"entity":"store","date_from":request["date_from"],
                "date_to":request["date_to"],"source_question_id":previous.get("id")}
    if request.get("product_keys") and request.get("product_keys") == memory.get("shown_product_keys"):
        used = {"shown_product_keys":request["product_keys"], "source_question_id":previous.get("id")}
        for key in ("date_from", "date_to"):
            if request.get(key) and request[key] == memory.get(key): used[key] = request[key]
        return used
    if (request.get('product_keys') and not memory.get('shown_product_keys')
            and request['product_keys']==memory.get('product_keys')):
        used={'product_keys':request['product_keys'],'source_question_id':previous.get('id')}
        for key in ('date_from','date_to'):
            if request.get(key) and request[key]==memory.get(key):used[key]=request[key]
        return used
    if request.get("dataset") == "funnel" and request.get("view") == "contributors":
        used = {"dataset":memory.get("last_dataset"), "analysis":memory.get("last_analysis"),
                "source_question_id":previous.get("id")} if memory.get("last_dataset") == "funnel" else {}
        if request.get("context_dates_inherited"):
            used.update(date_from=request.get("date_from"), date_to=request.get("date_to"))
        return used
    if clarification:
        pending = previous.get("router_request") or {}
        used = {key: pending[key] for key in ("analysis", "metric", "entity", "period_days", "date_from", "date_to") if key in pending}
        used["kind"] = "clarification"
        if request.get("product_keys"): used["product_keys"] = request["product_keys"]
    else:
        product = request.get("product") or {}
        if request.get("product_key") and request.get("product_key") == memory.get("last_product_key"):
            if product.get("match_type") == "memory" or (request.get("metric") == "orders_count" and request.get("entity") == "region" and not product):
                used["product_key"] = request["product_key"]
        from ai_chat.routing.seller_questions import PRODUCT_REQUIRED
        import re
        explicit_period = bool(re.search(r"за (?:последни[ех] )?(?:неделю|месяц|\d+ д(?:ня|ней))", question.lower()))
        inherited_dates = request.get("metric") == "orders_count" or (
            request.get("metric") in PRODUCT_REQUIRED and product.get("match_type") == "memory" and not explicit_period)
        for key in ("date_from", "date_to"):
            if inherited_dates and request.get(key) and request[key] == memory.get(key):
                used[key] = request[key]
        import re
        from ai_chat.routing.seller_questions import BY_METRIC
        if memory.get("last_metric") in {"orders_count", *BY_METRIC} and re.fullmatch(r"а?\s*за .+", question.lower().strip().rstrip("?!.")):
            for key, source in (("analysis", "last_analysis"), ("metric", "last_metric"), ("entity", "last_scope")):
                if request.get(key) == memory.get(source):
                    used[key] = request[key]
    if used:
        used["source_question_id"] = previous.get("id")
    return used


def update_journal_question(journal_id, **payload):
    from core.logger import logger
    for attempt in range(2):
        try:
            rows = supabase.table("system_ai_questions").update(payload).eq("id", journal_id).execute().data
            if rows:
                return True
        except Exception:
            pass
    logger.error("Dialogue journal update failed for id=%s", journal_id)
    return False


async def send_journal_reply(update, journal_id, answer, *, request, result, status, error_message=None, memory_used=None, reply_markup=None):
    message_target = getattr(update,"effective_message",None) or update.message
    from telegram_bot.text_formatting import prepare_text, message_chunks
    spans = []
    if '<b>' in answer:
        from ai_chat.answer_builder.resolver import resolve_answer_rule
        rule = resolve_answer_rule(supabase=supabase,
            question_type=request.get('question_type','simple'),
            language=request.get('language','ru'),request=request,result=result or {})
        answer, spans = prepare_text(answer, rule)
    if not update_journal_question(journal_id, router_request=request, result=result, status=status,
            error_message=error_message, answer_text=answer, memory_used=memory_used or {}, delivery_status="pending"):
        await message_target.reply_text("Не удалось сохранить ответ в журнал. Попробуй позже.")
        return
    sent = []
    try:
        for chunk, entities in message_chunks(answer, spans, TELEGRAM_MESSAGE_LIMIT):
            formatting = {'entities':entities} if entities else {}
            if reply_markup is None:
                message = await message_target.reply_text(chunk, **formatting)
            else:
                message = await message_target.reply_text(chunk, reply_markup=reply_markup, **formatting)
            accepted_text = getattr(message, "text", None)
            sent.append(accepted_text if isinstance(accepted_text, str) else chunk)
    except Exception as error:
        log_ai_error(question=message_target.text or "", request=request, error=error)
        from telegram.error import TimedOut, NetworkError, BadRequest
        uncertain = isinstance(error, TimedOut) or (isinstance(error, NetworkError)
            and not isinstance(error, BadRequest) and "ConnectError" not in str(error))
        update_journal_question(journal_id, answer_text=answer if uncertain else "".join(sent) or None,
            delivery_status="unknown" if uncertain else "partial" if sent else "failed", status="error",
            error_message="Telegram delivery failed: " + type(error).__name__)
        return
    update_journal_question(journal_id, answer_text="".join(sent), delivery_status="sent")



def log_ai_error(question: str, request: dict | None, error: Exception) -> None:
    try:
        supabase.table("system_ai_errors").insert(
            {
                "user_question": question,
                "router_request": request,
                "error_message": str(error),
                "traceback": traceback.format_exc(),
                "source": "telegram",
                "status": "new",
            }
        ).execute()
    except Exception:
        # Never let error logging break the Telegram reply flow.
        pass


# Log AI question with request/result/status/error_message for analytics
def log_ai_question(question: str, request: dict | None, result: dict | None,
                    status: str, error_message: str | None = None, *,
                    answer_text=None, memory_used=None, delivery_status=None):
    from core.logger import logger
    try:
        rows = supabase.table("system_ai_questions").insert({
            "user_question": question, "router_request": request, "result": result,
            "status": status, "error_message": error_message, "source": "telegram",
            "review_status": "new", "answer_text": answer_text,
            "memory_used": memory_used, "delivery_status": delivery_status,
        }).execute().data or []
        return rows[0]["id"] if rows else None
    except Exception:
        logger.error("Dialogue journal insert failed")
        return None

async def send_long_message(update: Update, text: str) -> None:
    if len(text) <= TELEGRAM_MESSAGE_LIMIT:
        await update.message.reply_text(text)
        return

    for start_index in range(0, len(text), TELEGRAM_MESSAGE_LIMIT):
        chunk = text[start_index : start_index + TELEGRAM_MESSAGE_LIMIT]
        await update.message.reply_text(chunk)


async def handle_stock_followup(update, context):
    from telegram_bot.stock_followups import load_context, keyboard, LABELS, formatted, card_rows, card_caption, card_keyboard
    from ai_chat.internal_tools.get_stocks import get_stocks
    from ai_chat.internal_tools.get_orders import get_orders
    from ai_chat.answer_builder.stock_followups import build_followup_answer
    from telegram import InputMediaPhoto
    from telegram.error import BadRequest
    import asyncio
    query=update.callback_query
    actor=update.effective_user.id
    chat=update.effective_chat.id
    parts=(query.data or '').split(':')
    if len(parts) not in (3,4) or parts[2] not in {*LABELS,'page','noop'}:
        await query.answer('Неизвестный вопрос.');return
    token,action=parts[1:3]
    current=resolve_active_telegram_context(telegram_user_id=actor,telegram_chat_id=chat)
    saved=load_context(token,actor,chat,current)
    if not saved:
        await query.answer('Контекст устарел или магазин изменился. Задайте вопрос заново.',show_alert=True);return
    result=saved['result']
    index=None
    if len(parts)==4:
        try:index=int(parts[3])
        except ValueError:index=-1
        if not 0<=index<len(card_rows(result)):
            await query.answer('Товар не найден.');return
    if action=='noop':
        await query.answer('Стрелки переключают товары, кнопки ниже уточняют показанный товар.');return
    if action=='page' and index is None:
        await query.answer('Не указан товар.');return
    await query.answer('Переключаю товар…' if action=='page' else 'Смотрю данные…')
    try:
        if action=='page':
            row=card_rows(result)[index]
            caption=card_caption(result,index)
            markup=card_keyboard(token,result,index)
            if row.get('main_photo_url'):
                try:
                    await query.edit_message_media(InputMediaPhoto(row['main_photo_url'],caption=caption,parse_mode='HTML'),reply_markup=markup)
                except BadRequest as error:
                    if 'not modified' not in str(error).lower():
                        await query.message.reply_text('Фото не загрузилось. Попробуйте ещё раз.')
            elif query.message.photo:
                await query.message.reply_text(caption,parse_mode='HTML',reply_markup=markup)
            else:
                await query.edit_message_text(caption,parse_mode='HTML',reply_markup=markup)
            return
        selected=result if index is None else {**result,'rows':[card_rows(result)[index]]}
        facts=[]
        req=saved['request']
        for row in selected['rows']:
            if action=='sizes':
                data=await asyncio.to_thread(get_stocks,user_id=req['user_id'],shop_id=req['shop_id'],
                    marketplace=req.get('marketplace','wb'),product_key=row['product_key'],
                    as_of=selected['snapshot_date'],level='variant',supabase=supabase)
                facts.extend({**item,'quantity':item['total_quantity']} for item in data['products'])
            elif action=='sales':
                data=await asyncio.to_thread(get_orders,user_id=req['user_id'],shop_id=req['shop_id'],
                    marketplace=req.get('marketplace','wb'),product_key=row['product_key'],
                    start_date=selected['date_from'],end_date=selected['date_to'],supabase=supabase)
                facts.extend(data['products'])
        answer=build_followup_answer(action,selected,facts)
        markup=keyboard(token) if index is None else card_keyboard(token,result,index)
        await query.message.reply_text(formatted(answer,selected),parse_mode='HTML',reply_markup=markup)
    except Exception:
        await query.message.reply_text('Не удалось получить детализацию. Попробуйте ещё раз.')
