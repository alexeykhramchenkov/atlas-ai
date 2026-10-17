# Контракты Internal Tools — тестовая версия

Актуализировано 16 октября 2026. Рабочая версия и рабочая БД не изменялись.

## Единая логика

Router определяет тип данных, товар, период и анализ. Executor вызывает соответствующий get_* и существующий Analysis. Answer Builder оформляет результат по system_ai_answer_rules. Свободный выбор инструментов моделью этим выпуском не включается.

Все инструменты получают `user_id`, `shop_id`, `marketplace="wb"`, необязательный `product_key` и внутренний keyword-only `supabase`. Контекст магазина задаёт сервер, а не пользовательская строка. `get_metric` дополнительно требует `metric`.

Период задаётся либо `period_days` (1–365 последних завершённых дней по Москве), либо обеими датами `start_date`, `end_date` включительно. Дневные снимки фильтруются по дате; отзывы — по границам календарных дней Москвы. Запрошенный период не сдвигается к последним доступным данным. `get_orders` сохраняет ранее согласованную проверку наличия дат; новые контракты не добавляют в ответ предупреждений о покрытии.

Внешние get_* не возвращают status/complete/latest_only. Нет записанных фактов — DataUnavailableError или его специализированный подкласс. Измеренный ноль отличается от отсутствующей записи/NULL. Списки загружаются постранично с устойчивой сортировкой. Полностью пустой каталог возвращает пустой список. Оценка полноты загрузок — отдельная задача.

Общие приватные операции в internal_tools/_common.py: проверка контекста/дат, страницы, проверка чисел, сумма аддитивных полей, названия через get_products. Это технические функции внутри существующего слоя, не инструменты для модели и не новые сборщики запросов.

## get_orders — ранее согласованный контракт сохранён

Вход: общий контекст + product_key + период + level="product"|"variant" (по умолчанию "product").
Выход: start_date, end_date, orders_count, cancelled_orders_count, orders_amount, cancelled_orders_amount, products.
В products: product_key, title, orders_count, cancelled_orders_count.
При level="variant" вместо products возвращается variants: те же числовые поля, product_key, title, variant_key, size_name. Источник — metrics_orders_variants_daily; при level="product" источник и ответ прежние.
Источник: metrics_orders_daily. Заказы включают отменённые, отмены показываются отдельно. Нельзя подменять их выкупами.

## get_stocks — ранее согласованный контракт сохранён

Вход: контекст + product_key, variant_key, warehouse_key, as_of, level=product|variant.
Выход: as_of, warehouse_quantity, to_customer_quantity, from_customer_quantity, total_quantity, products.
В products те же количества, product_key/title. Деталь variant добавляет variant_key, size_name, warehouse_key, warehouse_name.
Общий остаток = склад + к покупателю + от покупателя. Это учётный остаток, а не обещание доступности к заказу.
Источник: metrics_stocks_daily или snapshots_stocks_variants_daily. Последняя дата выбирается по магазину, без отдельного старого снимка для каждого товара.

## get_funnel — ранее согласованный контракт сохранён

Вход: контекст + product_key + период.
Выход: start_date, end_date, open_count, cart_count, order_count, buyout_count, cancel_count, products.
В products те же пять сумм, product_key/title.
Источник: metrics_funnel_daily. Значения воронки WB не подменяют статистику get_orders/get_sales.

## get_sales

Вход: контекст + product_key + период.
Выход: start_date, end_date, sales_count, return_count, products.
В products: product_key, title, sales_count, return_count.
Источник: metrics_sales_daily. sales_count — выкупы, return_count — возвраты в выбранном периоде. Возврат может относиться к более раннему выкупу. Отдельного get_refunds нет.

## get_ads

Вход: контекст + product_key, campaign_id, level=campaign|product + период.
Фильтр product_key разрешён только при level=product, иначе ошибка.
Выход: start_date, end_date, level, currency, views, clicks, orders, canceled, add_to_cart, spend, revenue; campaigns ИЛИ products.
Деталь campaigns: ad_id, campaign_id и те же аддитивные поля.
Деталь products: ad_id, campaign_id, product_key, title и те же поля.
Источники: metrics_ads_daily ИЛИ metrics_ads_product_daily, никогда сумма обоих уровней. Разные валюты не суммируются. CPC/CTR/CPO/ROAS не суммируются из дневных процентов, их считает Analysis.
В Executor для рейтинга товаров расходы/заказы нескольких кампаний сначала группируются по product_key в существующем Analysis, затем передаются в rank.

