"""Pure ranking of prepared facts; no database, dates or aggregation."""

from decimal import Decimal, InvalidOperation


def run(*, rows, metric, direction="desc", limit=1):
    if not isinstance(metric, str) or not metric:
        raise ValueError("metric is required")
    if direction not in {"asc", "desc"}:
        raise ValueError("direction must be asc or desc")
    if type(limit) is not int or limit < 1:
        raise ValueError("limit must be a positive integer")

    prepared = []
    for row in rows:
        value = row.get(metric)
        if value is None or isinstance(value, bool):
            raise ValueError(f"Missing or invalid ranking value: {metric}")
        try:
            number = Decimal(str(value))
        except (InvalidOperation, ValueError):
            raise ValueError(f"Invalid ranking value: {metric}") from None
        if not number.is_finite():
            raise ValueError(f"Non-finite ranking value: {metric}")
        prepared.append((number, row))
    prepared.sort(key=lambda pair: pair[0], reverse=direction == "desc")

    result = []
    position = 0
    previous = None
    for number, row in prepared:
        if number != previous:
            position += 1
            previous = number
        if position > limit:
            break
        result.append({**row, "rank": position})
    return {"rows": result}
