# Prompt and analysis architecture

All natural-language SQL plans use the actual schema catalog from `database.py`.
ClickHouse metadata comes from DESCRIBE TABLE on the configured allowlist. SQLite
metadata comes from the explicitly selected read-only local database. No sample
records are included in the query-generation schema prompt.

`agents/prompts/query_prompts.py` defines the supported JSON grammar and receives
`schema` and `dialect`. `rewrite_prompts.py` provides schema-aware question rewriting
and decomposition. There are no forced legacy table joins or fixed research years.
Malformed hypothesis drafts raise an error instead of fabricating fallback questions.

Every plan passes through `agents/query_validation.py`; `agents/sql_compiler.py`
then emits only SELECT. Validation covers identifiers, actual tables/columns,
JOIN equality objects, operators and values, aliases, nested membership subqueries,
limits and the supported day/week/month time buckets. `QueryAgent.execute_plan`
also validates user-configured statistical and forecasting queries. The legacy
executor delegates natural language to QueryAgent rather than accepting raw SQL.

Hypothesis mode computes Welch/Fisher tests and confidence intervals in
`statistical_analysis.py`. Marketing prompts cannot override p-values or H0 decisions.
The UI asks users to specify the contrast and affirm independent observations.
Narrative causal alternatives are not assigned invented support percentages.

Forecasting is computed by the state-space local linear trend model in
`forecasting.py`. The final periods are held out chronologically, MAE/RMSE and
last-value baseline error are reported, then the final model is fitted to the full
history. Prediction intervals come from the model, not an LLM. LLM synthesis methods
reject uncomputed hypothesis/forecast evidence.

Domain prompts distinguish measured facts from interpretations. Missing results
and zero volume cannot, on their own, prove funnel narrowing or causality.

Application logs retain operational metadata only; queries, filter values,
records and tracebacks are omitted. See README.md for local setup and privacy details.