## get_profit

Вход: контекст + product_key + период + view=profit|expenses.
Выход: start_date, end_date, view, соответствующие суммы, products с product_key/title и теми же суммами.

view=profit, источник metrics_financial_daily:
- sales_count, returns_count, net_sales_count;
- sales_amount, returns_amount, net_sales_amount;
- cogs_amount, marketplace_expense_amount;
- commission_amount, logistics_amount, storage_amount, acquiring_amount, deduction_amount;
- gross_profit, net_profit.

view=expenses, источник metrics_realization_daily:
- wb_commission_amount, logistics_amount, storage_amount, acquiring_amount;
- penalty_amount, deduction_amount, acceptance_amount;
- other_income_amount, other_expense_amount, seller_payout;
- total_income_amount, total_expense_amount, gross_margin_before_cost, wb_net_result;
- compensation_amount, reimbursement_amount.

Два источника не склеиваются и не выдаются за эквивалентные виды прибыли. Знаковые корректировки сохраняются, денежные суммы складываются через Decimal. Неизвестное значение остаётся NULL, не превращается в ноль. Дневные маржи не суммируются. Себестоимость не выдумывается. Отдельного get_expenses нет.

## get_reviews

Вход: контекст + product_key + период + rating_min/rating_max (необязательные целые 1–5).
Выход: start_date, end_date, reviews_count, reviews.
В reviews: feedback_id, product_key, title, rating, text, pros, cons, tags, has_photo, has_answer, created_at.
Источник normalized_feedbacks. Дедупликация по feedback_id; противоречащие дубли — ошибка. Имена покупателей и их контактные данные не возвращаются. Средние оценки, темы и рейтинги по числу отзывов относятся к Analysis. Контекст explain_change теперь использует отзывы за последние 30 завершённых дней, а не неограниченную выборку.

## get_prices

Вход: контекст + product_key, variant_key + as_of ИЛИ период. При отсутствии обоих — последний снимок магазина.
Выход снимка: as_of, prices. Выход истории: start_date, end_date, prices.
В prices: snapshot_date, product_key, title, variant_key, size_name, base_price, final_price, discount_percent, currency.
Источник snapshots_prices_daily. Цены разных размеров/дней не усредняются и не суммируются. Противоречащие записи одной даты/варианта — ошибка. Старые даты отдельных товаров не подставляются вместо отсутствия записи на общем снимке. В explain_change неоднозначная цена нескольких размеров остаётся неизвестной.

## get_products

Вход: контекст + product_key ИЛИ keyword-only product_keys (список; для внутренней подстановки названий). Без селектора — весь каталог. Период отсутствует.
Выход: products_count, products.
В products: product_key, title, marketplace_product_id, seller_sku, brand, subject_name, category_name, main_photo_url, created_at.
Источник normalized_products. Пустой список product_keys означает пустой результат. Противоречащие дубли product_key — ошибка. Подсчёт товаров идёт по каталогу, не по товарам с остатками или заказами. Router и enricher используют этот же инструмент с обязательным контекстом магазина.

## get_metric

Вход: контекст + metric + product_key + as_of ИЛИ период. По умолчанию — последний снимок магазина.
Выход снимка: metric, as_of, products. Выход истории: metric, start_date, end_date, products.
В products: product_key, title, snapshot_date, value.
Читает только разрешённые сохранённые колонки из metrics_stocks_daily, metrics_sales_daily, metrics_funnel_daily, metrics_financial_daily. Список METRICS находится в самом инструменте. Произвольные таблицы и выражения запрещены; system_metric_rules содержит правила, а не значения метрик.
Не вычисляет новые метрики и не суммирует дневные проценты. days_left в этих таблицах отсутствует; get_metric(days_left) явно отклоняется, существующий прогноз остаётся в Analysis/Metric. total_stock_value — сохранённая оценка источника; её качество этим выпуском не пересчитывается.

## Analysis и совместимость

rank(rows, metric, direction=desc|asc, limit) → {rows:[...исходная строка, rank]}. Без дат, БД и скрытого запроса фактов. Равные позиции сохраняются. Действующие метки Router best/worst направляются в rank через Executor.

Сравнения, конверсии, отношения, группировка по регионам/товарам и прогнозы остаются в существующих Analysis/Metric. Переход всех анализов на единую публичную схему и свободный tool calling модели — отдельный этап.

