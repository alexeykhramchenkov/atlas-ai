Актуальные контракты get_* (тест, 16 октября 2026): project_docs/GET_CONTRACTS.md.
Ниже сохранена история предыдущих контрактов и этапов миграции.

CONTRACTS.md

Обновление get_funnel — 16 октября 2026, только тест

get_funnel(user_id, shop_id, marketplace="wb", product_key=None,
           period_days=None, start_date=None, end_date=None, *, supabase=None)

Период: period_days ИЛИ обе даты включительно. period_days — последние
завершённые дни по Москве (1–365). product_key=None — весь магазин.
Возвращает start_date, end_date, open_count, cart_count, order_count,
buyout_count, cancel_count, products. В products: product_key, title и те же
пять сумм по товару. Без status, complete и latest_only.
Источник: metrics_funnel_daily; названия: normalized_products. Все чтения
ограничены tenant и загружаются постранично без обрезания.
Суммируются имеющиеся факты за запрошенный период без сдвига дат.
Пустая выборка — FunnelDataUnavailableError, а не выдуманные нули.
Качество покрытия — отдельная задача, в пользовательский ответ не добавляется.
Executor передаёт products в rank(rows=products, metric="cart_count",
direction="desc", limit=1). Даты rank не принимает; равные места сохраняются.
Сравнение вызывает get_funnel отдельно для каждого периода. Конверсии
остаются в Analysis/Metric; дневные проценты не суммируются.
Старые потребители делегируют чтение get_funnel. Формулировки находятся
в system_ai_answer_rules тестовой базы; Answer Builder не расширялся.

Главный принцип

Каждый слой системы имеет фиксированный вход и выход.

Запрещено менять контракт без обновления CONTRACTS.md.

⸻

1. Router Contract

Router получает вопрос пользователя.

Router сначала применяет детерминированные правила. Если вопрос аналитический,
но правила не смогли построить запрос, допускается LLM fallback со строгой JSON
Schema. После LLM обязательны enum/schema validation и добавление tenant context
из системы; LLM не имеет права задавать user_id, shop_id или marketplace.

Вход:

Почему упали заказы?

Выход:

{
  "analysis": "explain_change",
  "metric": "orders",
  "scope": "store",
  "entity": null,
  "period_days": 30,
  "answer_scope": "single",
  "limit": 1,
  "user_id": 1,
  "shop_id": 1,
  "marketplace": "wb",
  "language": "ru"
}

Обязательные поля:

analysis
metric
scope
period_days
user_id
shop_id
marketplace
language

⸻

Entity Contract

Поддерживаемые entity:

store
product
variant
ad
warehouse
keyword
region

Примеры:

Почему упали заказы?
→ scope=store

Почему упали заказы у Ангелов?
→ scope=product

В какой регион чаще всего заказывают?
→ entity=region, scope=store

⸻
⸻

2. Executor Contract

Executor получает Router Request.

Вход:

{
  "analysis": "explain_change",
  "metric": "orders"
}

Выход:

{
  "analysis": "explain_change",
  "status": "success",
  "result": {}
}

Executor ничего не считает.

Executor только вызывает нужный Analysis.

⸻

3. Analysis Contract

Analysis получает Request.

Вход:

{
  "analysis": "explain_change",
  "metric": "orders",
  "scope": "store",
  "period_days": 30
}

Выход:

{
  "analysis": "explain_change",
  "metric": "orders",
  "status": "success",
  "result": {}
}

Analysis не ходит напрямую в Supabase.

Analysis работает только через Metric Adapter.

⸻

4. Metric Adapter Contract

Metric Adapter предоставляет единый интерфейс ко всем метрикам.

Поддерживаемые режимы:

value
compare
state
history
forecast

⸻

Derived Metric Contract

Derived Metric вычисляется из базовых метрик.

Derived Metrics не хранятся напрямую в Supabase.

Примеры:

stock_health
traffic_health
rating_health
risk_orders_share
availability_score

Analysis Engine может использовать Derived Metrics так же, как обычные метрики.

