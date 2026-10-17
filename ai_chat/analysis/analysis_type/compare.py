def run(*, current: dict, previous: dict, metrics: list[str]):
    """Compare numeric facts supplied by Executor; no data access or wording."""
    result = {}
    for metric in metrics:
        now, before = current[metric], previous[metric]
        result[metric] = {
            "current": now, "previous": before,
            "change_abs": now - before,
            "change_pct": round((now - before) / before * 100, 1) if before else (0 if now == 0 else None),
        }
    return result


def compare_rows(*, current: list[dict], previous: list[dict], metric: str):
    """Attribute the additive change across the union of product keys."""
    from ai_chat.analysis.analysis_type.rank import run as rank
    now = {row["product_key"]: row for row in current}
    before = {row["product_key"]: row for row in previous}
    rows = []
    for key in sorted(now.keys() | before.keys()):
        a, b = now.get(key, {}), before.get(key, {})
        comparison = run(current={metric:a.get(metric, 0)}, previous={metric:b.get(metric, 0)}, metrics=[metric])[metric]
        rows.append({"product_key":key, "title":a.get("title") or b.get("title") or key, **comparison})
    losses = [row for row in rows if row["change_abs"] < 0]
    gains = [row for row in rows if row["change_abs"] > 0]
    percentage_gains = [row for row in gains if row["change_pct"] is not None]
    zero_baseline_gains = [row for row in gains if row["change_pct"] is None]
    return {"losses":rank(rows=losses, metric="change_pct", direction="asc", limit=max(1,len(losses)))["rows"],
            "gains":rank(rows=percentage_gains, metric="change_pct", direction="desc", limit=max(1,len(percentage_gains)))["rows"] + zero_baseline_gains,
            "loss_total":-sum(row["change_abs"] for row in losses),
            "gain_total":sum(row["change_abs"] for row in gains)}