get_seller_facts сохраняется как совместимость старых сценариев, делегируя каталог, остатки, воронку, рекламу, выкупы/возвраты, финансы, цены и отзывы соответствующим get_*. Его старые источники событий/дневных заказов и служебные журналы ещё используются старой аналитикой; они не выдаются за новые инструменты модели.

Старые обзорные анализы и денежные метрики заказов требуют отдельной миграции; наличие рабочих get_* не означает, что любой старый Analysis уже переведён на новую схему.


## Подтверждённый ноль рекламы — только тест, 16 октября 2026

Пустые метрики get_ads дают ноль только после явного пустого API-ответа
за каждый день периода и успешных sync/normalization/snapshot/metric в правильном
порядке. Все проверки ограничены магазином. Отсутствующий день, ошибка,
незавершённая обработка и непустой RAW не превращаются в ноль. Контракт прежний.
На текущих данных 2/7 дней подтверждены как нулевые; 30 дней пока не подтверждены.
Символ ₽ и формулировка находятся в таблице правил ответов.

## Funnel period comparison (test, 2026-10-16)

`get_funnel` input/output contract is unchanged. Router selects `analysis=compare`
for funnel dynamics/comparison. Executor calls the same getter for the requested
completed period and the immediately preceding period of equal length, keeping
user/shop/marketplace/product filters identical. Analysis `compare.run` accepts
`current`, `previous`, and `metrics`, and returns per-field current/previous,
absolute change, and percentage change. A zero baseline with nonzero current
produces null percentage; zero against zero produces 0. No database access or
response wording lives in this calculation. Two test `system_ai_answer_rules`
format store and product comparisons; zero-baseline and unchanged wording is
configured in these rules. Generic `change` formatter renders numeric signs.
Verification: 171 tests passed; Telegram journal 124/125 success/sent.

## Funnel attribution follow-up (test, 2026-10-16)

After a successful store funnel comparison, the immediate follow-up asking which
products declined in orders reuses that comparison's dates and funnel dataset.
Existing memory expiry (10 minutes), tenant/chat matching and immediate-previous
turn restriction remain unchanged. Explicit unrelated topics do not enter this
route. Journal memory_used records dataset, prior analysis/scope, dates and source
question ID. No product from older topics is inherited.
Executor obtains two unchanged get_funnel results. Pure Analysis compare_rows
joins product_key across their product arrays, computes signed changes, and uses
rank for negative/positive contributors. Both lists are complete, without top-N
truncation, so gains minus losses reconciles to the store's total change.
Missing product entries in an otherwise returned period contribute zero recorded
orders; unavailable whole periods still follow the existing no-data path.
Response headings, section templates and empty-list text live in the answer rule.

## Generic funnel count attribution (test, 2026-10-16)

The phrase-specific orders decline branch is replaced with constrained semantic
selection inside the existing Router's LLM module. Input is the question and only
bounded prior funnel parameters, without store facts, identity or credentials.
Allowed metrics: open_count/cart_count/order_count/buyout_count/cancel_count;
allowed direction: positive/negative. Model cannot pick tenant, arbitrary tools,
code or numerical facts. Existing Executor and get_funnel twice produce facts;
compare_rows and rank compute/sort changes. Executor selects gains/losses as rows.
Ten table rules (five data labels x two directions) use the same compact template.
Zero baseline growth renders the table-configured 'было 0', never infinity.
No new get_funnel input/output fields. No new layers or source collectors.
Unrelated questions return to the existing Router; explicit periods override
memory. Memory expires at 10 minutes and only the immediate successful preceding
turn can provide it. Consecutive funnel follow-ups retain the original dates.
The test .env now uses the existing authorized OpenAI key (copied locally from the
archived configuration; no key printed or stored in the database).

Funnel contributor default sorting: displayed change_pct ascending for decline,
descending for growth. Undefined percentages from zero baseline go last.

## Analysis.filter (test, 2026-10-16)

Pure contract: run(*, rows, conditions=None, cumulative=None) -> {rows}.
Conditions are ANDed {field, operator, value}; operators eq/ne/gt/gte/lt/lte/in/not_in.
Missing/null values fail conditions, including ne/not_in. No conditions preserve
input order. Cumulative {field, share} operates after conditions: known finite
nonnegative numeric values, 0 < share <= 1, descending value with product_key
ascending as deterministic tie breaker. Includes the row crossing target share;
zero total returns no rows. Unknown cumulative values raise rather than become 0.
Rows are not mutated. No database access or business defaults in filter.