⸻
⸻

4.1 Compare Contract

Вход:

{
  "metric": "views",
  "view": "compare",
  "scope": "store",
  "period_days": 30
}

Выход:

{
  "metric": "views",
  "view": "compare",
  "current": 15765,
  "previous": 26107,
  "change_abs": -10342,
  "change_pct": -39.61,
  "period_days": 30
}

⸻

4.2 Value Contract

Выход:

{
  "metric": "profit",
  "view": "value",
  "value": 245000
}

⸻

4.3 State Contract

Выход:

{
  "metric": "stock",
  "view": "state",
  "status": "ok",
  "value": 120
}

⸻

4.4 History Contract

Выход:

{
  "metric": "orders",
  "view": "history",
  "points": [
    {
      "date": "2026-06-01",
      "value": 15
    }
  ]
}

⸻

5. Internal Tool Contract

Любой internal tool обязан вернуть список словарей.

Выход:

[
  {
    "snapshot_date": "2026-06-15",
    "orders_count": 25
  }
]

Internal Tools знают:

таблицы
SQL
Supabase

⸻

6. Analysis Result Contract

Любой analysis возвращает:

{
  "analysis": "best",
  "status": "success",
  "result": {}
}

⸻

Analysis Contract Rule

Допустимые analysis определяются только в ANALYSIS_REGISTRY.md.

Запрещено создавать новый analysis без обновления ANALYSIS_REGISTRY.md.

⸻
⸻

7. Explain Change Contract

Вход:

{
  "analysis": "explain_change",
  "metric": "orders",
  "scope": "store"
}

Выход:

{
  "analysis": "explain_change",
  "metric": "orders",
  "main_cause": "conversion",
  "confidence": 0.84,
  "evidence": [
    {
      "metric": "conversion",
      "change_pct": -25
    }
  ]
}

⸻

8. Best Contract

Выход:

{
  "analysis": "best",
  "entity": "product",
  "items": [
    {
      "product_key": "wb_439996132",
      "score": 92.4
    }
  ]
}

⸻

9. Answer Builder Contract

Вход:

{
  "analysis": "explain_change",
  "result": {}
}

Выход:

Заказы снизились на 21%.
Основная причина:
Конверсия снизилась на 18%.
Дополнительно:
• Просмотры -5%
• Остатки без изменений

Answer Builder не достаёт данные.

LLM Answer Interpreter Contract

LLM может интерпретировать только готовый Analysis Result. Он не обращается к
Supabase, не вычисляет бизнес-метрики и не добавляет отсутствующие числа. При
ошибке LLM Answer Builder возвращает детерминированный ответ или raw JSON fallback.

⸻

10. Memory Contract

Вход:

{
  "question": "...",
  "request": {},
  "result": {}
}

Выход:

{
  "last_analysis": "explain_change",
  "last_metric": "orders",
  "last_scope": "store"
}

⸻

Contract Stability Rule

После запуска MVP запрещено менять:

- Router Contract
- Metric Adapter Contract
- Analysis Result Contract

без обновления CONTRACTS.md и отдельного архитектурного решения.

⸻
⸻

Главное правило

Любой новый код обязан использовать существующие контракты.

Если нужен новый контракт:

1. Обновить CONTRACTS.md
2. Получить подтверждение
3. Только потом менять код

⸻

11. Data Pipeline Tenant Contract

Каждый production job слоёв normalization, snapshots и metrics обязан получать:

```json
{
  "user_id": 1,
  "shop_id": 1,
  "marketplace": "wb"
}
```

Все coverage-запросы, чтение source-таблиц и запись target-таблиц выполняются в
границах этого tenant context.

Запрещено:

- запускать production job без `user_id` или `shop_id`;
- читать все строки marketplace и фильтровать магазин только в Python;
- использовать unique/upsert key бизнес-данных без tenant-полей, если таблица
  принадлежит конкретному магазину.

Для `normalized_orders` канонический upsert key:

