Voice-to-Text
переводит голос в текст

Input Normalizer
чистит хаос, опечатки, длинные фразы

LLM Router Fallback
используется только после детерминированного router и возвращает JSON по строгой schema

Context Resolver
понимает "они", "этот товар", "как раньше"

Intent Router
определяет смысл вопроса: explain_change, best, risk, forecast и т.д.

Question Classifier
понимает простой вопрос, сложный, составной, стратегический

Planner
строит plan[] для сложных вопросов

Executor
выполняет план

Metric Adapter
приводит разные метрики к единому формату: value, compare, state, history

Internal Tools
достают конкретные данные

Datasets / Supabase
хранят факты

Analysis Engine
объясняет, сравнивает, ранжирует, прогнозирует

Detector Engine
находит события и проблемы

Action Engine
решает, что делать

Answer Builder
пишет человеческий ответ

LLM Answer Interpreter
переводит готовый structured result в текст, не получает доступ к базе и не считает метрики

Memory Writer
запоминает контекст диалога
