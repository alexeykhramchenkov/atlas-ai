# REPORT: Architecture Alignment Audit

Дата: 2026-06-29

## 1. Основные принципы Atlas

Atlas описан как AI Analytics OS для e-commerce. Главная идея: пользователь задает естественный вопрос, а система переводит его в формальный аналитический request, выполняет расчет по правилам и возвращает человеческий ответ.

Основной pipeline:

```text
User
→ Telegram / Web Chat
→ Voice-to-Text
→ Input Normalizer
→ Context Resolver
→ Intent Router
→ Question Classifier
→ Planner
→ Executor
→ Metric Adapter
→ Internal Tools
→ Datasets / Supabase
→ Analysis Engine
→ Detector Engine
→ Action Engine
→ Answer Builder
→ Memory Writer
→ User
```

Ключевые архитектурные принципы:

1. **Analysis-first.** Сначала определяется тип анализа: `metric_value`, `best`, `worst`, `explain_change`, `risk`, `forecast` и т.д. Метрика, scope, entity и period являются параметрами анализа.
2. **Registry / Rules over hardcode.** Бизнес-правила, aliases, execution configs, plans, criteria и formatting rules должны жить в Supabase rules/registry tables, а не в Python if/else.
3. **Universal Engine.** Python должен содержать универсальные механизмы: Router, Planner, Executor, Metric Adapter, Answer Builder, Memory. Бизнес-специфика должна быть конфигурационной.
4. **Контракты между слоями.** Router, Executor, Analysis, Metric Adapter, Internal Tools, Answer Builder и Memory имеют фиксированные входы/выходы. Контракт нельзя менять без обновления `CONTRACTS.md`.
5. **LLM не считает.** Все значения должны приходить из Metric Adapter / Internal Tools / Supabase. Если данных нет, система должна честно сказать, что данных недостаточно.
6. **Analysis не ходит в Supabase напрямую.** По целевой архитектуре Analysis интерпретирует подготовленные данные и использует Metric Adapter. SQL и знание таблиц принадлежат Internal Tools / data layer.
7. **Metric Registry.** Метрика определяется как `metric + view + scope`; поддерживаемые views: `value`, `compare`, `state`, `history`, `forecast`.
8. **Analysis Registry.** Новый analysis нельзя добавлять без регистрации purpose, metrics, scopes, required views и output contract.
9. **Detector System.** Детекторы создают events с context и priority. Они не должны писать recommended actions.
10. **Маленькие изменения.** Сначала найти существующий слой/правило/registry, потом предлагать минимальный diff.

Приоритет источников истины по `DECISIONS.md`: `PROJECT_RULES.md`, `ARCHITECTURE.md`, `CONTRACTS.md`, `METRIC_REGISTRY.md`, `ANALYSIS_REGISTRY.md`. `DECISIONS.md` является историческим журналом, если противоречит registry/contract документам.

## 2. Что уже соответствует архитектуре

### Pipeline / Orchestrators

Sync, normalization, metrics и detector pipeline хорошо соответствуют registry-подходу:

- `ingestion/orchestrators/sync_registry.py` читает `system_sync_registry` и динамически загружает sync handler.
- `normalized/orchestrators/normalization_registry.py` читает `system_normalization_registry`, импортирует normalizer по path и проверяет контракт `run_normalization_job(job, state, registry_entry)`.
- `metrics/builders/orchestrators/metric_registry.py`, scheduler и worker используют `system_metric_registry`.
- `detectors/orchestrators/detector_registry.py`, scheduler и worker используют `system_detector_registry`.

Это хороший пример целевой архитектуры: scheduler создает job по registry/state/frequency, worker берет job, находит registry entry, загружает runner и обновляет state/log.

### Router / Rules

Router частично соответствует rules-first подходу:

- metric aliases читаются из `system_metric_ai_bot_rules`;
- entity aliases читаются из `system_ai_entity_rules`;
- analysis aliases читаются из `system_ai_analysis_rules`;
- scope aliases читаются из `system_ai_scope_rules`;
- lookup chain plans читаются из `system_question_type_rules`;
- fuzzy resolver используется для rule-based matching.

### Analysis Execution

`best` и `worst` исполняются через общий `ranked.py`, что соответствует решению в `DECISIONS.md`. Execution config берется из `system_metric_rules`.

`metric_value.py` также использует `system_metric_rules` и импортирует metric module по dataset, то есть находится ближе к универсальному dispatch.

### Dataset Registry / Data Docs

`DATASETS.md` хорошо выполняет роль карты фактических связей: какие tables, metrics, entities и active rules сейчас найдены. Документ явно отделяет подтвержденные связи от `UNKNOWN`.

### Event / Detector System

Detector event model в `detectors/detector_types.py` соответствует решению:

- `event_domain`;
- `event_type`;
- `entity_type`;
- `entity_id`;
- `severity`;
- `confidence`;
- `priority`;
- `title`;
- `description`;
- `payload`;
- `meta`.

Поля `recommended_action` нет, что соответствует `DECISIONS.md`.

В Supabase schema также есть `system_detector_rules` с thresholds, entity scope, required tables/columns, rules/settings и payload schema. Это правильное направление для rule-based detector layer.

## 3. Что пока не соответствует

### Router содержит hardcoded markers

В `ai_chat/routing/route.py` есть локальные наборы:

- `NON_DEFAULT_METRIC_MARKERS`;
- `FOLLOW_UP_SIZE_MARKERS`;
- `FOLLOW_UP_SALES_MARKERS`;
- `OVERVIEW_SALES_MARKERS`;
- `EN_TOP_SCOPE_MARKERS`;
- `DECLINING_PRODUCTS_MARKERS`;
- `EXPLAIN_CHANGE_SALES_METRIC_MARKERS`.

Это работает как MVP, но архитектурно является отклонением: такие знания должны быть в rules/registry tables.

### Technical metric names протекают в Router и Rules

`METRIC_REGISTRY.md` говорит, что Router должен возвращать бизнес-метрики: `orders`, `views`, `conversion`, `profit`, `revenue`, `stock`, а не технические поля.

Фактическая текущая система часто использует:

- `orders_count`;
- `orders_revenue`;
- `stock_qty`;
- `gross_order_value`;
- `total_quantity`.

`DATASETS.md` фиксирует это как текущую active reality, но по registry-документам это не целевая семантика.

### Analysis иногда ходит к Supabase через rules / fetch

По целевой архитектуре Analysis не должен знать Supabase. Фактически:

- `ranked.py` читает `system_metric_rules` и затем напрямую fetches rows из Supabase table, указанной в config;
- `metric_value.py` читает `system_metric_rules`;
- `overview.py` и другие analysis type могут тянуть данные через supabase-oriented helpers.

Это прагматичный MVP, но не полностью соответствует контракту “Analysis работает через Metric Adapter / Internal Tools”.

### Metric Adapter не является единым центром для всех analysis

`explain_change` использует `ai_chat.metric_adapter`, что ближе к целевой архитектуре. Ranking и metric_value в большей степени используют `system_metric_rules` и dataset/metric modules напрямую.

### Answer Builder смешивает rule-based и hardcoded formatting

Подробнее ниже, но основная проблема: `answer.py` содержит специальные branches вида `if dataset/analysis/entity/metric`, что противоречит принятому решению “Answer specificity lives in Supabase”.

### Schema / docs / code не полностью синхронизированы

`DECISIONS.md` описывает `system_ai_answer_rules` как целевую таблицу Answer Builder. Код `answer_builder/resolver.py` уже читает `system_ai_answer_rules`. Но в `SUPABASE_SCHEMA.md` эта таблица не найдена. Возможные объяснения:

- schema snapshot устарел;
- таблица еще не создана;
- код опережает schema.