```text
user_id,shop_id,marketplace,srid
```


## Stock depletion MVP 2026-10-12

`stocks / risk_check / product / days_left`: deterministic routing of the Russian stock-depletion question. Tenant context is required. Data access reads the latest stock snapshot and all pages of order metrics from the preceding 7 complete calendar days, excluding the stock date. Analysis receives facts from the existing stocks internal tool, ranks available quantity divided by daily order rate, and returns only products with <=7 days remaining (default top 5). Zero demand and missing stock values do not imply risk. No order rows or fewer than 7 distinct dates suppress the forecast. This is a conservative availability check; metric-date presence alone does not prove successful source ingestion. Archived stock snapshots are explicitly labeled. Product titles use tenant-filtered data. No raw JSON or LLM arithmetic in the answer.

Statuses: `ok`, `no_data`, `no_orders`, `incomplete`. Result includes snapshot_date, date_from, date_to, period_days, checked_products, risk_count, rows, stale. Future supplies and returns are excluded. This MVP does not establish 250,000-product performance or data freshness; live database and source coverage must be checked before recording.

Live validation 2026-10-12: current stocks use POST https://seller-analytics-api.wildberries.ru/api/analytics/v1/stocks-report/wb-warehouses with Personal/Service Analytics token, offset pagination (250000 warehouse/size rows per page, not products) and 20s interval. Current chrtId identifies the stock variant. Stock risk subtracts cancelled_orders_count from orders_count. Tested in actual Telegram against a fresh 19-product stock report and complete 7-day order metrics. Refresh is manual.

Stock followups: callback stock:<opaque id>:<priority|sizes|sales> references a local stored original request/result (24h TTL). Actor, chat and active tenant must match. All details are limited to original result product keys and original snapshot/period. Supabase access stays in internal_tools/get_stocks.py; formatting in answer_builder/stock_followups.py. Sizes sum recorded warehouse rows and use tenant-filtered variant names; omitted sizes are not inferred as zero. Sales button reports gross orders, cancellations, net orders and days, without equating orders to buyouts. Followup keyboards retain the same immutable context.

Product cards: positive-stock products first for display, original ranking retained for replenishment. New callbacks stock:<token>:page:<index>, noop:<index>, sizes:<index>, sales:<index> validate the index and inherited actor/chat/tenant guards. Photo and caption edit in the same message; per-product details use only selected product_key. Legacy list callbacks stay supported. Missing/unfetchable photos fall back to a text card; failed page media edits keep the original card unchanged and report the load failure.

Test-only WB connection (2026-10-13): existing connection:planned:wb callback starts a private, actor/chat-bound 10-minute credential intake. Credential messages are intercepted before Router and AI question/error logging. Validation uses seller-info and Content/Analytics/Statistics ping; tokens must be read-only, unexpired, match the API seller ID, and include the three scopes. Existing integration repository stores Fernet ciphertext in api_token and encrypted_api_token, fingerprint only in token_fingerprint; existing user/shop/connection/context fields are reused. The sync connection resolver decrypts in memory after exact owner/shop/marketplace checks and fails closed on missing/invalid encrypted credentials; its returned api_token argument remains unchanged. No analytical request/result or database schema changes. No plaintext fallback for WB sync jobs. New connections have no copied analytical data; scheduler is not started by onboarding. /start cancels pending intake. Credential messages are deleted best-effort and deletion failure is reported.

Test reel chain 2026-10-13 (approved): existing metric_value/best analyses use net_orders (orders minus cancellations). Store weekly question resets product context; best inherits date_from/date_to and selects one positive leader; destination ranking inherits the leader product_key and exact dates. Memory adds date_from/date_to and isolates Telegram actor/chat and tenant before lookup. Regional counts read tenant/product-bound normalized_orders, exclude cancellations and deduplicate srid. All reads paginated; incomplete seven-day metric coverage suppresses answers. Existing request fields, analysis types and database schema retained. No localization. The currently approved copied API slice is 2026-10-06 through2026-10-12 for test shop1; direct fresh-load attempt was rejected and not executed.

