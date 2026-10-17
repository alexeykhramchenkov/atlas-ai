# DATASETS

Документ описывает текущие AI Chat dataset-связи, найденные в проекте и активных Supabase rules.

Важно: если DATASETS.md противоречит METRIC_REGISTRY.md, ANALYSIS_REGISTRY.md или CONTRACTS.md, приоритет у новых registry/contract документов.

Источники:

* `ai_chat/`
* `metrics/builders/`
* `ai_chat/routing/`
* active Supabase rules:
  * `system_metric_rules`
  * `system_metric_ai_bot_rules`
  * `system_ai_entity_rules`
  * `system_ai_analysis_rules`
  * `system_ai_scope_rules`
  * `system_question_type_rules`

Если связь не найдена в коде или active rules, она помечена как `UNKNOWN`.

Важно: `project_docs/SUPABASE_SCHEMA.md` является generated snapshot. Для текущих active rules при расследовании использовать живой SELECT к Supabase.

---

## Orders

### Назначение

Хранит и анализирует заказы: количество заказов, валовую выручку по заказам, чистую выручку после отмен, отмены, сумму отмен и средний чек.

Используется AI Chat для вопросов вида:

* сколько заказов;
* какой товар принес больше всего заказов;
* какой товар принес больше всего выручки;
* какая чистая выручка;
* сколько отмен;
* какой процент отмен;
* какой средний чек.

### Таблицы

* `metrics_orders_daily`
* `metrics_orders_variants_daily`

`metrics_orders_daily` используется активными AI rules для `store` и `product`.

`metrics_orders_variants_daily` строится в `metrics/builders/metrics_orders_variants_daily.py`, но активные AI rules для Orders variant-level анализа не найдены: `UNKNOWN`.

### Метрики

Найдены в `system_metric_ai_bot_rules`, `system_metric_rules` и `ai_chat/metric/orders.py`:

* `orders_count`
* `orders_revenue`
* `net_orders_revenue`
* `cancelled_orders`
* `cancelled_revenue`
* `cancel_rate`
* `average_order_value`

Поля таблицы `metrics_orders_daily`, используемые правилами:

* `orders_count`
* `cancelled_orders_count`
* `gross_order_value`
* `net_order_value`
* `avg_order_value`

Правила выручки:

* `orders_revenue` = `gross_order_value`
* `net_orders_revenue` = `net_order_value`
* `cancelled_revenue` = `gross_order_value - net_order_value`

### Entity

Поддержаны в `ai_chat/metric/orders.py`:

* `store`
* `product`

Найдены в active `system_ai_entity_rules`, но не подтверждены активными Orders rules:

* `variant` — `UNKNOWN` для Orders AI Chat
* `warehouse` — не относится к Orders
* `region` — поддержан для `best/worst.orders_count` через группировку
  `normalized_orders.region_name`; `orders_count` считает созданные заказы,
  включая отменённые, как и основной контракт заказов.

### Analysis

Активно используется:

* `metric_value`
* `best`
* `worst`
* `ranked`

Важная деталь: `best` и `worst` в `ai_chat/analysis/executor.py` направляются в `ai_chat/analysis/analysis_type/ranked.py`.

`answer_scope` не является analysis type. Он влияет на `limit` через `system_ai_scope_rules`: `single` -> 1, `top` -> 5.

Найдены в `system_ai_analysis_rules`, но не подтверждены active Orders handlers:

* `compare` — `UNKNOWN`
* `explain_change` — `UNKNOWN`

`overview` для Orders как dataset analysis не найден: `UNKNOWN`.

Lookup Chain использует Orders как первый шаг для поиска `product_key`, например:

* `orders` -> `metrics_orders_daily` -> `orders_count` -> `product` -> `best` -> `rows.0.product_key`

### Особенности

* Active metric routing идет через `system_metric_ai_bot_rules`.
* Active metric execution rules идут через `system_metric_rules`.
* `metric_value` загружает rule config и вызывает dataset-модуль `ai_chat/metric/orders.py`.
* `best` и `worst` используют ranked analysis.
* Product ranking обогащается справочными полями товара через `ai_chat/enrichers/product.py`.
* Enrichment должен добавлять только справочные поля товара и не должен перезаписывать агрегированные metric fields.
* Для обычной выручки используется gross revenue: `gross_order_value`.
* Для чистой выручки используется net revenue: `net_order_value`.
* Metric builders внутри `metrics/builders/metrics_orders_daily.py` и `metrics/builders/metrics_orders_variants_daily.py` используют `net_order_value` для growth/share расчетов; это не должно менять AI Chat правило `orders_revenue = gross_order_value`.
* В `ai_chat/metric/orders.py` alias `revenue` нормализуется в `orders_revenue`.
* `metrics_orders_variants_daily` существует и строится builder-ом, но active AI Chat rules для него не найдены.
* Если в ranked config `value_field` и `revenue_field` указывают на одно поле, нельзя повторно суммировать это поле как secondary revenue, иначе агрегат может быть завышен.
* Для ranked result по revenue проверять одновременно `value`, `gross_order_value`, `net_order_value` и `meta.raw_rows_count`.
* В Lookup Chain MVP Orders может передавать `product_key` в следующий dataset через `from_step` + `path`.

