CONTRACTS.md

Главный принцип

Каждый слой системы имеет фиксированный вход и выход.

Запрещено менять контракт без обновления CONTRACTS.md.

⸻

1. Router Contract

Router получает вопрос пользователя.

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

Примеры:

Почему упали заказы?
→ scope=store

Почему упали заказы у Ангелов?
→ scope=product

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