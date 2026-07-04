PROJECT_RULES.md

1. Роль Codex

Codex — исполнитель кода.

Codex не принимает архитектурные решения самостоятельно.

Перед изменениями Codex обязан:

1. Найти существующий слой/файл.
2. Объяснить, почему изменение должно быть именно там.
3. Предложить минимальный diff.
4. Не применять изменения без подтверждения.

⸻

2. Главный принцип архитектуры

Система строится как AI Analytics OS для e-commerce.

Пайплайн:

User
↓
Telegram / Web Chat
↓
Voice-to-Text
↓
Input Normalizer
↓
Context Resolver
↓
Intent Router
↓
Question Classifier
↓
Planner
↓
Executor
↓
Metric Adapter
↓
Internal Tools
↓
Datasets / Supabase
↓
Analysis Engine
↓
Detector Engine
↓
Action Engine
↓
Answer Builder
↓
Memory Writer
↓
User

⸻

3. Что запрещено

Codex запрещено:

* создавать новые сущности без проверки существующих;
* писать прямые Supabase-запросы внутри Analysis;
* считать бизнес-метрики через LLM;
* менять router, executor, answer_builder без отдельного разрешения;
* смешивать Analysis, Tools и Data Access в одном файле;
* дублировать существующие tools;
* менять контракты без обновления CONTRACTS.md;
* делать большой diff без согласования;
* удалять файлы без отдельного разрешения.

⸻

4. Разделение ответственности

Router

Определяет смысл вопроса.

Возвращает request:

* analysis
* metric
* scope
* entity
* period_days
* user_id
* shop_id
* marketplace
* language

Router не считает данные.

⸻

Executor

Получает request и вызывает нужный analysis.

Executor не содержит бизнес-логики.

⸻

Metric Adapter

Приводит разные метрики к единому формату:

* value
* compare
* state
* history
* forecast

Metric Adapter может использовать internal_tools.

⸻

Internal Tools

Достают данные из Supabase.

Internal Tools могут знать таблицы и поля.

⸻

Analysis Engine

Интерпретирует уже подготовленные данные.

Analysis Engine не ходит напрямую в Supabase.

Analysis Engine не должен содержать SQL.

⸻

Detector Engine

Находит события:

* падение заказов
* риск остатков
* рост расходов
* падение конверсии

Detector создаёт только:

problem + context + priority

Detector не пишет recommended_action.

⸻

Action Engine

Получает events / risks / opportunities.

Решает, что делать сегодня.

⸻

Answer Builder

Превращает structured result в человеческий ответ.

Answer Builder не достаёт данные.

⸻

Memory Writer

Сохраняет контекст диалога.

⸻

5. Главная формула обработки вопроса

Question
↓
Intent / Analysis
↓
Parameters
↓
Rules
↓
Metrics
↓
Metric Adapter
↓
Internal Tools
↓
Analysis Result
↓
Answer

⸻

6. Analysis-first подход

Любой вопрос сначала определяется через тип анализа.

Примеры:

* Почему упали продажи? → explain_change
* Какой товар лучший? → best
* Что делать? → today_actions
* Где риск? → risk
* Что масштабировать? → scale
* Что будет если поднять цену? → what_if
* Что будет дальше? → forecast

Metric, scope, entity, period — вторичные параметры.

⸻

7. Правила по данным

LLM не считает.

Все расчёты выполняются через:

Metric Adapter
↓
Internal Tools
↓
Supabase

Если данных нет, система должна честно вернуть:

“Недостаточно данных для ответа.”

Запрещено придумывать значения.

⸻

8. Правила по изменениям

Каждая задача должна быть маленькой.

Правильный формат задачи:

1. Проверить текущий код.
2. Показать, что уже есть.
3. Предложить минимальный diff.
4. Дождаться подтверждения.
5. Применить только согласованные изменения.
6. Запустить минимальную проверку.
7. Показать результат.

⸻

9. Правила по explain_change

explain_change отвечает на вопросы:

* Почему упали заказы?
* Почему упала прибыль?
* Почему упала конверсия?
* Почему упали просмотры?

explain_change не ходит напрямую в Supabase.

explain_change получает подготовленные метрики через Metric Adapter.

Для MVP:

metric = orders
scope = store / product

Факторы:

* views
* cart_rate
* conversion
* stock

⸻

10. Правила по новым сущностям

Если Codex считает, что нужна новая сущность, он обязан сначала ответить:

1. Какая проблема решается?
2. Почему нельзя использовать существующий слой?
3. Где она находится в общей архитектуре?
4. Какой контракт входа/выхода?
5. Какой минимальный diff?

Без этого новую сущность не создавать.

⸻

11. Текущий MVP

Текущий MVP должен поддерживать:

1. Почему упали заказы?
2. Почему упала прибыль?
3. Какой товар лучший?

Не делать до отдельного разрешения:

* find_contributors
* forecast
* what_if
* opportunity
* memory
* complex planner
* action engine
* full detector engine

⸻

12. Главное правило

Сначала рабочий end-to-end результат.

Потом улучшение архитектуры.

Не строить идеальную систему до первого работающего ответа.