Funnel contributor lists now default to existing answer_scope=top: Executor calls
unchanged get_stocks, selects cumulative total_quantity share=.8, then applies
product_key IN selection to the already percent-ranked contributor rows. Stock
universe is the whole store stock snapshot, not the subset with metric changes.
Whole-store comparison totals and contributions remain computed on all funnel
facts; only displayed rows are filtered. answer_scope=all skips stocks/filter.
LLM schema uses existing answer_scope (no stock_scope); explicit 'show all' can
inherit last_metric/direction from immediate successful contributors turn.
Existing 10-minute tenant/chat-bound memory remains unchanged.

## get_orders amounts and shown-product references (test, 2026-10-16)

Approved additive output fields at top level and per product: orders_amount,
cancelled_orders_amount. Input unchanged. Source metrics_orders_daily:
orders_amount=sum(gross_order_value), cancelled_orders_amount=sum(gross-net).
Snapshot source uses historical order price_with_disc (fallback total_price),
and net excludes cancelled orders; these are order amounts, not buyout proceeds.
Decimal aggregation, null propagation for missing amounts, no fabricated zero.

Memory adds shown_product_keys from result.rows of the immediately previous
successful delivered answer, excluding hidden gains/losses and filtered products.
Existing tenant/chat and 10-minute boundaries remain. LLM requires an explicit
plural/list reference to reuse keys; unrelated standalone questions do not inherit.
Router supplies product_keys to Executor, not get_orders. Existing get_orders
reads facts; Analysis.filter selects the cohort and group_rows sums amounts using
zero grouping dimensions. Rules table formats the result; journal memory_used
records selected keys and source question ID. No database schema changes.

## Revenue routing consolidation (test, 2026-10-16)

Router maps orders_revenue to canonical orders_amount for normal order queries.
Executor also accepts old orders_revenue requests as a compatibility alias to the
same existing get_orders orders_amount facts, for scalar and rank requests.
No get_orders signature/output additions in this release. Last completed Moscow
days and explicit inclusive dates remain governed by get_orders, not old unbounded
lower-date-only revenue reads. Store scalar value and product rows share one source.
After store order amount, a semantic 'break down by products' follow-up keeps the
same metric/dates and store-wide scope; old cohort keys are not inherited.
Product results rank by orders_amount descending; table rule renders items+total.
Legacy overview/other monetary metrics are outside this migration.

## Hide zero order amounts (test, 2026-10-16)

No get_* or Analysis contract changes. Existing Analysis.filter(field=orders_amount,
operator=gt,value=0) hides zeros only from product display, before existing rank.
Period/cohort total is computed before filtering and stays unchanged.
Existing Router answer_scope top is default for order amount breakdown/reference;
all means explicitly include zero amounts. Monetary source scope=store is retained
through breakdown memory so restoring zeros restores full store, not just the
previously shown positive keys. For cohort breakdown, original product_keys remain
in journal request/memory; explicit 'they' still means only shown_product_keys.
Formatting remains in rule91; existing sections template keeps total even for an
empty filtered list. No new tool/parameter names were added.

## Funnel summary default (test, 2026-10-16)

Requests for the funnel summary (dataset=funnel, metric=funnel) now always use
existing compare analysis, with or without the word dynamics. Omitted period means
7 completed Moscow days, compared to immediately preceding 7. Explicit periods
continue to win. Other metric defaults unchanged. Existing table formatting and
get_funnel contracts unchanged; no added analysis or tools.

## General LLM clarification protocol (test, 2026-10-16)

Existing Router now performs a general post-plan intent check when displayed
products exist or the draft is invalid. No phrase-specific ambiguity matching.
LLM returns execute/clarify/unsupported, optional validated parameter updates,
and a short question plus2-3semantic options. Schema/whitelist protects tenant
fields; selection references are symbolic store/shown_products, resolved by server.
Options and bounded source context are saved in existing router_request.clarification.
Handler sends action=clarify via a generic answer table rule without calling
Executor. Existing immediately-prior journal lookup,10min TTL, tenant/chat and
successful delivery constraints apply. Resume LLM chooses an option, repeats for
an unclear answer, or cancels pending for a new question. Server revalidates updates
before execution. No new database tables, get_* or Analysis contracts.
Stock cohort execution uses existing get_stocks -> Analysis.filter -> group_rows
for selected total. Private get_* unchanged. Displayed memory excludes store-only
summary rows even when execution result internally contains rows.
This is bounded clarification infrastructure, not a guarantee of all ambiguity
recognition. Valid tools/parameter vocabulary remains constrained to current
capabilities; invalid option updates cannot execute. Existing legacy product-name
clarification remains for compatibility, rather than creating new phrase cases.

