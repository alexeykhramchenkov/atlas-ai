# Decisions

## Current Architecture Override

Актуальная архитектура проекта задается файлами:

- PROJECT_RULES.md
- ARCHITECTURE.md
- CONTRACTS.md
- METRIC_REGISTRY.md
- ANALYSIS_REGISTRY.md

Если DECISIONS.md противоречит этим документам, приоритет у registry/contract документов.

Термины обновлены:

- diagnostic / root_cause → explain_change
- decision → today_actions / scale / risk / opportunity
- metric dependencies → Explain Change Rules / Metric Registry
- decision criteria → scale_rules / risk_rules / opportunity_rules / action_rules

DECISIONS.md используется как исторический журнал решений, а не как главный источник архитектуры.

Документ фиксирует принятые архитектурные решения по `wb_profit_bot`. Перед изменением кода сверять с `project_docs/ARCHITECTURE.md`, `project_docs/DATASETS.md` и реальными файлами проекта.

## AI Chat Routing

### Router не хранит бизнес-правила

Решение: router должен определять намерение пользователя через Supabase rules, а не через hardcode условий в Python.

Источники правил:

* metric aliases: `system_metric_ai_bot_rules`
* entity aliases: `system_ai_entity_rules`
* analysis aliases: `system_ai_analysis_rules`
* scope aliases: `system_ai_scope_rules`
* question type aliases and plans: `system_question_type_rules`
* answer formatting rules: `system_ai_answer_rules`
* execution rules: `system_metric_rules`

Практическое правило: если вопрос роутится неправильно, сначала проверять active rule в Supabase, затем код resolver-а.

## Analysis Dispatch

### `best` и `worst` исполняются через `ranked.py`

Решение: production path для ranking сейчас идет через `ai_chat/analysis/analysis_type/ranked.py`.

Текущий dispatch:

* `metric_value` -> `ai_chat.analysis.analysis_type.metric_value.run`
* `best` -> `ai_chat.analysis.analysis_type.ranked.run`
* `worst` -> `ai_chat.analysis.analysis_type.ranked.run`

Практическое правило: новые ranking rules подключать через `system_metric_rules` и проверять `ranked.py`, а не legacy `best.py` / `worst.py`.

## Revenue Semantics

### Основная выручка по заказам = gross

Решение:

* `orders_revenue` = `gross_order_value`
* `net_orders_revenue` = `net_order_value`

Причина: обычный вопрос про выручку должен отвечать валовой выручкой. Чистая выручка используется только при явном запросе: "чистая выручка", "после отмен", `net revenue`.

Практическое правило:

* Для `orders_revenue` в `system_metric_rules.config.value_field` использовать `gross_order_value`.
* Для `net_orders_revenue` использовать `net_order_value`.
* Не подменять `gross_order_value` значением `net_order_value` в answer/enrichment layer.

## Stocks Semantics

### Остатки считаются только по последнему snapshot

Решение: stock rankings должны использовать `latest_snapshot_only=true`.

Причина: остаток является состоянием на дату, а не периодической суммой. Суммирование по нескольким `snapshot_date` дает завышенный результат.

Практическое правило:

* Для `stocks` + ranked проверять `result.meta.latest_snapshot_only=true`.
* `result.meta.date_filter_mode` должен быть `latest_snapshot`.
* `raw_rows_count` должен соответствовать строкам последнего snapshot, а не всему периоду.

## Enrichment

### Enrichment не перезаписывает метрики

Решение: product enrichment добавляет только справочные поля товара.

Разрешенные справочные поля:

* `title`
* `brand`
* `seller_sku`
* `subject_name`
* `main_photo_url`
* `marketplace_product_id`

Агрегированные поля analysis layer имеют приоритет:

* `value`
* `orders_count`
* `orders_revenue`
* `gross_order_value`
* `net_order_value`
* `stock_qty`
* `stock_value`

Практическое правило: при merge использовать приоритет row/analysis values над product info.

## Answer Scope

### Scope определяется отдельными rules

Решение: `answer_scope` и `limit` определяются через `system_ai_scope_rules`.

Текущая семантика:

* `single` -> limit 1
* `top` -> limit 5

Практическое правило:

* "у какого товара" -> `single`
* "у каких товаров" -> `top`
* TOP marker должен иметь приоритет над SINGLE marker.

## Telegram Answer Path

### Telegram сейчас возвращает raw JSON

Решение/статус: текущий Telegram handler напрямую отправляет JSON с `question`, `request`, `result`.

`ai_chat/answer_builder.py` существует, но не подключен к Telegram path.

Практическое правило: перед подключением Answer Builder проверить формат result и не ломать logging в `system_ai_questions`.

## Rule-Based Answer Builder

### Формат ответа хранится в Supabase

Дата: 2026-06-22

Проблема

Старый `ai_chat/answer_builder.py` ориентирован на tool-based path и содержит форматирование в Python.

Если хранить формат ответа в Python:

* появится hardcode под каждый вопрос;
* изменение текста ответа потребует code diff;
* Lookup Chain, Diagnostic и Decision начнут разрастаться отдельными ветками;
* Engine перестанет быть универсальным.

