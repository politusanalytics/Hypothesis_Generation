# System Prompts Architecture & Engineering Guide

This document outlines the organization of system prompts in [`agents/prompts/`] and specifies the necessary additions and review areas for ClickHouse schema compatibility and few-shot guidance.

> **Note on Current State:**
> The system prompts have been centralized into dedicated modules. Newly integrated and adapted prompts should be reviewed and verified to ensure full alignment with database schemas and model execution requirements.

---

## 1. Prompt Modules & Reference Map

The prompt architecture is organized into four functional modules:

```
agents/prompts/
├── domain_prompts.py      # Business logic, marketing dictionary, and heuristic rules
├── query_prompts.py       # SPJQ JSON query generation and SQL agent prefix
├── rewrite_prompts.py     # Contextual threading, intent decomposition, and hypothesis formation
└── synthesis_prompts.py   # CMO executive summaries, scorecards, and predictive insights
```

### A. Domain & Marketing Rules (`domain_prompts.py`)
Encapsulates business and marketing logic to ensure empirical interpretation of SQL results.

* **`MARKETING_CONCEPT_DEFINITIONS`**: Standardizes core consumer journey stages (`Consideration`, `Purchase`, `Recommendation`, `Complaint`) and causal brand health dimensions (`Solution`, `Reason to Believe`, Demographics).
* **`BUSINESS_HEURISTIC_RULES`**: Strategic inference rules instructing the LLM to:
  * Interpret zero/null consideration volume as **top-of-funnel narrowing** rather than "missing data".
  * Resolve trend divergences (e.g., falling recommendations with stable purchases indicate a necessary "Solution" brand).
  * Enforce 3-tier evidence grading: `[Doğrulandı / Demonstrated]`, `[Makul / Plausible]`, `[Desteklenmeyen / Unsupported]`.
* **`get_domain_context_prompt()`**: Injects the marketing dictionary and heuristic rules into downstream synthesis chains.
* **`build_hypothesis_synthesis_prompt()`**: Template for single-hypothesis verification against SQL evidence.

---

### B. Query Planning & SQL Prompts (`query_prompts.py`)
Guides the translation of natural language questions into structured SPJQ (Select-Project-Join-Query) JSON objects.

* **`QUERY_GENERATOR_SYSTEM_PROMPT`**: System prompt providing the SPJQ JSON grammar (`table`, `joins`, `columns`, `aggregates`, `filters`, `group_by`, `order_by`, `limit`) and noise-reduction rules (aggregating `topic_categories`/`products` instead of raw micro-text).
* **`SQL_AGENT_PREFIX`**: System prefix for LangChain's interactive SQL agent (`create_sql_agent`), enforcing operational root cause discovery and demographic JOINs (`is_org = 0`).

---

### C. Rewrite, Threading & Decomposition Prompts (`rewrite_prompts.py`)
Handles conversational context resolution, user clarification, and multi-hypothesis formulation.

* **`CONTEXTUALIZE_QUERY_PROMPT`**: Resolves conversational follow-up questions (e.g., *"How about among women?"*) into self-contained SQL research questions while preserving historical context and filters.
* **`ASSESS_CLARIFICATION_NEED_PROMPT`**: Evaluates query ambiguity and outputs structured interactive clarification options when user requests are too broad.
* **`MACRO_QUESTION_PROMPT`**: Generates a high-level strategic research question based on a summary of database contents.
* **`DECOMPOSE_QUESTION_PROMPT`**: Breaks down a macro strategic question into two targeted SQL sub-questions.
* **`COMPETING_HYPOTHESES_PROMPT`**: Formulates a tri-hypothesis framework in JSON:
  * $H_0$: Null Hypothesis (general market trend / external factor)
  * $H_1$: Primary Hypothesis (internal friction / top-of-funnel collapse)
  * $H_2$: Competing Hypothesis (direct-to-purchase / channel migration)
  alongside 2 SQL verification sub-questions.
* **`PREDICTIVE_TRENDS_PROMPT`**: Decomposes a forecasting request into historical time-series SQL sub-queries.

---

### D. Strategic Synthesis & Executive Insights (`synthesis_prompts.py`)
Transforms raw SQL execution results into executive-level briefings and comparative decision scorecards.

* **`EXECUTIVE_SUMMARY_PROMPT`**: CMO synthesis prompt creating a concise 3–4 sentence executive summary and 1 concrete strategic action.
* **`COMPETING_HYPOTHESES_EVALUATION_PROMPT`**: Econometrician and CMO scorecard prompt producing a comparative Markdown decision table (`[KABUL]`, `[KISMEN]`, `[REDDEDİLDİ]`), concrete metric citations, winning hypothesis analysis, and a 2-point action plan.
* **`PREDICTIVE_INSIGHT_PROMPT`**: Growth strategist prompt projecting future opportunities, risks, and proactive mitigation steps based on time-series evidence.

---

## 2. Necessary Additions & Upgrades

### 1. ClickHouse Schema Compatibility & Semantic Mapping
To ensure accurate query planning against ClickHouse, the system prompts require explicit schema context and querying semantics:

* **Table Purpose Definitions**:
  * `tweets`: Raw post content, creation timestamps, engagement counts, and author identifiers.
  * `tweet_predictions`: Model-predicted classifications including consumer journey stages, sentiment, topics, topic categories, and product mentions.
  * `users`: Account demographic data (e.g., `age_range`, `gender`, `location`, `is_org`).
  * `user_factors`: Aggregated user-level psychographic and behavioral factor scores.
* **Relational Joins & Foreign Keys**:
  * Joining `tweets` with `tweet_predictions` on `tweet_id`.
  * Joining `tweets` with `users` on `tweets.author_id = users.id`.
  * Filtering non-human / organization accounts via `users.is_org = 0`.
* **ClickHouse-Specific Operations**:
  * Querying `Array(String)` columns using `HAS`, `HAS_ANY`, and `HAS_ALL`.
  * Flattening nested arrays using `ARRAY JOIN`.
  * Aggregating distinct array values via `groupArray`.

---

### 2. Few-Shot Example Integration
Adding concrete input-output examples directly inside the prompts ensures consistent formatting and prevents syntax hallucinations:

* **`QUERY_GENERATOR_SYSTEM_PROMPT`**:
  * Examples covering grouped aggregations with ordering and limits (e.g., top complaint categories in a specific timeframe).
  * Examples demonstrating multi-table demographic JOINs with bot exclusion.
  * Examples showing array containment filtering on `consumer_journey` or `topics`.
* **`COMPETING_HYPOTHESES_PROMPT`**:
  * Reference examples mapping ambiguous business observations into distinct $H_0, H_1, H_2$ formulations and valid SQL verification questions.
* **`ASSESS_CLARIFICATION_NEED_PROMPT`**:
  * Examples distinguishing between specific actionable queries (no clarification needed) and broad/vague queries (generating category/product option cards).