Friendly answer rules, test-only 2026-10-14 (approved): existing system_ai_answer_rules gains three records using compact_text. Its title_template is the message body; existing field label/path/formatter entries supply named placeholders. Existing fields[].template adds item_fields(name/path/formatter), item_template, complete_intro, partial_intro, equal_summary, ranked_summary, empty_text and status_text. Presentation placeholders period, orders_word, times_word, items, region_count, region_intro, summary provide Russian display formatting. Actual business results, Router/Executor/Analysis contracts and database schema are unchanged. Net-orders answers resolve these table rules before rendering; no inline success wording remains in answer.py. Missing rule fails with a configuration message. Previous five records preserved; before/apply/rollback stored in setup/friendly-answer-release.

Test dialogue boundaries 2026-10-14 (approved): existing memory reads only the immediately preceding journal turn in the same Telegram actor/chat, checks tenant and marketplace, and expires it after ten minutes. No older successful turn is recovered across a different topic, failed request, incomplete result, /start, or shop selection. Reset actions reuse journal status blocked with error_message dialogue_reset. Existing memory keys and analytic request/result fields are retained. Explicit periods replace inherited dates; explicit product selection never falls back to the previous product on a failed lookup. Generic dimension words or an initial “а” no longer imply a product reference. For the existing net_orders destination question without a product, Router returns existing is_valid_question=false/error_code=unclear_question/message fields; the existing journal stores that request as invalid_question. A single next product-only reply (exact catalog name/SKU/key/article) can complete that request within ten minutes and the same actor/chat/tenant. A new question cancels it. Clarification wording uses the existing top_product_stock answer template and a test-only system_ai_answer_rules record. Incomplete status is rendered before checking empty rows; answer wording uses the displayed period. No new table, column, analysis type or persistence format. Journal audit found formatted response text is not persisted; success is recorded before answer formatting, and incomplete/no_data are currently stored as success plus result.status. These journal behaviours were inspected and remain unchanged.

Test dialogue journal 2026-10-14 (approved journal-only extension): system_ai_questions adds nullable answer_text(text), memory_used(jsonb), delivery_status(text). Historical rows remain NULL; no old response or memory is reconstructed. Analytics request/result contracts are unchanged. Existing Telegram handler creates one record before routing, updates that same ID after rendering and sending, retains raw user text, and routes all normal text replies (including invalid, blocked, missing-context and technical-error replies) through the journal. Current pending ID is excluded from memory lookup; an older pending/failed turn remains a context barrier. memory_used is {} when no context was used; otherwise it records selected dates/product or clarification fields plus source_question_id, without changing router_request/result. Explicit product/period values are not reported as memory. A successful send saves Telegram's returned message text; long responses are joined in original chunk order. delivery_status: pending, sent, failed, partial, unknown. Partial failures preserve confirmed sent text; ambiguous network/timeouts retain prepared text with unknown, never claim confirmed delivery. Incomplete/no_product results use existing blocked journal status; formatted errors do not create a premature success row. Existing review fields remain available and new. API-key intake stays excluded from the journal. Journal failures are reported to the application logger; without a successful initial journal insert the analytics pipeline is not run. /start main-menu replies are journaled and remain dialogue_reset barriers. No production access or changes.

## Approved get_orders and rank contracts — 2026-10-16

The following separates approved target contracts from rollout state. Earlier historical notes remain for reference; this section governs the approved target for these two functions.

### get_orders — approved target, NOT migrated in this release

Input: server-owned user_id, shop_id, marketplace and database connection; optional product_key; either period_days or BOTH start_date/end_date, never both modes. period_days selects the last N completed Moscow calendar days, not the last available database day. Dates are inclusive. No latest_only flag in the target input.

Output: {start_date, end_date, orders_count, cancelled_orders_count, products:[{product_key,title,orders_count,cancelled_orders_count}]}. Orders include cancellations. No status or complete fields in this target output. Data-access errors/incomplete coverage must not be reported as complete-period totals. This release documents, but does not migrate, the current list-returning get_orders API or its callers.