Решение

Переходим к rule-based Answer Builder.

Главный принцип:

```text
Engine is universal.
Answer specificity lives in Supabase.
Python does not contain business-specific answer formatting.
```

Целевой слой:

* `ai_chat/answer_builder/__init__.py`
* `ai_chat/answer_builder/answer.py`
* `ai_chat/answer_builder/resolver.py`
* `ai_chat/answer_builder/fields.py`
* `ai_chat/answer_builder/formatters.py`
* `ai_chat/answer_builder/templates.py`

Главная таблица:

* `system_ai_answer_rules`

MVP поля:

* `id`
* `question_type`
* `template_name`
* `language`
* `title_template`
* `fields jsonb`
* `priority`
* `is_active`
* `created_at`
* `updated_at`

Flow:

```text
execution_result
↓
question_type
↓
resolve_answer_rule()
↓
extract fields by path
↓
apply formatter
↓
apply template
↓
return text
```

Практическое правило

Python отвечает за универсальные операции:

* найти answer rule;
* извлечь value по path;
* применить formatter;
* применить template;
* скрыть поле по `hide_if_missing=true`.

Supabase отвечает за специфику ответа:

* какой template выбрать;
* какие поля показать;
* какие labels использовать;
* какой formatter применить;
* какие поля скрывать при отсутствии.

Пример для Lookup Chain:

```text
question_type = lookup_chain
template_name = top_product_stock
language = ru
```

Fields:

```text
steps.0.result.rows.0.title -> Товар -> text
steps.0.result.rows.0.product_key -> Артикул -> text
steps.0.result.rows.0.orders_count -> Заказы -> number
steps.0.result.rows.0.gross_order_value -> Выручка -> money
steps.1.result.rows.0.stock_qty -> Остаток -> qty
steps.1.result.rows.0.stock_qty_full -> Полный остаток -> qty
steps.1.result.rows.0.days_left -> Хватит на дней -> days, hide_if_missing=true
```

Статус: принято как целевая архитектура, код еще не реализован.

## Detector Events

### Детекторы создают events, а не recommended actions

Решение: detector layer должен создавать события с business context и priority.

Текущая модель события:

* `event_domain`
* `event_type`
* `entity_type`
* `entity_id`
* `severity`
* `confidence`
* `priority`
* `title`
* `description`
* `payload`
* `meta`

Поле `recommended_action` в `DetectorEvent` не найдено и не должно добавляться без отдельного решения.

## Supabase Safety

### Schema changes запрещены без явного решения

Решение: для расследований разрешен SELECT. Любые INSERT/UPDATE/DELETE требуют отдельного подтверждения.

Запрещено без отдельного явного подтверждения:

* менять Supabase schema;
* редактировать migrations;
* выполнять destructive SQL;
* менять `.env`;
* править `ingestion/*`, `sync/*`, `run_pipeline.py`.

## Project Docs

### `SUPABASE_SCHEMA.md` является generated snapshot

Решение: `project_docs/SUPABASE_SCHEMA.md` не редактировать вручную.

Если нужна актуализация схемы, использовать `project_docs/update_supabase_schema.py` только после отдельного подтверждения, потому что это обращение к Supabase и перегенерация большого документа.

## Universal AI Engine

### Engine не содержит бизнес-логику

Дата: 2026-06-22

Проблема

Количество вопросов, типов анализа и бизнес-сценариев будет постоянно расти.

Если хранить бизнес-логику в Python:

* Router станет огромным;
* появится множество `if/else`;
* новые вопросы будут требовать изменения кода;
* Codex будет постоянно менять engine вместо rules;
* архитектура станет плохо масштабируемой.

Решение

Engine должен быть универсальным.

Python отвечает только за универсальные механизмы:

* Router
* Planner
* Executor
* Answer Builder
* Memory

Supabase отвечает за бизнес-логику:

* metric aliases
* entity aliases
* analysis aliases
* scope aliases
* question types
* metric dependencies
* decision criteria
* execution configs

Главное правило:

```text
Engine never contains business logic.

All business rules,
question types,
dependencies,
playbooks,
decision criteria
must live in Supabase tables.
```

Практическое правило

Если появляется новый вопрос, новый тип анализа или новая бизнес-логика, сначала нужно проверить/добавить Supabase rules, а не писать hardcode в Python.

Затрагивает:

* router
* planner
* executor
* answer_builder
* memory
* supabase rules

Статус: принято.

## Question Types

### Все вопросы делятся на типы

Дата: 2026-06-22

Проблема

AI Chat должен отвечать не только на простые вопросы, но и на составные, диагностические, рекомендательные и follow-up вопросы.

Если не разделить вопросы на типы, Router и Executor будут смешивать разные сценарии выполнения.

Решение

Каждый вопрос должен относиться к одному из question types:

* `simple`
* `ranking`
* `lookup_chain`
* `compare`
* `diagnostic`
* `decision`
* `follow_up`
* `multi_object_reasoning`
* `forecast`

