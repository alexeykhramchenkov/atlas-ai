# REPORT: Atlas Questions Audit After Rule-Based Answer Builder

Дата: 2026-06-29

## 1. Summary
- total questions: 57
- OK: 8
- PARTIAL: 2
- BROKEN: 0
- NOT_SUPPORTED: 43
- WEAK_ANSWER: 4
- NO_DATA: 0
- raw JSON answers: 4

Метод проверки: `route(question) -> executor.execute(request) -> build_answer(..., supabase=supabase)`. Код, router, answer_builder, rules, Supabase и Git в рамках этого аудита не изменялись.

## 2. What improved
- У каких товаров больше всего заказов? — стало лучше: `ranking_list` rule_id=3, raw JSON нет.
- Покажи топ 5 товаров по заказам — стало лучше: `ranking_list` rule_id=3, raw JSON нет.
- У каких товаров больше всего выручки? — стало лучше: `ranking_list` rule_id=4, raw JSON нет.
- Какой товар дал больше всего выручки? — стало лучше: `ranking_list` rule_id=4, raw JSON нет.
- У каких товаров больше всего остатков? — стало лучше: `ranking_list` rule_id=5, raw JSON нет.
- У какого товара больше всего остатков? — стало лучше: `ranking_list` rule_id=5, raw JSON нет.

## 3. What still works poorly
- Сколько заказов было за последние 30 дней? — WEAK_ANSWER: Есть данные, но ответ остался raw JSON.
- Какая выручка за последние 30 дней? — WEAK_ANSWER: Есть данные, но ответ остался raw JSON.
- Почему выросли продажи? — PARTIAL: Ответ есть, но объясняет падение продаж, а вопрос про рост.
- У каких товаров заканчиваются остатки? — WEAK_ANSWER: Возвращает stock metric_value rows как JSON, без явной фильтрации заканчивающихся остатков.
- На каком складе больше всего товара? — PARTIAL: Вопрос про склад, route уходит в stocks/best/product и отвечает товаром, не складом.
- Какие товары отсутствуют на складе? — WEAK_ANSWER: Есть данные, но ответ остался raw JSON.

## 4. What is not supported
- Какая прибыль за последние 30 дней?
- Сколько товаров сейчас в магазине?
- Какие товары продаются лучше всего?
- Какие товары продаются хуже всего?
- У каких товаров больше всего прибыли?
- У каких товаров больше всего просмотров?
- У каких товаров больше всего возвратов?
- Почему упали просмотры?
- Почему выросли просмотры?
- Почему снизилась конверсия?
- Что сильнее всего повлияло на продажи за последние 30 дней?
- Что происходит с товаром wb_236370462?
- Почему у товара wb_236370462 упали просмотры?
- Какие показатели изменились у товара wb_236370462?
- Есть ли проблемы у товара wb_236370462?
- Какие товары скоро закончатся?
- Какие размеры закончились?
- Какая сейчас конверсия?
- Какой cart rate?
- Какой buyout rate?
- На каком этапе теряется больше всего покупателей?
- Какие товары имеют низкую конверсию?
- Какая комиссия Wildberries?
- Сколько потратили на логистику?
- Какие товары самые прибыльные?
- Какие товары самые убыточные?
- Из чего складывается прибыль?
- Сравни последние 30 дней с предыдущими 30 днями.
- Какие показатели изменились сильнее всего?
- Какие товары выросли?
- Какие товары упали?
- Что изменилось за неделю?
- Какие товары находятся в зоне риска?
- На что мне стоит обратить внимание?
- Есть ли критические проблемы?
- Какие события произошли за последние 30 дней?
- Что ухудшилось сильнее всего?
- Что происходит в магазине?
- Как чувствует себя магазин?
- Есть ли проблемы?
- Что изменилось за последнее время?
- Что мне нужно знать сегодня?
- Сделай полный анализ магазина.

## 5. Remaining raw JSON cases
- Сколько заказов было за последние 30 дней? — orders/metric_value/orders_count/store
- Какая выручка за последние 30 дней? — orders/metric_value/orders_revenue/store
- У каких товаров заканчиваются остатки? — stocks/metric_value/stock_qty/product
- Какие товары отсутствуют на складе? — stocks/metric_value/stock_qty/product