### rank — approved and implemented pure Analysis function

Input: {rows, metric, direction, limit}. No dates, period or database connection. Metric identifies a numeric field already present in every row. direction is asc or desc. limit is a positive integer denoting the number of distinct rank positions; ties share the same rank and are all included at the cutoff (dense ranking). Missing, boolean, invalid and non-finite metric values raise an error; they are not treated as zero. Rows are never mutated. Equal-value rows retain input order.

Output: {rows:[{...original_row,rank}]}. No status, complete or date fields. Empty input returns {rows:[]}. Period context stays with get_orders/Executor and is available for rendering separately.

Rollout in this release: the existing calculate_chain product-order leader path now delegates ranking to rank, rather than duplicating sorting. It retains its existing external result envelope and period completeness checks. Router/Executor still dispatch that legacy path via analysis=best; global migration to analysis=rank and LLM tool selection is NOT included. This is an incremental integration, not completion of the target architecture. No database rule changes or production changes.

## get_orders migration completed in test — 2026-10-16

This section supersedes the earlier release's “NOT migrated” rollout note for get_orders. The approved data contract is unchanged:

- get_orders(user_id, shop_id, marketplace='wb', product_key=None, period_days=None, start_date=None, end_date=None, *, supabase=None).
- Exactly one period selector: period_days (1..365, last completed Europe/Moscow days) OR both inclusive ISO dates. Unfinished days, mixed selectors and reversed dates are rejected. No latest_only.
- Exact success output: {start_date,end_date,orders_count,cancelled_orders_count,products:[{product_key,title,orders_count,cancelled_orders_count}]}. No status or complete. Names can be null when catalog data is absent.
- All orders include cancellations; cancellation counts are separate. Product names are fetched only for selected ordered keys in the same tenant, within get_orders; no standalone catalog collector call.
- Both reads are paginated and tenant scoped. Missing daily metric coverage raises IncompleteOrdersError instead of returning partial totals; invalid/missing counts are not coerced to zero. Daily coverage is a conservative check, not proof of successful upstream ingestion for every product. The error does not imply database unavailability.
- Executor orchestrates get_orders -> pure rank for order rankings. Dates stay in its existing analytics result envelope; rank still accepts only rows,metric,direction,limit and returns only rows. Existing outer journal/rendering status fields are not part of the get_orders contract.
- Existing Router dispatch best/worst labels remain for compatibility; this release does not activate OpenAI's autonomous tool selection. No risk_check/overview changes.
- get_chain_inputs and the duplicate calculate_chain aggregation/leader implementation were removed. Store totals consume get_orders directly. Regions use get_orders for period facts plus the existing get_seller_facts order_events source, with deduplication/region calculation in the existing ranked Analysis. No new collector function was introduced. get_seller_facts remains pending its separate approved migration.
- Existing comparison/contributor consumers in metric_adapter consume the new totals/products object and explicit previous-period dates.
- Answer formatting stays in test rule 7, using the existing compact_text item template to render all tied leaders; no inline success text was added to Python. The new contract has no standalone article field, so the obsolete article placeholder was removed.

Backups, rule before/after snapshots and verification evidence: setup/get-orders-contract-release. Production files and production database are out of scope.


Обновление get_stocks — 16 октября 2026, только тест

get_stocks(user_id, shop_id, marketplace="wb", product_key=None,
           variant_key=None, warehouse_key=None, as_of=None, level="product", *, supabase=None)

Возвращает as_of, warehouse_quantity, to_customer_quantity,
from_customer_quantity, total_quantity, products. Каждая строка products
содержит product_key, title и те же четыре количества.
level="variant" добавляет variant_key, size_name, warehouse_key, warehouse_name.
Общий остаток = склад + к покупателю + от покупателя.
as_of=None выбирает последний снимок магазина, не отдельного товара.
Нет записи — StockDataUnavailableError, а не нулевой остаток.
Источник product: metrics_stocks_daily; детализация: snapshots_stocks_variants_daily.
Доступ ограничен user_id, shop_id, marketplace. status/complete отсутствуют.

