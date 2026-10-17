"""Pure reusable row filtering. No database access or business defaults."""
from decimal import Decimal, InvalidOperation


def run(*, rows, conditions=None, cumulative=None):
    conditions = [] if conditions is None else conditions
    operators = {'eq', 'ne', 'gt', 'gte', 'lt', 'lte', 'in', 'not_in'}
    for condition in conditions:
        if not condition.get('field') or condition.get('operator') not in operators or 'value' not in condition:
            raise ValueError('Invalid filter condition')
    def matches(row, condition):
        field, op, expected = condition['field'], condition['operator'], condition['value']
        actual = row.get(field)
        if actual is None:
            return False
        if op == 'eq': return actual == expected
        if op == 'ne': return actual != expected
        if op == 'in': return actual in expected
        if op == 'not_in': return actual not in expected
        if op == 'gt': return actual > expected
        if op == 'gte': return actual >= expected
        if op == 'lt': return actual < expected
        return actual <= expected
    selected = [row for row in rows if all(matches(row, c) for c in conditions)]
    if cumulative is None:
        return {'rows': selected}
    def number(value):
        if value is None or isinstance(value, bool): raise ValueError('Cumulative values must be known nonnegative numbers')
        try: value = Decimal(str(value))
        except InvalidOperation: raise ValueError('Invalid cumulative number') from None
        if not value.is_finite() or value < 0: raise ValueError('Invalid cumulative number')
        return value
    field = cumulative.get('field')
    share = number(cumulative.get('share'))
    if not field or not 0 < share <= 1: raise ValueError('Invalid cumulative specification')
    prepared = [(number(row.get(field)), str(row.get('product_key', '')), row) for row in selected]
    prepared.sort(key=lambda item: (-item[0], item[1]))
    total = sum((item[0] for item in prepared), Decimal(0))
    result, running = [], Decimal(0)
    if total:
        for amount, _, row in prepared:
            result.append(row); running += amount
            if running >= total * share: break
    return {'rows': result}