## 6. Detailed results

| Question | Answer | Route / Request | Analysis / Tool | Status | Raw JSON | Improved | Comment |
|---|---|---|---|---|---|---|---|
| Сколько заказов было за последние 30 дней? | { "question": "Сколько заказов было за последние 30 дней?", "request": { "is_valid_question": true, "question_type": "simple", "dataset": "orders", "analysis": "metric_value", "metric": "orders_count", "entity": "store", "period_days": 30, "answer_scope": "single", "limit": 1, "user_id": 1, "shop_id": 1, "marketplace": "wb" }, "result": { "dataset": "orders", "analysis": "metric_value", "entity": "store", "period_days": 30, "orders_count": 114.0, "orders_revenue": 315620.13 } } | question_type=simple; dataset=orders; analysis=metric_value; metric=orders_count; entity=store; period_days=30; answer_scope=single; limit=1 | orders/metric_value/orders_count/store | WEAK_ANSWER | yes | no | Есть данные, но ответ остался raw JSON. |
| Какая выручка за последние 30 дней? | { "question": "Какая выручка за последние 30 дней?", "request": { "is_valid_question": true, "question_type": "simple", "dataset": "orders", "analysis": "metric_value", "metric": "orders_revenue", "entity": "store", "period_days": 30, "answer_scope": "single", "limit": 1, "user_id": 1, "shop_id": 1, "marketplace": "wb" }, "result": { "dataset": "orders", "analysis": "metric_value", "entity": "store", "period_days": 30, "orders_count": 114.0, "orders_revenue": 403051.13 } } | question_type=simple; dataset=orders; analysis=metric_value; metric=orders_revenue; entity=store; period_days=30; answer_scope=single; limit=1 | orders/metric_value/orders_revenue/store | WEAK_ANSWER | yes | no | Есть данные, но ответ остался raw JSON. |
| Какая прибыль за последние 30 дней? | Question is unclear or unsupported. | INVALID:unsupported_metric | - | NOT_SUPPORTED | no | no | unsupported_metric |
| Сколько товаров сейчас в магазине? | Question is unclear or unsupported. | INVALID:unsupported_metric | - | NOT_SUPPORTED | no | no | unsupported_metric |
| Какие товары продаются лучше всего? | Question is unclear or unsupported. | INVALID:unsupported_metric | - | NOT_SUPPORTED | no | no | unsupported_metric |
| Какие товары продаются хуже всего? | Question is unclear or unsupported. | INVALID:unsupported_metric | - | NOT_SUPPORTED | no | no | unsupported_metric |
| У каких товаров больше всего заказов? | Топ товаров по заказам за последние 30 дней: 1. Платье феи для девочки / wb_439996132 — 19 заказов 2. Платье праздничное пышное с длинными рукавами и завязками / wb_236370462 — 17 заказов 3. Платье праздничное ретро / wb_263628189 — 14 заказов 4. Платье с крыльями ангела / wb_236348866 — 11 заказов 5. Платье сарафан летний нарядный / wb_236356081 — 10 заказов AI Summary: Больше всего заказов сейчас дают первые товары в рейтинге. Основной лидер — wb_439996132. | question_type=simple; dataset=orders; analysis=best; metric=orders_count; entity=product; period_days=30; answer_scope=top; limit=5; rule_id=3; template=ranking_list | orders/best/orders_count/product | OK | no | yes | Человеческий ranking ответ. Улучшение: после rule-based Answer Builder ответ идет через ranking_list rule/template, raw JSON нет. |
| Покажи топ 5 товаров по заказам | Топ товаров по заказам за последние 30 дней: 1. Платье феи для девочки / wb_439996132 — 19 заказов 2. Платье праздничное пышное с длинными рукавами и завязками / wb_236370462 — 17 заказов 3. Платье праздничное ретро / wb_263628189 — 14 заказов 4. Платье с крыльями ангела / wb_236348866 — 11 заказов 5. Платье сарафан летний нарядный / wb_236356081 — 10 заказов AI Summary: Больше всего заказов сейчас дают первые товары в рейтинге. Основной лидер — wb_439996132. | question_type=simple; dataset=orders; analysis=best; metric=orders_count; entity=product; period_days=30; answer_scope=top; limit=5; rule_id=3; template=ranking_list | orders/best/orders_count/product | OK | no | yes | Человеческий ranking ответ. Улучшение: после rule-based Answer Builder ответ идет через ranking_list rule/template, raw JSON нет. |
| У каких товаров больше всего выручки? | Топ товаров по выручке за последние 30 дней: 1. Платье феи для девочки / wb_439996132 — 133 380 ₽ 2. Платье праздничное пышное с длинными рукавами и завязками / wb_236370462 — 64 090 ₽ 3. Платье праздничное ретро / wb_263628189 — 48 720 ₽ 4. Платье нарядное праздничное пышное / wb_236336854 — 26 912 ₽ 5. Платье с крыльями ангела / wb_236348866 — 26 180 ₽ AI Summary: Основная выручка сосредоточена в верхних товарах рейтинга. Лидер по выручке — wb_439996132. | question_type=simple; dataset=orders; analysis=best; metric=orders_revenue; entity=product; period_days=30; answer_scope=top; limit=5; rule_id=4; template=ranking_list | orders/best/orders_revenue/product | OK | no | yes | Человеческий ranking ответ. Улучшение: после rule-based Answer Builder ответ идет через ranking_list rule/template, raw JSON нет. |
| Какой товар дал больше всего выручки? | Топ товаров по выручке за последние 30 дней: 1. Платье феи для девочки / wb_439996132 — 133 380 ₽ AI Summary: Основная выручка сосредоточена в верхних товарах рейтинга. Лидер по выручке — wb_439996132. | question_type=simple; dataset=orders; analysis=best; metric=orders_revenue; entity=product; period_days=30; answer_scope=single; limit=1; rule_id=4; template=ranking_list | orders/best/orders_revenue/product | OK | no | yes | Человеческий ranking ответ. Улучшение: после rule-based Answer Builder ответ идет через ranking_list rule/template, raw JSON нет. |
| У каких товаров больше всего прибыли? | Question is unclear or unsupported. | INVALID:unsupported_metric | - | NOT_SUPPORTED | no | no | unsupported_metric |
| У каких товаров больше всего просмотров? | Question is unclear or unsupported. | INVALID:unsupported_metric | - | NOT_SUPPORTED | no | no | unsupported_metric |
| У каких товаров больше всего остатков? | Товары с наибольшими остатками: 1. Платье с крыльями ангела / wb_236348866 — 123 шт. 2. Платье праздничное пышное с длинными рукавами и завязками / wb_236370462 — 109 шт. 3. Платье нарядное праздничное пышное с бантом / wb_236350068 — 102 шт. 4. Платье нарядное праздничное пышное / wb_236336854 — 56 шт. 5. Платье для девочки пышное с пайетками / wb_439996134 — 47 шт. AI Summary: Самый большой остаток сейчас у wb_236348866. Эти товары стоит отслеживать отдельно. | question_type=simple; dataset=stocks; analysis=best; metric=stock_qty; entity=product; period_days=30; answer_scope=top; limit=5; rule_id=5; template=ranking_list | stocks/best/stock_qty/product | OK | no | yes | Человеческий ranking ответ. Улучшение: после rule-based Answer Builder ответ идет через ranking_list rule/template, raw JSON нет. |
| У какого товара больше всего остатков? | Товары с наибольшими остатками: 1. Платье с крыльями ангела / wb_236348866 — 123 шт. AI Summary: Самый большой остаток сейчас у wb_236348866. Эти товары стоит отслеживать отдельно. | question_type=simple; dataset=stocks; analysis=best; metric=stock_qty; entity=product; period_days=30; answer_scope=single; limit=1; rule_id=5; template=ranking_list | stocks/best/stock_qty/product | OK | no | yes | Человеческий ranking ответ. Улучшение: после rule-based Answer Builder ответ идет через ranking_list rule/template, raw JSON нет. |
| У каких товаров больше всего возвратов? | Question is unclear or unsupported. | INVALID:unsupported_metric | - | NOT_SUPPORTED | no | no | unsupported_metric |
| Почему упали продажи? | Данные - Заказы: -41.83% - Просмотры: -68.11% - Cart rate: +1.76% - Конверсия: -10.11% - Остатки: 660 шт. AI Summary Заказы изменились в основном из-за падения трафика. Конверсия тоже ухудшилась, поэтому снижение видно и в трафике, и ниже по воронке. | question_type=simple; dataset=orders; analysis=explain_change; metric=orders; entity=store; scope=store; period_days=30; answer_scope=single; limit=1 | orders/explain_change/orders/store | OK | no | no | Человеческий explain_change ответ. |
| Почему выросли продажи? | Данные - Заказы: -41.83% - Просмотры: -68.11% - Cart rate: +1.76% - Конверсия: -10.11% - Остатки: 660 шт. AI Summary Заказы изменились в основном из-за падения трафика. Конверсия тоже ухудшилась, поэтому снижение видно и в трафике, и ниже по воронке. | question_type=simple; dataset=orders; analysis=explain_change; metric=orders; entity=store; scope=store; period_days=30; answer_scope=single; limit=1 | orders/explain_change/orders/store | PARTIAL | no | no | Ответ есть, но объясняет падение продаж, а вопрос про рост. |
| Почему упали просмотры? | Question is unclear or unsupported. | INVALID:unsupported_metric | - | NOT_SUPPORTED | no | no | unsupported_metric |
| Почему выросли просмотры? | Question is unclear or unsupported. | INVALID:unsupported_metric | - | NOT_SUPPORTED | no | no | unsupported_metric |
| Почему снизилась конверсия? | Question is unclear or unsupported. | INVALID:unsupported_metric | - | NOT_SUPPORTED | no | no | unsupported_metric |
| Что сильнее всего повлияло на продажи за последние 30 дней? | Question is unclear or unsupported. | INVALID:unsupported_metric | - | NOT_SUPPORTED | no | no | unsupported_metric |
| Что происходит с товаром wb_236370462? | Question is unclear or unsupported. | INVALID:unsupported_metric | - | NOT_SUPPORTED | no | no | unsupported_metric |
| Почему у товара wb_236370462 упали продажи? | Данные - Заказы: -48.57% - Просмотры: -71.51% - Cart rate: -0.12% - Конверсия: -24.69% - Остатки: 109 шт. AI Summary У плаща "Платье праздничное пышное с длинными рукавами и завязками" упали продажи на 48,57% из-за снижения просмотров на 71,51%. Конверсия также снизилась на 24,69%, что указывает на ухудшение качества воронки продаж. | question_type=simple; dataset=orders; analysis=explain_change; metric=orders; entity=product; scope=product; period_days=30; answer_scope=single; limit=1 | orders/explain_change/orders/product | OK | no | no | Product explain_change распознан и отвечает по конкретному товару. |
| Почему у товара wb_236370462 упали просмотры? | Question is unclear or unsupported. | INVALID:unsupported_metric | - | NOT_SUPPORTED | no | no | unsupported_metric |
| Какие показатели изменились у товара wb_236370462? | Question is unclear or unsupported. | INVALID:unsupported_metric | - | NOT_SUPPORTED | no | no | unsupported_metric |
| Есть ли проблемы у товара wb_236370462? | Question is unclear or unsupported. | INVALID:unsupported_metric | - | NOT_SUPPORTED | no | no | unsupported_metric |
| У каких товаров заканчиваются остатки? | { "question": "У каких товаров заканчиваются остатки?", "request": { "is_valid_question": true, "question_type": "simple", "dataset": "stocks", "analysis": "metric_value", "metric": "stock_qty", "entity": "product", "period_days": 30, "answer_scope": "top", "limit": 5, "user_id": 1, "shop_id": 1, "marketplace": "wb" }, "result": { "entity": "product", "dataset": "stocks", "analysis": "metric_value", "metric": "stock_qty", "snapshot_date": "2026-06-26", "rows": [ { "entity": "product", "product_key": "wb_236336854", "marketplace_product_id": "236336854", "seller_sku": "wb27m5cwls", "stock_qty": 56.0, "stock_qty_full": 58.0, "stock_in_way_to_client": 1.0, "stock_in_way_from_client": 1.0, "stock_value": 195112.0, "variants_count": 4.0, "warehouses_count": 19.0, "avg_stock_value_per_unit": 3364.0 }, { "entity": "product", "product_key": "wb_236342090", "marketplace_product_id": "236342090",… | question_type=simple; dataset=stocks; analysis=metric_value; metric=stock_qty; entity=product; period_days=30; answer_scope=top; limit=5 | stocks/metric_value/stock_qty/product | WEAK_ANSWER | yes | no | Возвращает stock metric_value rows как JSON, без явной фильтрации заканчивающихся остатков. |
| Какие товары скоро закончатся? | Question is unclear or unsupported. | INVALID:unsupported_metric | - | NOT_SUPPORTED | no | no | unsupported_metric |
| На каком складе больше всего товара? | Товары с наибольшими остатками: 1. Платье с крыльями ангела / wb_236348866 — 123 шт. AI Summary: Самый большой остаток сейчас у wb_236348866. Эти товары стоит отслеживать отдельно. | question_type=simple; dataset=stocks; analysis=best; metric=stock_qty; entity=product; period_days=30; answer_scope=single; limit=1; rule_id=5; template=ranking_list | stocks/best/stock_qty/product | PARTIAL | no | no | Вопрос про склад, route уходит в stocks/best/product и отвечает товаром, не складом. |
| Какие размеры закончились? | Question is unclear or unsupported. | INVALID:unsupported_metric | - | NOT_SUPPORTED | no | no | unsupported_metric |
| Какие товары отсутствуют на складе? | { "question": "Какие товары отсутствуют на складе?", "request": { "is_valid_question": true, "question_type": "simple", "dataset": "stocks", "analysis": "metric_value", "metric": "stock_qty", "entity": "product", "period_days": 30, "answer_scope": "top", "limit": 5, "user_id": 1, "shop_id": 1, "marketplace": "wb" }, "result": { "entity": "product", "dataset": "stocks", "analysis": "metric_value", "metric": "stock_qty", "snapshot_date": "2026-06-26", "rows": [ { "entity": "product", "product_key": "wb_236336854", "marketplace_product_id": "236336854", "seller_sku": "wb27m5cwls", "stock_qty": 56.0, "stock_qty_full": 58.0, "stock_in_way_to_client": 1.0, "stock_in_way_from_client": 1.0, "stock_value": 195112.0, "variants_count": 4.0, "warehouses_count": 19.0, "avg_stock_value_per_unit": 3364.0 }, { "entity": "product", "product_key": "wb_236342090", "marketplace_product_id": "236342090", "s… | question_type=simple; dataset=stocks; analysis=metric_value; metric=stock_qty; entity=product; period_days=30; answer_scope=top; limit=5 | stocks/metric_value/stock_qty/product | WEAK_ANSWER | yes | no | Есть данные, но ответ остался raw JSON. |
| Какая сейчас конверсия? | Question is unclear or unsupported. | INVALID:unsupported_metric | - | NOT_SUPPORTED | no | no | unsupported_metric |
| Какой cart rate? | Question is unclear or unsupported. | INVALID:unsupported_metric | - | NOT_SUPPORTED | no | no | unsupported_metric |
| Какой buyout rate? | Question is unclear or unsupported. | INVALID:unsupported_metric | - | NOT_SUPPORTED | no | no | unsupported_metric |
| На каком этапе теряется больше всего покупателей? | Question is unclear or unsupported. | INVALID:unsupported_metric | - | NOT_SUPPORTED | no | no | unsupported_metric |
| Какие товары имеют низкую конверсию? | Question is unclear or unsupported. | INVALID:unsupported_metric | - | NOT_SUPPORTED | no | no | unsupported_metric |
| Какая комиссия Wildberries? | Question is unclear or unsupported. | INVALID:unsupported_metric | - | NOT_SUPPORTED | no | no | unsupported_metric |
| Сколько потратили на логистику? | Question is unclear or unsupported. | INVALID:unsupported_metric | - | NOT_SUPPORTED | no | no | unsupported_metric |
| Какие товары самые прибыльные? | Question is unclear or unsupported. | INVALID:unsupported_metric | - | NOT_SUPPORTED | no | no | unsupported_metric |
| Какие товары самые убыточные? | Question is unclear or unsupported. | INVALID:unsupported_metric | - | NOT_SUPPORTED | no | no | unsupported_metric |
| Из чего складывается прибыль? | Question is unclear or unsupported. | INVALID:unsupported_metric | - | NOT_SUPPORTED | no | no | unsupported_metric |
| Сравни последние 30 дней с предыдущими 30 днями. | Question is unclear or unsupported. | INVALID:unsupported_metric | - | NOT_SUPPORTED | no | no | unsupported_metric |
| Какие показатели изменились сильнее всего? | Question is unclear or unsupported. | INVALID:unsupported_metric | - | NOT_SUPPORTED | no | no | unsupported_metric |
| Какие товары выросли? | Question is unclear or unsupported. | INVALID:unsupported_metric | - | NOT_SUPPORTED | no | no | unsupported_metric |
| Какие товары упали? | Question is unclear or unsupported. | INVALID:unsupported_metric | - | NOT_SUPPORTED | no | no | unsupported_metric |
| Что изменилось за неделю? | Question is unclear or unsupported. | INVALID:unsupported_metric | - | NOT_SUPPORTED | no | no | unsupported_metric |
| Какие товары находятся в зоне риска? | Question is unclear or unsupported. | INVALID:unsupported_metric | - | NOT_SUPPORTED | no | no | unsupported_metric |
| На что мне стоит обратить внимание? | Question is unclear or unsupported. | INVALID:unsupported_metric | - | NOT_SUPPORTED | no | no | unsupported_metric |
| Есть ли критические проблемы? | Question is unclear or unsupported. | INVALID:unsupported_metric | - | NOT_SUPPORTED | no | no | unsupported_metric |
| Какие события произошли за последние 30 дней? | Question is unclear or unsupported. | INVALID:unsupported_metric | - | NOT_SUPPORTED | no | no | unsupported_metric |
| Что ухудшилось сильнее всего? | Question is unclear or unsupported. | INVALID:unsupported_metric | - | NOT_SUPPORTED | no | no | unsupported_metric |
| Что происходит в магазине? | Question is unclear or unsupported. | INVALID:unsupported_metric | - | NOT_SUPPORTED | no | no | unsupported_metric |
| Как чувствует себя магазин? | Question is unclear or unsupported. | INVALID:unsupported_metric | - | NOT_SUPPORTED | no | no | unsupported_metric |
| Есть ли проблемы? | Question is unclear or unsupported. | INVALID:unsupported_metric | - | NOT_SUPPORTED | no | no | unsupported_metric |
| Что изменилось за последнее время? | Question is unclear or unsupported. | INVALID:unsupported_metric | - | NOT_SUPPORTED | no | no | unsupported_metric |
| Что мне нужно знать сегодня? | Question is unclear or unsupported. | INVALID:unsupported_metric | - | NOT_SUPPORTED | no | no | unsupported_metric |
| Сделай полный анализ магазина. | Question is unclear or unsupported. | INVALID:unsupported_metric | - | NOT_SUPPORTED | no | no | unsupported_metric |

## 7. Recommended next step

Следующий наиболее важный шаг: убрать оставшиеся raw JSON ответы для `metric_value` и stock metric_value через rule-based templates, начиная с базовых вопросов `Сколько заказов`, `Какая выручка`, `Сколько товаров/остатков`. Это даст максимальный прирост пользовательского качества без изменения router/analytics.