В любом случае это архитектурный риск.

## 4. Аудит Answer Builder

### Целевая архитектура

По `DECISIONS.md` Answer Builder должен быть rule-based:

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

Python должен делать универсальные операции:

- найти answer rule;
- извлечь value по path;
- применить formatter;
- применить template;
- скрыть missing fields.

Supabase должен хранить специфику:

- какой template выбрать;
- какие поля показать;
- labels;
- formatter;
- hide rules.

### Текущее состояние

Answer Builder частично использует registry/rules:

- `answer_builder/resolver.py` читает `system_ai_answer_rules`;
- `fields.py` извлекает поля по path;
- `formatters.py` умеет `text`, `number`, `money`, `qty`, `percent`, `days`;
- `templates.py` применяет template.

Но фактический `build_answer()` сначала выполняет набор Python-specific branches:

- `if payload.get("analysis") == "explain_change"`;
- `_is_variant_ranking_answer`;
- `_is_product_orders_ranking_answer`;
- `_is_product_revenue_ranking_answer`;
- `_is_product_stock_ranking_answer`;
- `_is_overview_answer`.

И только после этого, если `supabase` передан, пытается использовать `system_ai_answer_rules`.

Если `supabase is None`, builder возвращает `_raw_json_answer`.

Вывод: Answer Builder сейчас **не является полностью rule-based**. Он содержит гибрид:

1. deterministic hardcoded formatters для MVP-сценариев;
2. зачаток rule-based resolver/template system;
3. fallback на raw JSON.

### Архитектурная оценка

Текущее состояние допустимо как MVP bridge, потому что `ROADMAP.md` прямо ставит Priority 3: “Return human-readable answers instead of JSON”. Но как долговременная архитектура это не соответствует решению “Engine is universal; answer specificity lives in Supabase”.

## 5. Аудит последних изменений

Последние изменения из `REPORT_ANSWER_FORMATTING_FIX.md` добавили форматирование для:

- `orders / best / orders_count / product`;
- `orders / best / orders_revenue / product`;
- `stocks / best / stock_qty / product`.

### Соответствуют ли архитектуре Atlas?

Частично.

Соответствуют:

- изменения сделаны в правильном слое: Answer Builder;
- analytics, SQL, router, tools и data shape не изменялись;
- задача была ограничена превращением уже готового structured result в человеческий ответ;
- результат закрывает roadmap Priority 3 на уровне MVP.

Не соответствуют целевой архитектуре:

- formatting specificity добавлена через Python branches;
- условия завязаны на `dataset`, `analysis`, `entity`, `metric`;
- labels, summary text и выбор полей зашиты в код;
- новые сценарии будут снова провоцировать добавление новых if/else.

### Это временное локальное решение или хорошо вписывается?

Это **временное локальное MVP-решение**.

Оно полезно как стабилизация пользовательского опыта, но не является целевым способом развития Answer Builder. Следующий архитектурный шаг должен быть перенос этих сценариев в `system_ai_answer_rules` / templates или расширение универсального template engine.

## 6. Риски при дальнейшем развитии

1. **If/else growth в Router и Answer Builder.** Каждый новый вопрос может добавлять marker set или branch, и engine быстро перестанет быть универсальным.
2. **Расхождение бизнес-метрик и технических полей.** Пока `orders_count`, `orders_revenue`, `stock_qty` используются как metrics, правила сложнее переносить на единый Metric Registry.
3. **Дублирование правил.** Aliases могут существовать одновременно в Supabase rules и Python marker constants.
4. **Неполный rule-based Answer Builder.** Сценарии будут работать, но изменение текста/формата потребует code diff.
5. **Schema drift.** Код ожидает `system_ai_answer_rules`, но schema snapshot ее не показывает.
6. **Analysis знает data access.** `ranked.py` фактически содержит fetching/grouping по Supabase config; это ограничивает чистоту Analysis/Metric Adapter разделения.
7. **Detector rules используются не полностью.** Есть `system_detector_rules`, но отдельные detector implementations все еще содержат много rule-like logic в Python.
8. **Contract drift.** Фактические result shapes (`rows`, `meta`, `dataset`) отличаются от более абстрактных examples в `CONTRACTS.md` (`result`, `items`, `score`).
9. **MVP exceptions могут стать permanent architecture.** Документы разрешают “сначала end-to-end”, но без планового переноса в rules временные решения закрепятся.

