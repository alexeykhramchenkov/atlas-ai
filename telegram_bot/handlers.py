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
from db.client import supabase
from telegram_bot.keyboards import build_shopify_connection_keyboard

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

    shopify_connection = get_shopify_connection(telegram_user_id)
    if shopify_connection:
        text = SHOPIFY_NOT_SYNCED_MESSAGE
        shopify_connected = True
    else:
        text = SHOPIFY_CONNECT_MESSAGE
        shopify_connected = False

    await update.message.reply_text(
        text,
        reply_markup=build_shopify_connection_keyboard(
            telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_chat_id,
            shopify_connected=shopify_connected,
        ),
    )


async def handle_integration_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
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
        .select("active_user_id,active_shop_id,active_marketplace")
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
    }


def is_shopify_sync_ready(*, user_id: int, shop_id: int) -> bool:
    return False


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    question = update.message.text.strip()

    if not question:
        await update.message.reply_text("Напиши вопрос о магазине.")
        return

    request_started_at = perf_counter()
    try:
        language = detect_language(question)
        telegram_user_id = update.effective_user.id if update.effective_user else None
        telegram_chat_id = update.effective_chat.id if update.effective_chat else None

        if telegram_user_id is None:
            await update.message.reply_text("Не удалось определить Telegram пользователя.")
            return

        active_context = resolve_active_telegram_context(
            telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_chat_id,
        )

        if not active_context:
            await update.message.reply_text(
                "Не найден активный магазин для этого Telegram пользователя."
            )
            return

        if active_context["marketplace"] == "shopify" and not is_shopify_sync_ready(
            user_id=active_context["user_id"],
            shop_id=active_context["shop_id"],
        ):
            blocked_request = {
                "marketplace": "shopify",
                "user_id": active_context["user_id"],
                "shop_id": active_context["shop_id"],
                "telegram_user_id": active_context["telegram_user_id"],
                "telegram_chat_id": active_context["telegram_chat_id"],
                "is_valid_question": True,
                "language": language,
            }
            log_ai_question(
                question=question,
                request=blocked_request,
                result=None,
                status="blocked",
                error_message=SHOPIFY_SYNC_NOT_READY_ERROR,
            )
            await update.message.reply_text(SHOPIFY_NOT_SYNCED_MESSAGE)
            return

        router_started_at = perf_counter()
        request_context = {
            **active_context,
            "language": language,
        }
        memory = resolve_last_product_context(
            telegram_user_id=request_context["telegram_user_id"],
            user_id=request_context["user_id"],
            shop_id=request_context["shop_id"],
            marketplace=request_context["marketplace"],
            supabase=supabase,
        )
        request = route(
            question,
            memory=memory,
            request_context=request_context,
        )
        log_timing(
            stage="router",
            started_at=router_started_at,
            source="telegram",
            language=language,
        )

        if not request.get("is_valid_question", True):
            log_ai_question(
                question=question,
                request=request,
                result=None,
                status="invalid_question",
                error_message=request.get("message") or request.get("error_code"),
            )

            await update.message.reply_text(
                "Я не понял вопрос. Попробуй спросить, например:\n\n"
                "У каких товаров больше всего заказов?\n"
                "Какой товар дал больше всего выручки?\n"
                "У каких товаров меньше всего прибыли?"
            )
            return

        request.setdefault("telegram_user_id", request_context["telegram_user_id"])
        request.setdefault("telegram_chat_id", request_context["telegram_chat_id"])
        request.setdefault("user_id", request_context["user_id"])
        request.setdefault("shop_id", request_context["shop_id"])
        request.setdefault("marketplace", request_context["marketplace"])
        request["language"] = language

        executor_started_at = perf_counter()
        result = executor.execute(request)
        log_timing(
            stage="executor",
            started_at=executor_started_at,
            analysis=request.get("analysis"),
            dataset=request.get("dataset"),
            scope=request.get("scope"),
        )
        log_ai_question(
            question=question,
            request=request,
            result=result,
            status="success",
        )

        answer_started_at = perf_counter()
        answer = build_answer(
            question=question,
            request=request,
            result=result,
            supabase=supabase,
            language=language,
        )
        log_timing(
            stage="answer_builder",
            started_at=answer_started_at,
            analysis=request.get("analysis"),
            language=language,
        )

    except Exception as error:
        request_for_log = request if "request" in locals() else None

        log_ai_error(
            question=question,
            request=request_for_log,
            error=error,
        )
        log_ai_question(
            question=question,
            request=request_for_log,
            result=None,
            status="error",
            error_message=str(error),
        )

        answer = f"Ошибка:\n{error}"

    log_timing(
        stage="total_request",
        started_at=request_started_at,
        source="telegram",
        language=language if "language" in locals() else None,
    )
    await send_long_message(update, answer)



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
def log_ai_question(
    question: str,
    request: dict | None,
    result: dict | None,
    status: str,
    error_message: str | None = None,
) -> None:
    try:
        supabase.table("system_ai_questions").insert(
            {
                "user_question": question,
                "router_request": request,
                "result": result,
                "status": status,
                "error_message": error_message,
                "source": "telegram",
                "review_status": "new",
            }
        ).execute()
    except Exception:
        # Never let question logging break the Telegram reply flow.
        pass

async def send_long_message(update: Update, text: str) -> None:
    if len(text) <= TELEGRAM_MESSAGE_LIMIT:
        await update.message.reply_text(text)
        return

    for start_index in range(0, len(text), TELEGRAM_MESSAGE_LIMIT):
        chunk = text[start_index : start_index + TELEGRAM_MESSAGE_LIMIT]
        await update.message.reply_text(chunk)
