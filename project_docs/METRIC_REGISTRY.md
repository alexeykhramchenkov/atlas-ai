METRIC_REGISTRY.md

Главный принцип

Metric Registry описывает все бизнес-метрики системы.

Analysis не знает таблицы Supabase.
Analysis запрашивает метрику по имени.
Metric Adapter знает, через какой internal tool получить данные.

⸻

Metric Identity

Любая метрика в системе определяется тремя параметрами:

metric
view
scope

Примеры:

orders.compare.store
orders.compare.product
stock.state.product
views.history.store

Формула:

Analysis
↓
Metric
↓
View
↓
Scope

⸻

1. Core Metrics

metric	meaning	default_view	source
orders	заказы	compare	get_orders / metrics_orders_daily
views	просмотры	compare	get_funnel / metrics_funnel_daily
cart_rate	добавления в корзину	compare	get_funnel / metrics_funnel_daily
conversion	конверсия в заказ	compare	get_funnel / metrics_funnel_daily
stock	остатки	state	get_stocks / metrics_stocks_daily
revenue	выручка	compare	get_revenue
profit	прибыль	compare	get_profit
ads_spend	расходы на рекламу	compare	get_ads
rating	рейтинг	state	get_rating
reviews	отзывы	state	get_reviews

⸻

2. Metric Views

Каждая метрика обязана поддерживать один или несколько views.

Поддерживаемые views:

* value
* compare
* state
* history
* forecast

Value

Текущее значение метрики.

Пример:

orders.value

Compare

Сравнение текущего периода с предыдущим.

Пример:

orders.compare

State

Текущее состояние объекта.

Пример:

stock.state

History

История изменений метрики.

Пример:

orders.history

Forecast

Прогноз значения метрики.

Пример:

orders.forecast

⸻

3. Scope Support

Каждая метрика поддерживает свой набор scope.

Поддерживаемые scope системы:

* store
* product
* variant
* ad
* warehouse

Не каждая метрика обязана поддерживать все scope.

Например:

stock.warehouse
поддерживается.

profit.warehouse
может не поддерживаться.

Примеры:

orders.store
orders.product

views.store
views.product

stock.product
stock.warehouse

⸻

4. Derived Metrics

Derived Metrics вычисляются из базовых метрик.

Они не хранятся в Supabase напрямую.

Примеры:

* stock_health
* rating_health
* traffic_health
* risk_orders_share
* availability_score

Derived Metrics могут использоваться Analysis Engine, но не должны храниться как отдельные dataset fields.

⸻

5. Funnel Metrics

metric	table	field	supported_views
views	metrics_funnel_daily	open_count	compare, history
cart_rate	metrics_funnel_daily	open_to_cart_pct	compare, history
conversion	metrics_funnel_daily	cart_to_order_pct	compare, history

⸻

6. Orders Metrics

metric	table	field	supported_views
orders	metrics_orders_daily	orders_count	value, compare, history

⸻

7. Stock Metrics

metric	table	field	supported_views
stock	metrics_stocks_daily	total_quantity	state
stock_full	metrics_stocks_daily	total_quantity_full	state
stock_value	metrics_stocks_daily	total_stock_value	state

⸻

8. Explain Change MVP Metrics

Для MVP explain_change по заказам используются:

target_metric	factor_metric	view
orders	views	compare
orders	cart_rate	compare
orders	conversion	compare
orders	stock	state

⸻

9. Metric Adapter Contract

Любая метрика должна возвращаться в одном из форматов:

Compare

{
  "metric": "views",
  "view": "compare",
  "current": 15765,
  "previous": 26107,
  "change_abs": -10342,
  "change_pct": -39.61,
  "period_days": 30
}

State

{
  "metric": "stock",
  "view": "state",
  "status": "ok",
  "value": 120
}

Value

{
  "metric": "orders",
  "view": "value",
  "value": 320
}

⸻

10. Naming Rules

Пользовательские метрики и технические поля не смешивать.

Правильно:

metric = orders
field = orders_count

Неправильно:

metric = orders_count

Router всегда возвращает бизнес-метрики:

* orders
* views
* conversion
* profit
* revenue
* stock

А не технические названия полей.

⸻

11. Current MVP Support

Сейчас в MVP поддерживаем:

metric	compare	state	ready
views	yes	no	yes
cart_rate	yes	no	yes
conversion	yes	no	yes
orders	in progress	no	partial
stock	no	in progress	partial

⸻

12. Future Metrics

Добавлять позже:

* buyout_rate
* avg_position
* visibility_score
* organic_views
* ads_views
* price
* discount
* available_sizes
* negative_reviews
* photo_changed
* title_changed
* description_changed
* competitor_price
* returns
* commission
* logistics
* average_order_value

## 2026-10-17: buyer_text_topics (тестовая фоновая задача)

Имя записи в существующем system_metric_registry, не новая бизнес-метрика и
не новый публичный Analysis. Runner metrics.builders.text_topics использует
прежний контракт run_metric_job, читает нормализованные отзывы и вопросы,
сохраняет производные темы в три согласованные таблицы.