## Stock display/scope default (test, 2026-10-16)

Agreed default supersedes generic ambiguity policy for stocks: without explicit
reference to prior products, request means whole store; display all recorded stock
product rows and total via table rule. Explicit reference means shown_product_keys
from preceding delivered list. Existing clarification validator applies symbolic
selection store/shown_products, without phrase-specific condition in Python.
Whole-store stock list rows now count as displayed memory, reflecting the new
format. No get_*/Analysis/Router parameter additions, no synthesized zero rows for
catalog products absent from stock facts. Direct live check19rows119units vs6rows95.

## get_followups — согласовано и реализовано в тесте, 17 октября 2026

Вопросы покупателей маркетплейса (не уточнения чат-бота).

```python
get_followups(user_id, shop_id, marketplace='wb', product_key=None,
              is_answered=None, start_date=None, end_date=None, *, supabase=None)
```

- Без дат — все загруженные вопросы; даты задаются вместе, включительно,
  по московскому календарю. Не подставляет 7/30 дней из старого контекста.
- product_key=None — магазин; иначе только выбранный товар этого магазина.
- is_answered=False/True/None — без ответа / с ответом / все.
- Выход: `{questions_count, questions:[{question_id,product_key,title,question_text,
  question_created_at,is_answered,answer_text,answer_created_at}]}`.
- Один question_id учитывается один раз; конфликт записей — ошибка.
- Источник normalized_questions; полная пагинация и фильтры user_id/shop_id/marketplace.
  Название — из tenant-каталога, при отсутствии из product_name исходного вопроса.
  Raw payload, данные автора и секреты инструмент не возвращает.

Router выбирает существующий analysis=metric_value, dataset=followups,
metric=questions_count, view=unanswered/topics; is_answered передаёт в инструмент.
Явное имя товара приоритетнее памяти; ссылка «этому товару» использует существующую память.
Для тем без выбранного товара требуется уточнить товар.
Executor вызывает get_followups. Для topics передаёт факты в приватную функцию
Analysis question_topics.summarize: ЛЛМ возвращает только темы и исходные ID,
код проверяет полное разбиение без повторов и считает количество. Сортировка —
существующий rank по questions_count desc. Нового публичного типа Analysis нет.
Для больших наборов группировка пакетами по 60 с последующим объединением тем
и восстановлением исходных question_id; строки не отбрасываются.
Ответы оформляют существующие compact_text/sections и тестовые правила 96/97.
Общий formatter=date отображает московскую дату. Схемы таблиц не менялись.
Другие get_* и рабочая версия не менялись.

### Темы отзывов и сокращённые названия — тест, 17 октября 2026

Контракты get_reviews и get_followups не менялись. Router использует get_reviews
для тем негатива (оценки 1–2) / позитива (4–5), по умолчанию за 30 завершённых
московских дней; явные даты/период имеют приоритет. Группировка текстов — существующий
приватный Analysis question_topics с параметрами источника: feedback_id, text/pros/cons,
feedback_ids и reviews_count. Оценки без текста входят в общий счётчик отзывов,
но не отправляются на тематический анализ. Темы считаются только по исходным ID
текстовых отзывов, полное разбиение проверяется кодом. Правила ответа — в тестовой таблице.

Общий resolver товара допускает одно отличительное слово названия в склонении,
только если оно однозначно соответствует одному товару tenant-каталога. При нескольких
кандидатах выбор не делается. Неразрешённое явно названное изделие не заменяется магазином.
Новый аналитический запрос отменяет незавершённое уточнение, даже без вопросительного слова.
Уточнение просит название или артикул WB, технические имена параметров не показываются.

## Сохранённый разбор текстов — согласовано 17 октября 2026 (только тест)

Этот раздел заменяет временный разбор тем при каждом вопросе и стандартный период
30 дней для негатива/позитива.

### get_reviews

