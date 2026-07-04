# ROADMAP

## Purpose

ROADMAP.md describes implementation order only.

Architecture is defined by:

- PROJECT_RULES.md
- ARCHITECTURE.md
- CONTRACTS.md
- METRIC_REGISTRY.md
- ANALYSIS_REGISTRY.md

If ROADMAP.md conflicts with those documents, the registry/contract documents win.

---

# Current Goal

Build a working end-to-end AI Commerce Analyst.

Target flow:

User
↓
Telegram
↓
Router
↓
Executor
↓
Analysis
↓
Metric Adapter
↓
Internal Tools
↓
Supabase
↓
Answer Builder
↓
User

---

# MVP Scope

Supported Analysis:

- metric_value
- best
- worst
- explain_change

Supported Metrics:

- orders
- views
- cart_rate
- conversion
- stock
- revenue
- profit

Supported Scope:

- store
- product

---

# Priority 1

Explain Change MVP

Goal:

Question:

Почему упали заказы?

should return a real answer.

Required factors:

- views.compare
- cart_rate.compare
- conversion.compare
- stock.state

Deliverable:

Working explain_change for orders.

---

# Priority 2

Metric Adapter

Goal:

Standardize metric access.

Views:

- value
- compare
- state
- history

Tasks:

- orders.compare
- views.compare
- cart_rate.compare
- conversion.compare
- stock.state

---

# Priority 3

Answer Builder

Goal:

Return human-readable answers instead of JSON.

Examples:

- Почему упали заказы?
- Какой товар лучший?
- У какого товара больше всего остатков?

---

# Priority 4

Best / Worst Analysis

Goal:

Support ranking questions.

Examples:

- Какой товар лучший?
- Какой товар худший?
- Какая реклама лучшая?

Rules come from ANALYSIS_REGISTRY.md.

---

# Priority 5

Store vs Product Explain Change

Goal:

Support:

- explain_change.orders.store
- explain_change.orders.product

---

# Future Roadmap

After MVP:

- scale
- risk
- opportunity
- today_actions
- overview
- forecast
- what_if

These analysis types are defined in ANALYSIS_REGISTRY.md but are not part of the current MVP.

---

# Documentation Rule

Any significant architecture change must update:

- PROJECT_RULES.md
- CONTRACTS.md
- METRIC_REGISTRY.md
- ANALYSIS_REGISTRY.md

before implementation.