### Связи

Найдены в active `system_metric_rules`:

* `orders` -> `metrics_orders_daily` -> `orders_count` -> `store` -> `metric_value`
* `orders` -> `metrics_orders_daily` -> `cancelled_orders` -> `store` -> `metric_value`
* `orders` -> `metrics_orders_daily` -> `cancel_rate` -> `store` -> `metric_value`
* `orders` -> `metrics_orders_daily` -> `average_order_value` -> `store` -> `metric_value`
* `orders` -> `metrics_orders_daily` -> `orders_revenue` -> `store` -> `metric_value`
* `orders` -> `metrics_orders_daily` -> `net_orders_revenue` -> `store` -> `metric_value`
* `orders` -> `metrics_orders_daily` -> `cancelled_revenue` -> `store` -> `metric_value`
* `orders` -> `metrics_orders_daily` -> `orders_count` -> `product` -> `best`
* `orders` -> `metrics_orders_daily` -> `orders_count` -> `product` -> `worst`
* `orders` -> `metrics_orders_daily` -> `orders_revenue` -> `product` -> `best`
* `orders` -> `metrics_orders_daily` -> `orders_revenue` -> `product` -> `worst`
* `orders` -> `metrics_orders_daily` -> `net_orders_revenue` -> `product` -> `best`
* `orders` -> `metrics_orders_daily` -> `orders_count` -> `product` -> `best` -> Lookup Chain step1

Known table without active AI Chat rule:

* `orders` -> `metrics_orders_variants_daily` -> `UNKNOWN` -> `variant` -> `UNKNOWN`

---

## Stocks

### Назначение

Хранит и анализирует остатки товаров, размеры, склады, товары в пути и стоимость остатков.

Используется AI Chat для вопросов вида:

* сколько товара на остатке;
* у какого товара больше всего остатков;
* у каких товаров больше всего остаток;
* у какого размера больше всего остатков;
* на каком складе больше всего товара;
* стоимость остатков.

### Таблицы

* `metrics_stocks_daily`
* `metrics_stocks_variants_daily`

Назначение по коду `ai_chat/metric/stocks.py`:

* `metrics_stocks_daily` используется для `store` и `product`
* `metrics_stocks_variants_daily` используется для `variant`, `warehouse`, `product_warehouse`, `variant_warehouse`

### Метрики

Найдены в `system_metric_ai_bot_rules`:

* `stock_qty`
* `stock_qty_full`
* `stock_in_way_to_client`
* `stock_in_way_from_client`
* `stock_value`

Дополнительно поддержаны в `ai_chat/metric/stocks.py`:

* `avg_stock_value_per_unit`
* `variants_count`
* `warehouses_count`

Поля таблицы `metrics_stocks_daily`:

* `total_quantity`
* `total_quantity_full`
* `total_in_way_to_client`
* `total_in_way_from_client`
* `total_stock_value`
* `variants_count`
* `warehouses_count`

Поля таблицы `metrics_stocks_variants_daily`:

* `quantity`
* `quantity_full`
* `in_way_to_client`
* `in_way_from_client`
* `stock_value`

Aliases в `ai_chat/metric/stocks.py`:

* `total_stock_qty` -> `stock_qty`
* `stock_qty` -> `stock_qty`
* `stock_qty_full` -> `stock_qty_full`
* `stock_in_way` -> `stock_in_way_to_client`
* `stock_in_way_to_client` -> `stock_in_way_to_client`
* `stock_in_way_from_client` -> `stock_in_way_from_client`
* `stock_value` -> `stock_value`

### Entity

Поддержаны в `ai_chat/metric/stocks.py`:

* `store`
* `product`
* `variant`
* `warehouse`
* `product_warehouse`
* `variant_warehouse`

Найдены в active `system_ai_entity_rules`:

* `store`
* `product`
* `variant`
* `warehouse`
* `region`

Для Stocks active `system_metric_rules` найдены для:

* `product`
* `variant`
* `warehouse`

Для `store`, `product_warehouse`, `variant_warehouse` handler есть в коде, но active ranked rules не найдены: `UNKNOWN`.

### Analysis

Активно используется:

* `metric_value`
* `best`
* `worst`
* `ranked`