```python
get_reviews(user_id, shop_id, marketplace='wb', product_key=None,
    period_days=None, start_date=None, end_date=None,
    rating_min=None, rating_max=None, include_topics=False, *, supabase=None)
```

Без всех трёх параметров периода — все загруженные отзывы; start_date/end_date
в ответе равны null. Явный period_days либо обе даты сохраняют прежнюю семантику
завершённых московских дней. Одновременное указание обоих способов запрещено.
Рейтинг остаётся независимым фильтром фактов. Прежние ключи ответа сохраняются:
{start_date,end_date,reviews_count,reviews:[...исходные факты...]}.

### get_followups

```python
get_followups(user_id, shop_id, marketplace='wb', product_key=None,
    is_answered=None, start_date=None, end_date=None,
    include_topics=False, *, supabase=None)
```

Период по-прежнему необязательный. Ответ без include_topics прежний:
{questions_count,questions:[...исходные факты...]}.

### Одинаковое дополнение для обоих инструментов

include_topics должен быть bool. False — прежняя форма каждой записи, без новых полей.
True — у каждой записи добавляется:

```json
{"topic_analysis":{"status":"ready","analysis_version":"buyer-text-v1",
 "topics":[{"topic_id":"uuid","title":"Размер и посадка",
 "summary":"Размер меньше ожидаемого","sentiment":"negative"}]}}
```

Статусы: ready / pending / no_text / error. Отсутствующая запись, несовпавший хеш
текста или товар означают pending, а не пустую тему. Версия выбирается сервером.
Устаревшие версии не выдаются. Объединённые темы разрешаются в корневой ID при чтении.
Все чтения и связи ограничены user_id/shop_id/marketplace.

### Фоновый процесс и Analysis

Задача buyer_text_topics зарегистрирована в существующем system_metric_registry,
runner_file_key=text_topics; выполняется существующим metric_worker через
run_metric_job(job,state,registry_entry) -> rows_read/rows_upserted/last_processed_date.
Обрабатывает normalized_feedbacks и normalized_questions после их загрузки/нормализации.
Периодический запуск — существующий metrics_all/metric_scheduler, интервал 1 час;
отдельный новый сервис или демон не добавлен. При первом запуске backfill, далее
сравнение хешей и версии. Без изменений — 0 вызовов ЛЛМ. Пустой текст — no_text без ЛЛМ.

LLM выбирает тему по справочнику или предлагает новую. Сохранение тем, анализа и
связей — одна транзакция RPC save_text_analysis_batch. Новый topic ID выдаёт база;
известные ID ограничены схемой ответа и повторно проверяются кодом. Числа модель
не считает. Справочник и результаты разделены по магазинам. Пакеты сохраняются
независимо: после ошибки готовые пакеты не повторяются, ошибка отмечается по источникам.

Запросы о темах используют get_reviews/get_followups(include_topics=True) ->
Analysis.persisted_topics -> rank -> существующие табличные правила ответа.
LLM не вызывается для повторного чтения/группировки текстов во время такого расчёта
(Router по-прежнему использует LLM для понимания вопроса).
Негатив/позитив выбираются по тональности аспекта, а не только по звёздам: один
отзыв может быть в обоих наборах. Счётчик каждой темы — уникальные source ID;
отзыв с несколькими темами не считается дважды внутри одной темы.
Pending/error не изображаются как нулевой негатив; result.status=incomplete.

Нишевые темы доступны только внутри своей категории товара; общие темы имеют
category="". Schema и код проверяют category и topic_id, пакеты фоновой обработки
формируются по категориям. Чужая нишевая тема не может попасть в готовый разбор.

17.10.2026 — пополнение (тест): существующая цепочка get_stocks + get_orders → days_left → filter → rank использует warehouse_quantity для списка пополнения, темп по умолчанию за 30 завершённых московских дней, отбор days_left <= 14, сортировка asc. Общий total_quantity и контракты get_* сохранены. Дневные заказы и размеры группируются по Europe/Moscow; границы чтения нормализованных заказов — московская полночь. Для зарегистрированного задания метрик job_type=full_rebuild перестраивает всю имеющуюся историю снимков.
Прогноз days_left отдельного товара также использует warehouse_quantity; обычный ответ об остатке сохраняет total_quantity. Исторические размеры, отсутствующие в текущем каталоге, получают нулевые строки по пересчитываемым дням, чтобы перенос заказа не оставлял его на старой дате.
