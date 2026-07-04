# REPORT: Answer Formatting Fix

Дата: 2026-06-29

## Измененные файлы

- `ai_chat/answer_builder/answer.py`
- `REPORT_ANSWER_FORMATTING_FIX.md`

## Где raw JSON попадал в ответ

Финальный ответ формируется в `ai_chat/answer_builder/answer.py` в функции `build_answer`.

Для результатов, у которых не было специального форматтера и не передавался `supabase` для шаблонов, код доходил до fallback:

```python
if supabase is None:
    return _raw_json_answer(...)
```

Из-за этого корректные данные для ranking-сценариев возвращались пользователю как raw JSON.

## Что исправлено

Добавлено безопасное форматирование для типовых результатов, которые уже возвращает аналитика:

- top товаров по заказам: `orders / best / orders_count / product`;
- top товаров по выручке: `orders / best / orders_revenue / product`;
- ranking товаров по остаткам: `stocks / best / stock_qty / product`.

Форматирование:

- не показывает raw JSON;
- использует `product_name` или `title`, если они есть;
- показывает `product_key` после названия;
- если названия нет, использует `product_key`;
- деньги форматируются с `₽`;
- заказы форматируются как `заказов`;
- остатки форматируются как `шт.`;
- в конце добавляется короткий `AI Summary`;
- если строк нет, возвращается честное сообщение, что данные не найдены.

Аналитика, router, SQL, tools и структура данных не изменялись.

## Проверенные вопросы

| question | old problem | new answer | status |
|---|---|---|---|
| У каких товаров больше всего заказов? | raw JSON | Топ товаров по заказам за последние 30 дней с названиями, `product_key`, количеством заказов и `AI Summary` | OK |
| Покажи топ 5 товаров по заказам | raw JSON | Топ-5 товаров по заказам с названиями, `product_key`, количеством заказов и `AI Summary` | OK |
| У каких товаров больше всего выручки? | частичный формат без `product_key` и summary | Топ товаров по выручке за последние 30 дней с названиями, `product_key`, суммой в ₽ и `AI Summary` | OK |
| Какой товар дал больше всего выручки? | частичный формат без `product_key` и summary | Один лидер по выручке с названием, `product_key`, суммой в ₽ и `AI Summary` | OK |
| У какого товара больше всего остатков? | raw JSON | Один товар с максимальным остатком, названием, `product_key`, количеством в шт. и `AI Summary` | OK |
| У каких товаров больше всего остатков? | raw JSON | Топ товаров по остаткам с названиями, `product_key`, количеством в шт. и `AI Summary` | OK |

## Ограничения остались

Не исправлялись и остаются отдельными задачами:

- product overview;
- risks;
- events;
- funnel diagnostics;
- commissions;
- logistics;
- conversion/cart/buyout;
- warehouse logic;
- size logic;
- вопросы про товары, у которых заканчиваются остатки, если router отправляет их не в ranking `best`, а в другой тип анализа.

## Проверка

Проверка выполнена через существующую цепочку:

```text
route(question) -> executor.execute(request) -> build_answer(...)
```

Все шесть обязательных вопросов больше не возвращают raw JSON.