## 7. Рекомендации по дальнейшему развитию архитектуры

### 1. Перед каждой задачей проверять существующий механизм

Порядок для будущих задач:

1. Проверить `ANALYSIS_REGISTRY.md`: существует ли нужный analysis.
2. Проверить `METRIC_REGISTRY.md`: существует ли metric/view/scope.
3. Проверить `CONTRACTS.md`: не меняется ли вход/выход слоя.
4. Проверить active Supabase rules: aliases, entity, scope, question type, metric rules.
5. Только после этого менять код.

### 2. Развивать Answer Builder через rules

Целевой путь:

- создать/актуализировать `system_ai_answer_rules`;
- добавить template types для ranking list, metric value, overview, explain change;
- хранить field paths, labels, formatters и title/summary templates в rules;
- Python оставить только renderer-ом.

Для ranking-сценариев вместо hardcoded functions лучше иметь rule примерно такого уровня:

```text
question_type = simple
analysis = best
dataset = orders
metric = orders_count
entity = product
template_name = ranking_list
fields:
  rows[].title -> product title
  rows[].product_key -> product key
  rows[].orders_count -> number
unit = заказов
summary_template = ...
```

Если текущая schema не поддерживает такой match, расширять rules/schema только отдельным архитектурным решением.

### 3. Свести metric names к бизнес-семантике

Долгосрочно Router должен возвращать:

- `orders`, а не `orders_count`;
- `revenue`, а не `orders_revenue`;
- `stock`, а не `stock_qty`.

Mapping на fields должен жить в Metric Rules / Metric Adapter.

### 4. Убрать marker constants из Router

Sales overview, declining products, follow-up, top markers и fallback sales metric должны быть перенесены в:

- `system_ai_analysis_rules`;
- `system_metric_ai_bot_rules`;
- `system_question_type_rules`;
- `system_ai_scope_rules`;
- будущие playbook/dependency rules.

### 5. Metric Adapter сделать обязательным boundary

Для новых analysis не добавлять прямой Supabase fetch в analysis modules. Новый analysis должен просить metric/view/scope у Metric Adapter.

### 6. Расширять Detector System через rules

Для новых detector scenarios сначала проверять:

- `system_detector_registry`;
- `system_detector_rules`;
- `DetectorEvent` contract;
- cooldown/dedup/state managers.

Не добавлять recommended actions в detector layer.

### 7. Разделить MVP exceptions и target architecture

Для каждого временного hardcoded решения стоит фиксировать:

- почему оно сделано;
- какой target rule/table должен заменить его;
- какой критерий готовности для удаления hardcode.

### 8. Поддерживать docs as source of truth

Если будущая задача требует изменить контракт, analysis, metric или registry shape:

1. сначала обновить соответствующий документ;
2. получить подтверждение;
3. только потом менять код.

## Итоговая оценка

Atlas уже движется в сторону registry-driven AI Analytics OS. Pipeline/orchestrator слои соответствуют этой философии лучше всего. AI Chat слой находится в переходном состоянии: Router и Analysis частично rule-based, Answer Builder имеет зачаток rule-based architecture, но фактическое форматирование ответов сейчас преимущественно реализовано через Python branches.

Последнее форматирование ответов улучшило продуктовый UX, но архитектурно является временным MVP-решением. Следующий правильный шаг — не наращивать новые formatter if/else, а довести rule-based Answer Builder до рабочего состояния и переносить formatting specificity в Supabase rules/templates.