Executor передаёт products в существующий Analysis rank:
rank(rows=products, metric="total_quantity", direction="desc", limit=1).
Даты rank не принимает. Равные места сохраняются.
Старые потребители остатков делегируют чтение get_stocks;
get_stock_risk_inputs и get_followup_facts удалены.
Внешний ответ Executor пока сохраняет прежний контракт совместимости.
Формулировки — system_ai_answer_rules тестовой базы.

## Buyer questions / get_followups — test, 2026-10-17

Approved buyer-question contract and integration are documented in
project_docs/GET_CONTRACTS.md, section get_followups. Returns original questions,
optional product/status/date filters; no implicit date period. Existing Router /
Executor / Analysis / table-based Answer Builder layers retained. Semantic topic
labels from LLM; membership validation, counts and rank remain deterministic.
No other get_* contracts or production changes.

## Persisted text topics — approved test change, 2026-10-17

User explicitly approved include_topics in get_reviews/get_followups and an optional
period in get_reviews (omitted means all loaded reviews). Exact contracts and
status semantics are in GET_CONTRACTS.md, section «Сохранённый разбор текстов».
Three approved new tables: text_topics, text_analyses, text_analysis_topics.
Registered runner reuses existing metric-worker job/state/log protocol.
Original normalized source tables remain untouched. Data access stays in get_* /
db.text_analysis_store, LLM annotation in Analysis, orchestration in the background
runner; formatting stays in system_ai_answer_rules. No production migration.

## get_orders variant level approved and implemented (test, 2026-10-17)
Optional level="product" (default, prior contract unchanged) or "variant".
Variant level reads metrics_orders_variants_daily with the existing tenant and period guards.
It returns variants instead of products; each row adds variant_key and size_name to the same count/amount facts.
Executor passes variants to the existing rank. The common LLM context resolver preserves a single current product and exact dates for dimensional follow-ups; explicit selections override memory.

## Telegram clarification presentation (test, 2026-10-17)
The existing Router clarification protocol emits exactly two short option labels (1..24 characters).
Telegram renders the stored options as inline buttons with callback_data clarify:<journal_id>:<index>.
A callback is valid only for the latest delivered pending clarification in the existing actor/chat/tenant/TTL boundary and the same active connection.
It applies validate_clarification_updates directly, reuses the ordinary execution and answer pipeline, and journals the selected label and exact answer. No extra LLM choice call; typed replies still use the existing resume flow.
No new database tables, analytical tools or analytical contracts.

## Supersedes legacy stock risk handler (test, 2026-10-17)
The active risk_check analysis and hardcoded risk answer builder are removed. Historical source/tests are retained only under setup/retired-risk-check for rollback.
Replenishment uses stocks/days_left/rank with existing get_stocks + get_orders, the existing days_left calculation, Analysis.filter(days_left <= 7), then rank(days_left, asc).
Default pace: last 30 completed Moscow days. An explicitly requested period overrides the default. An unqualified replenishment request covers the store; a semantic reference to the last displayed list applies existing product_keys.
The existing bounded LLM clarification protocol accepts days_left and preserves this selection. Zero demand yields no finite prediction; unknown days are not ranked as zero. Answer wording is stored in system_ai_answer_rules, not Python.
No get_* or Analysis function contracts changed.

## Empty-result selection memory fix (test, 2026-10-17)
No new fields/contracts. Existing shown_product_keys remains the actual displayed rows; existing memory.product_keys retains the immediately previous request's input selection.
Semantic references choose displayed rows when present, otherwise the bounded input selection after an empty result. The existing selection=shown_products update resolves to that input selection only as a fallback; explicit store selection clears it.
The existing one-turn, 10-minute, actor/chat/tenant boundary is unchanged. No backwards history scan or extended sticky memory. A failed semantic resolution does not silently widen the scope to the store.
