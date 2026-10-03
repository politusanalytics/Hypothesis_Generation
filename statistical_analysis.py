"""Deterministic, two-sided tests using complete aggregate statistics."""
import math
from scipy import stats
from statsmodels.stats.proportion import confint_proportions_2indep


def _alpha(alpha):
    if not 0 < alpha < 1:
        raise ValueError("Anlamlılık düzeyi 0 ile 1 arasında olmalı.")


def _count(value):
    if isinstance(value, bool) or not math.isfinite(float(value)) or float(value) != int(value) or int(value) < 0:
        raise ValueError("Gözlem sayısı negatif olmayan tamsayı olmalı.")
    return int(value)


def _result(method, p, effect, interval, alpha, n_a, n_b, group_a, group_b):
    if group_a == group_b:
        raise ValueError("İki farklı grup seçilmeli.")
    _alpha(alpha)
    if not math.isfinite(p) or not math.isfinite(effect):
        raise ValueError("Test hesaplanamadı; veri varyansını ve kapsamını kontrol edin.")
    return {"method": method, "p_value": float(p), "effect": float(effect),
            "confidence_interval": [float(interval[0]), float(interval[1])],
            "confidence_level": 1 - alpha, "alpha": alpha, "n_a": n_a, "n_b": n_b,
            "group_a": str(group_a), "group_b": str(group_b),
            "decision": "H0 reddedildi" if p < alpha else "H0 reddedilemedi",
            "caveat": "Bağımsız gözlemler varsayılır. Sonuç nedensellik kanıtlamaz; "
                       "H0'ın reddedilememesi eşitliği kanıtlamaz. p-değeri hipotezin doğru olma olasılığı değildir."}


def welch_test(n_a, mean_a, sd_a, n_b, mean_b, sd_b, group_a="A", group_b="B", alpha=0.05):
    """Welch t-test and a confidence interval for mean(B) - mean(A)."""
    _alpha(alpha)
    n_a, n_b = _count(n_a), _count(n_b)
    if min(n_a, n_b) < 2:
        raise ValueError("Her grupta en az iki sayısal gözlem gerekli.")
    if any(v is None or not math.isfinite(float(v)) for v in (mean_a, mean_b, sd_a, sd_b)):
        raise ValueError("Ortalama ve standart sapmalar sonlu olmalı.")
    if sd_a < 0 or sd_b < 0:
        raise ValueError("Standart sapma negatif olamaz.")
    var_a, var_b = sd_a ** 2 / n_a, sd_b ** 2 / n_b
    if var_a + var_b <= 0:
        raise ValueError("İki grubun da varyansı sıfır; Welch testi uygulanamaz.")
    df = (var_a + var_b) ** 2 / (var_a ** 2 / (n_a - 1) + var_b ** 2 / (n_b - 1))
    effect = mean_b - mean_a
    width = stats.t.ppf(1 - alpha / 2, df) * math.sqrt(var_a + var_b)
    test = stats.ttest_ind_from_stats(mean_b, sd_b, n_b, mean_a, sd_a, n_a, equal_var=False)
    result = _result("Welch t-testi", test.pvalue, effect, [effect - width, effect + width],
                     alpha, n_a, n_b, group_a, group_b)
    result.update({"mean_a": float(mean_a), "mean_b": float(mean_b), "df": float(df)})
    return result


def fisher_test(success_a, n_a, success_b, n_b, group_a="A", group_b="B", alpha=0.05):
    """Fisher exact test with a Newcombe interval for rate(B) - rate(A)."""
    _alpha(alpha)
    success_a, n_a, success_b, n_b = map(_count, (success_a, n_a, success_b, n_b))
    if not n_a or not n_b or success_a > n_a or success_b > n_b:
        raise ValueError("Başarı sayıları grup toplamlarıyla tutarlı olmalı; iki grup da dolu olmalı.")
    test = stats.fisher_exact([[success_b, n_b - success_b], [success_a, n_a - success_a]], alternative="two-sided")
    interval = confint_proportions_2indep(success_b, n_b, success_a, n_a,
                                         method="newcomb", compare="diff", alpha=alpha)
    result = _result("Fisher kesin testi", test.pvalue, success_b / n_b - success_a / n_a,
                     interval, alpha, n_a, n_b, group_a, group_b)
    result.update({"rate_a": success_a / n_a, "rate_b": success_b / n_b})
    return result


def hypothesis_report(result):
    low, high = result["confidence_interval"]
    return (f"**{result['method']} — {result['decision']}**\n\n"
            f"H0: İki grubun seçilen metrik açısından farkı yoktur. H1: Fark vardır.\n\n"
            f"p-değeri: **{result['p_value']:.6g}**, α: {result['alpha']:.3g}. "
            f"Gözlem sayıları: A={result['n_a']}, B={result['n_b']}.\n\n"
            f"Etki (B − A): **{result['effect']:.6g}**; "
            f"%{result['confidence_level'] * 100:.0f} güven aralığı: [{low:.6g}, {high:.6g}].\n\n"
            + result["caveat"])


def test_database_groups(query_agent, table, group_column, group_a, group_b,
                         metric, method, success_value=None, filters=None, alpha=0.05):
    """Aggregate the whole selected population, not a LIMIT-truncated sample."""
    if group_a == group_b:
        raise ValueError("İki farklı grup seçilmeli.")
    base = list(filters or []) + [{"column": group_column, "op": "IN", "value": [group_a, group_b]}]
    if method == "welch":
        aggregates = [{"op": "count", "column": metric, "as": "n"},
                      {"op": "avg", "column": metric, "as": "mean"},
                      {"op": "stddev_samp", "column": metric, "as": "sd"}]
    elif method == "fisher":
        aggregates = [{"op": "count", "column": metric, "as": "n"}]
    else:
        raise ValueError("Test welch veya fisher olmalı.")
    plan = {"table": table, "group_by": [group_column], "filters": base, "aggregates": aggregates}
    response = query_agent.execute_plan(plan)
    key = group_column.split(".")[-1]
    records = {row[key]: row for row in response["result"]}
    if group_a not in records or group_b not in records:
        raise ValueError("Seçilen gruplardan biri sorgu kapsamında yok.")
    a, b = records[group_a], records[group_b]
    sql = [response["sql"]]
    if method == "welch":
        result = welch_test(a["n"], a["mean"], a["sd"], b["n"], b["mean"], b["sd"], group_a, group_b, alpha)
    else:
        plan["filters"] = base + [{"column": metric, "op": "EQ", "value": success_value}]
        numerator = query_agent.execute_plan(plan)
        successes = {row[key]: row["n"] for row in numerator["result"]}
        result = fisher_test(successes.get(group_a, 0), a["n"], successes.get(group_b, 0), b["n"],
                             group_a, group_b, alpha)
        sql.append(numerator["sql"])
    result["sql"] = sql
    return result