Семантика

* `simple` — один вопрос, один request.
* `ranking` — поиск лучших/худших объектов.
* `lookup_chain` — найти объект по метрике A и получить метрику B по найденному объекту.
* `compare` — сравнение объектов, периодов или источников.
* `diagnostic` — ответ на вопрос “почему изменился показатель?”.
* `decision` — ответ на вопрос “что делать?”.
* `follow_up` — вопрос использует Memory из предыдущего ответа.
* `multi_object_reasoning` — вопрос с несколькими условиями и фильтрами.
* `forecast` — прогноз или симуляция.

Практическое правило

Router должен определять `question_type`, но не должен знать, как именно выполнять каждый сценарий.

Planner строит `request` или `plan[]` на основе `question_type` и Supabase rules.

Executor исполняет request/plan.

Answer Builder формирует ответ.

Текущее состояние: `lookup_chain` MVP реализован в Router/Executor. Router читает `system_question_type_rules`, Executor выполняет `plan[]` по шагам.

Статус: принято.

## Lookup Chain

### Простые по смыслу, но составные вопросы исполняются через plan[]

Дата: 2026-06-22

Проблема

Вопрос может быть простым для пользователя, но требовать несколько шагов выполнения.

Пример:

```text
Какой остаток у товара с топ продажами?
```

Этот вопрос нельзя выполнить одним request, потому что сначала нужно найти товар с топ продажами, а затем получить остаток по найденному `product_key`.

Решение

Для таких вопросов используется `lookup_chain`.

Источник rules:

* `system_question_type_rules`

Пример plan:

```text
Step 1:
orders -> orders_count -> best -> product -> limit 1

Result:
product_key

Step 2:
stocks -> stock_qty -> metric_value -> product_key from step 1
```

Практическое правило

`lookup_chain` не является diagnostic question. Он не ищет причину, а связывает несколько запросов.

Текущая реализация:

* Router возвращает `question_type=lookup_chain` и `plan[]`.
* Executor выполняет шаги последовательно.
* Внутренний step получает `question_type=plan_step`.
* Step input может ссылаться на предыдущий результат через `from_step` + `path`.
* Path extraction возвращает понятные ошибки для пустых rows, отсутствующих ключей и индексов вне диапазона.

Проверенный MVP-кейс:

```text
Question:
Какой остаток у товара с топ продажами?

Step 1:
orders -> orders_count -> best -> product
result: product_key=wb_439996132, orders_count=24

Step 2:
stocks -> stock_qty -> metric_value -> product
input: product_key=wb_439996132
result: stock_qty=17

status=success
```

Статус: реализовано как MVP.

## Diagnostic Playbooks

### Вопросы “почему” используют metric dependencies

Дата: 2026-06-22

Проблема

Вопросы вида:

* Почему упали продажи?
* Почему упала прибыль?
* Почему упал CTR?
* Почему упал процент выкупа?

нельзя корректно отвечать одним SQL-запросом.

Нужно проверить цепочку связанных метрик.

Решение

Diagnostic questions должны использовать граф зависимостей метрик.

Будущая таблица:

* `system_metric_dependencies`

Пример:

```text
orders_count depends on:

* views
* cart_rate
* buyout_rate
* stock_qty
* price
* rating
* ads_budget
```

Business chain:

```text
PRICE
INVENTORY
CONTENT
REVIEWS
ADS
↓
VISIBILITY / QUALITY
↓
TRAFFIC
↓
CART
↓
ORDERS
↓
REVENUE
↓
PROFIT
```

Практическое правило

Для question_type=`diagnostic` Planner должен читать `system_metric_dependencies`, строить diagnostic `plan[]`, а Executor должен выполнять шаги последовательно.

Answer Builder должен возвращать:

* что произошло;
* какие метрики проверены;
* какие факты найдены;
* какая причина наиболее вероятна;
* где данных недостаточно.

Статус: принято как целевая архитектура.

## Decision Playbooks

### Вопросы “что делать” используют scoring criteria

Дата: 2026-06-22

Проблема

Вопросы вида:

* На какой товар поставить рекламу?
* Какую рекламу масштабировать?
* Что остановить?
* Что заказать?
* Какой товар развивать?

не являются обычной аналитикой. Это выбор действия на основе набора критериев.

Решение

Decision questions должны использовать criteria/scoring.

Будущая таблица:

* `system_decision_criteria`

Пример для `start_ads`:

```text
criteria:

* stock_qty > 30
* available_sizes > 0
* days_left > 7
* orders_count > 5
* revenue > 0
* profit_margin > 20
* rating > 4.5
* buyout_rate > 70
```

Практическое правило

Для question_type=`decision` Planner должен найти decision playbook, Executor должен собрать кандидатов, посчитать score и вернуть ranked candidates.

Answer Builder должен объяснить:

* какой объект выбран;
* почему он выбран;
* какие риски есть;
* какие кандидаты не прошли критерии.

Критерии и веса должны храниться в Supabase, а не в Python.

Статус: принято как целевая архитектура.
