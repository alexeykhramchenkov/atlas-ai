# REPORT: Rule-Based Answer Builder

Дата: 2026-06-29

## 1. Прочитанные документы

Перед изменениями проверены:

- `project_docs/PROJECT_RULES.md`
- `project_docs/ARCHITECTURE.md`
- `project_docs/CONTRACTS.md`
- `project_docs/METRIC_REGISTRY.md`
- `project_docs/ANALYSIS_REGISTRY.md`
- `project_docs/DECISIONS.md`
- `REPORT_ARCHITECTURE_ALIGNMENT.md`

Ключевой принцип из документов: Answer Builder должен быть rule-based. Python отвечает за универсальный renderer, а специфика ответа должна жить в rules/templates.

## 2. system_ai_answer_rules

Живая таблица `system_ai_answer_rules` существует в Supabase, хотя `project_docs/SUPABASE_SCHEMA.md` ее не показывает. Это означает, что schema snapshot устарел или не синхронизирован с текущей базой.

Фактические поля, увиденные через SELECT:

- `id`
- `question_type`
- `template_name`
- `language`
- `title_template`
- `fields`
- `priority`
- `is_active`
- `created_at`
- `updated_at`

До изменений в таблице были только active rules для `lookup_chain`:

- `id=1`, `language=ru`, `template_name=top_product_stock`
- `id=2`, `language=en`, `template_name=top_product_stock`

Для `simple / best / product` правил не было.

## 3. Структура rules

Схема таблицы не менялась. Для новых ranking rules использован существующий JSONB `fields`.

В `fields` теперь поддерживаются служебные элементы:

- `match`: декларативное условие выбора rule;
- `template`: настройки template;
- поля с `path`, `fallback_paths`, `role`, `formatter`, `unit`.

Пример структуры:

```json
[
  {
    "match": {
      "dataset": "orders",
      "analysis": "best",
      "metric": "orders_count",
      "entity": "product"
    }
  },
  {
    "template": {
      "rows_path": "rows",
      "empty_text": "Данных по заказам товаров не найдено.",
      "summary_template": "Больше всего заказов сейчас дают первые товары в рейтинге. Основной лидер — {top_product}."
    }
  },
  {
    "path": "title",
    "fallback_paths": ["product_name", "product_key"],
    "role": "item_label",
    "formatter": "text"
  },
  {
    "path": "product_key",
    "role": "item_label",
    "formatter": "text"
  },
  {
    "path": "orders_count",
    "fallback_paths": ["orders", "value"],
    "role": "item_value",
    "formatter": "number",
    "unit": "заказов"
  }
]
```

Python renderer не знает конкретные значения `orders_count`, `orders_revenue` или `stock_qty`; они находятся в `match` и field paths rules.

## 4. Перенесенные сценарии

Добавлены active Supabase rules:

| id | question_type | template_name | match |
|---:|---|---|---|
| 3 | `simple` | `ranking_list` | `orders / best / orders_count / product` |
| 4 | `simple` | `ranking_list` | `orders / best / orders_revenue / product` |
| 5 | `simple` | `ranking_list` | `stocks / best / stock_qty / product` |

Сценарии теперь проходят через:

```text
execution_result
→ resolve_answer_rule
→ extract fields
→ apply formatters
→ apply ranking_list template
→ final answer
```

## 5. Что изменено в коде

Измененные файлы:

- `ai_chat/answer_builder/answer.py`
- `ai_chat/answer_builder/resolver.py`
- `ai_chat/answer_builder/fields.py`
- `ai_chat/answer_builder/templates.py`
- `REPORT_RULE_BASED_ANSWER_BUILDER.md`

### answer.py

- Rule/template rendering перенесен выше legacy fallback.
- Если `supabase` не передан, Answer Builder лениво использует default `db.client.supabase` для чтения answer rules.
- Удалены hardcoded ветки для:
  - product orders ranking;
  - product revenue ranking;
  - product stock ranking.
- Raw JSON остался только fallback для неподдержанных/сломанных случаев.

### resolver.py

- `resolve_answer_rule` теперь принимает `request` и `result`.
- Resolver читает все active rules для `question_type/language`, сортирует по `priority` и выбирает первое правило, у которого `fields[].match` совпадает с контекстом.
- Убран прежний `.limit(1)`, потому что для одного `question_type=simple` теперь может быть несколько rules.

### fields.py

- Добавлена минимальная поддержка path segment вида `rows[]` для будущих declarative templates.

### templates.py

- Добавлен универсальный `ranking_list` template.
- Template читает из rule:
  - `rows_path`;
  - `empty_text`;
  - `summary_template`;
  - item label/value fields;
  - formatter;
  - unit;
  - fallback paths.

## 6. Проверенные вопросы

Проверка выполнена через:

```text
route(question)
→ executor.execute(request)
→ resolve_answer_rule(...)
→ build_answer(...)
```

| question | rule_id | template | result |
|---|---:|---|---|
| У каких товаров больше всего заказов? | 3 | `ranking_list` | OK, no raw JSON |
| Покажи топ 5 товаров по заказам | 3 | `ranking_list` | OK, no raw JSON |
| У каких товаров больше всего выручки? | 4 | `ranking_list` | OK, no raw JSON |
| Какой товар дал больше всего выручки? | 4 | `ranking_list` | OK, no raw JSON |
| У какого товара больше всего остатков? | 5 | `ranking_list` | OK, no raw JSON |
| У каких товаров больше всего остатков? | 5 | `ranking_list` | OK, no raw JSON |

Данные не изменились:

- top orders лидер: `wb_439996132`, `19 заказов`;
- top revenue лидер: `wb_439996132`, `133 380 ₽`;
- top stock лидер: `wb_236348866`, `123 шт.`.

## 7. Проверки

Синтаксис:

```text
python -m py_compile ai_chat/answer_builder/answer.py ai_chat/answer_builder/resolver.py ai_chat/answer_builder/fields.py ai_chat/answer_builder/templates.py
```

Результат: OK.

Unit tests:

```text
python -m pytest tests/test_answer_builder_explain_change.py
```

Результат: 1 failed, 2 passed.

Падение не связано с rule-based ranking changes. Тест ожидает `Остатки: 0%`, текущий explain_change фактически возвращает `Остатки: 0 шт.`. Этот дефект существовал до текущей задачи и не исправлялся, чтобы не менять explain_change.

## 8. Ограничения остались

- `system_ai_answer_rules` есть в live Supabase, но отсутствует в `SUPABASE_SCHEMA.md`.
- `ranking_list` покрывает только общий список rows; complex narrative templates пока не переносились.
- `explain_change`, `overview` и variant ranking пока остаются legacy deterministic branches.
- Matching rules используют JSON `fields[].match`, потому что текущая таблица не имеет отдельных колонок `dataset`, `analysis`, `metric`, `entity`.
- Router по-прежнему возвращает технические metrics (`orders_count`, `orders_revenue`, `stock_qty`), хотя `METRIC_REGISTRY.md` описывает целевую бизнес-семантику.

## 9. Итог

Три ranking-сценария перенесены с hardcoded Python branches на rule/template mechanism.

Answer Builder стал ближе к целевой архитектуре Atlas:

```text
rules / registry / templates → universal renderer
```

Новые hardcoded branches не добавлялись. Raw JSON fallback оставлен только как аварийный fallback.