Важная деталь: `best` и `worst` в `ai_chat/analysis/executor.py` направляются в `ai_chat/analysis/analysis_type/ranked.py`.

`answer_scope` не является analysis type. Он влияет на `limit` через `system_ai_scope_rules`: `single` -> 1, `top` -> 5.

Найдены в `system_ai_analysis_rules`, но не подтверждены active Stocks handlers:

* `compare` — `UNKNOWN`
* `explain_change` — `UNKNOWN`

`overview` для Stocks как dataset analysis не найден: `UNKNOWN`.

Lookup Chain использует Stocks как следующий шаг, когда `product_key` уже найден предыдущим step:

* `stocks` -> `metrics_stocks_daily` -> `stock_qty` -> `product` -> `metric_value`

### Особенности

* Для active stock ranking rules используется `latest_snapshot_only = true`.
* При `latest_snapshot_only = true` ranked analysis сначала получает последнюю `snapshot_date`, затем фильтрует строки только этой даты.
* Для stock ranked result обязательно проверять `meta.latest_snapshot_only`, `meta.latest_snapshot_date`, `meta.date_filter_mode`, `meta.raw_rows_count`.
* `store` и `product` в `metric_value` используют `metrics_stocks_daily`.
* `variant`, `warehouse`, `product_warehouse`, `variant_warehouse` в `metric_value` используют `metrics_stocks_variants_daily`.
* Product/store fields в `metrics_stocks_daily` имеют prefix `total_*`.
* Variant/warehouse fields в `metrics_stocks_variants_daily` не имеют prefix `total_*`.
* `stock_qty` нормализуется так:
  * product/store: `total_quantity`
  * variant/warehouse: `quantity`
* `stock_value` нормализуется так:
  * product/store: `total_stock_value`
  * variant/warehouse: `stock_value`
* Entity routing использует `system_ai_entity_rules`.
* Для entity routing более специфичный alias должен выигрывать у короткого общего alias. Например, `на каком складе` должен выигрывать у `товар`.
* Scope routing использует `system_ai_scope_rules`. Например, `у каких товаров` должен давать `answer_scope=top`, а `у какого товара` должен давать `answer_scope=single`.
* Lookup Chain routing использует `system_question_type_rules`; plan может передать `product_key` из Orders step в Stocks step.
* Active routing rules для `stock_qty_full`, `stock_in_way_to_client`, `stock_in_way_from_client`, `stock_value` найдены в `system_metric_ai_bot_rules`, но active execution rules в `system_metric_rules` найдены только для `stock_qty`: остальные execution связи `UNKNOWN`.

### Связи

Найдены в active `system_metric_rules`:

* `stocks` -> `metrics_stocks_daily` -> `stock_qty` -> `product` -> `best`
* `stocks` -> `metrics_stocks_daily` -> `stock_qty` -> `product` -> `worst`
* `stocks` -> `metrics_stocks_variants_daily` -> `stock_qty` -> `variant` -> `best`
* `stocks` -> `metrics_stocks_variants_daily` -> `stock_qty` -> `variant` -> `worst`
* `stocks` -> `metrics_stocks_variants_daily` -> `stock_qty` -> `warehouse` -> `best`
* `stocks` -> `metrics_stocks_variants_daily` -> `stock_qty` -> `warehouse` -> `worst`

Найдены в `ai_chat/metric/stocks.py` handler-level support:

* `stocks` -> `metrics_stocks_daily` -> stock metrics -> `store` -> `metric_value`
* `stocks` -> `metrics_stocks_daily` -> stock metrics -> `product` -> `metric_value`
* `stocks` -> `metrics_stocks_variants_daily` -> stock metrics -> `variant` -> `metric_value`
* `stocks` -> `metrics_stocks_variants_daily` -> stock metrics -> `warehouse` -> `metric_value`
* `stocks` -> `metrics_stocks_variants_daily` -> stock metrics -> `product_warehouse` -> `metric_value`
* `stocks` -> `metrics_stocks_variants_daily` -> stock metrics -> `variant_warehouse` -> `metric_value`
* `orders` -> `orders_count` -> `best/product` -> `product_key` -> `stocks` -> `stock_qty` -> `metric_value/product`

Routing rules found, execution rules not found:

* `stocks` -> `UNKNOWN` -> `stock_qty_full` -> `UNKNOWN` -> `UNKNOWN`
* `stocks` -> `UNKNOWN` -> `stock_in_way_to_client` -> `UNKNOWN` -> `UNKNOWN`
* `stocks` -> `UNKNOWN` -> `stock_in_way_from_client` -> `UNKNOWN` -> `UNKNOWN`
* `stocks` -> `UNKNOWN` -> `stock_value` -> `UNKNOWN` -> `UNKNOWN`
