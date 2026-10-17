Главный принцип

Atlas работает через Analysis-first архитектуру.

Любой вопрос пользователя сначала определяется как тип анализа.

Только после этого определяются:

* metric
* scope
* entity
* period

Формула:

Question
↓
Analysis
↓
Metric
↓
Scope
↓
Period
↓
Metrics
↓
Answer

⸻

Analysis Identity

Любой analysis в системе определяется тремя параметрами:

analysis
metric
scope

Примеры:

explain_change.orders.store

explain_change.orders.product

best.profit.product

risk.stock.product

Формула:

Analysis
↓
Metric
↓
Scope

Analysis является первичной сущностью системы.

Metric, Scope и Period являются параметрами анализа.

⸻

Analysis Registration Rule

Запрещено создавать новый analysis type без обновления ANALYSIS_REGISTRY.md.

Перед созданием нового analysis необходимо определить:

- purpose
- supported metrics
- supported scopes
- required views
- output contract

Если существующий analysis способен решить задачу, новый analysis не создается.

⸻

1. metric_value

Purpose

Получить текущее значение метрики.

Example Questions

* Сколько заказов?
* Какая прибыль?
* Сколько просмотров?

Required Inputs

* metric

Supported Metrics

* orders
* views
* profit
* revenue
* stock

Required Views

* value

⸻

2. explain_change

Purpose

Объяснить изменение метрики.

Example Questions

* Почему упали заказы?
* Почему выросла прибыль?
* Почему упала конверсия?
* Почему упали просмотры?

Required Inputs

* metric

Required Views

* compare
* state

Uses

Explain Change Rules

⸻

Explain Change Notes

find_contributors не является отдельным analysis.

find_contributors является вспомогательным шагом внутри explain_change.

Пример:

Почему упали заказы?
↓
explain_change
↓
опционально find_contributors
↓
ответ

root_cause не является отдельным analysis.

Все вопросы класса root cause должны реализовываться через explain_change.

⸻

Current MVP

orders

↓

views
cart_rate
conversion
stock

⸻

Future

profit

↓

revenue
ads_spend
logistics
commission
returns

⸻

revenue

↓

orders
average_order_value

⸻

views

↓

avg_position
organic_views
ads_views

⸻

conversion

↓

price
reviews
rating
stock

⸻

3. best

Purpose

Найти лучшие объекты.

Example Questions

* Какой товар лучший?
* Какая реклама лучшая?
* Какой склад лучший?

Required Views

* value

Uses

ranking_rules

⸻

4. worst

Purpose

Найти худшие объекты.

Example Questions

* Какой товар худший?
* Какая реклама худшая?

Required Views

* value

Uses

ranking_rules

⸻

5. scale

Purpose

Найти кандидатов для масштабирования.

Example Questions

* Что масштабировать?
* Какую рекламу увеличить?
* Какой товар развивать?

Required Views

* compare
* state

Uses

scale_rules

⸻

6. risk

Purpose

Найти риски.

Example Questions

* Где риск?
* Что может просесть?
* Какие остатки заканчиваются?

Required Views

* compare
* state

Uses

risk_rules

⸻

7. opportunity

Purpose

Найти точки роста.

Example Questions

* Где лежат деньги?
* Что я упускаю?
* Где потенциал роста?

Required Views

* compare
* state

Uses

opportunity_rules

⸻

8. today_actions

Purpose

Определить самые важные действия сегодня.

Example Questions

* Что делать?
* С чего начать?
* На чем сфокусироваться?

Required Inputs

нет

Uses

Detector Engine
Action Engine

⸻

9. overview

Purpose

Сделать сводку по магазину.

Example Questions

* Что происходит?
* Как дела у магазина?
* Что изменилось за неделю?

Required Views

* value
* compare

⸻

10. forecast

Purpose

Сделать прогноз.

Example Questions

* Что будет через месяц?
* Сколько будет заказов?
* Какой прогноз прибыли?

Required Views

* history
* forecast

⸻

11. what_if

Purpose

Сценарное моделирование.

Example Questions

* Что будет если поднять цену?
* Что будет если увеличить рекламу?
* Что будет если вернуть размеры?

Required Views

* history
* forecast
* state

⸻

Current MVP

Разрешено реализовывать:

* metric_value
* best
* worst
* explain_change

Запрещено реализовывать до отдельного решения:

* scale
* risk
* opportunity
* today_actions
* forecast
* what_if

Они остаются в реестре как будущие типы анализа.

⸻

Analysis Status

MVP:

- metric_value
- explain_change
- best
- worst

Planned:

- scale
- risk
- opportunity
- today_actions
- overview
- forecast
- what_if

Новые analysis до отдельного архитектурного решения не добавляются.

⸻

Главное правило

Analysis определяет логику системы.

Metric, Scope, Entity и Period являются параметрами анализа, а не самостоятельными сущностями.
## 2026-10-17: общий разбор покупательских текстов (тест)

Новых публичных типов анализа не добавлено. Внутренние вычисления:
- text_annotation.annotate(items, topics): семантические аспекты по готовым текстам,
  без доступа к базе. Только в фоновом runner.
- persisted_topics.summarize(rows, source_type, sentiment): уникальные ID по темам,
  готовность обработки, сортировка через существующий rank. Без DB/LLM.

Повторные фрагменты одной темы/тональности в одном тексте объединяются; источник
внутри темы считается один раз. source_type review/question использует один алгоритм.

2026-10-17: risk_check retired from active dispatch. Stock replenishment now uses existing metric_value/rank over days_left, get_stocks/get_orders, filter and rank. Default pace window 30 completed days; urgency threshold 7 days. Legacy source is archived under setup/retired-risk-check only.
