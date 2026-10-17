from typing import Any

from ai_chat.answer_builder.fields import extract_path
from ai_chat.answer_builder.formatters import format_value


def apply_template(
    *,
    rule: dict[str, Any],
    fields: list[dict[str, Any]],
    language: str,
    data: dict[str, Any] | None = None,
    request: dict[str, Any] | None = None,
) -> str:
    template_name = rule.get("template_name")

    if template_name == "compact_text":
        return _render_compact(rule, data or {}, request or {}, language)

    if template_name == "top_product_stock":
        return _render_key_value(
            title=rule.get("title_template") or template_name,
            fields=fields,
        )

    if template_name == "ranking_list":
        return _render_ranking_list(
            rule=rule,
            data=data or {},
            request=request or {},
            language=language,
        )

    raise ValueError(f"Unknown answer template: {template_name}")


def _render_key_value(
    *,
    title: str,
    fields: list[dict[str, Any]],
) -> str:
    lines = [title]

    for field in fields:
        lines.extend(
            [
                "",
                f"{field['label']}:",
                field["formatted"],
            ]
        )

    return "\n".join(lines)


def _render_ranking_list(
    *,
    rule: dict[str, Any],
    data: dict[str, Any],
    request: dict[str, Any],
    language: str,
) -> str:
    config = _extract_template_config(rule)
    rows_path = config.get("rows_path") or "rows"
    rows = _extract_optional_path(data, rows_path) or []

    if not rows:
        return config.get("empty_text") or "Данных не найдено."

    title = _render_text_template(
        rule.get("title_template") or config.get("title_template") or "Рейтинг:",
        data=data,
        request=request,
        top_row=rows[0],
    )
    item_fields = _extract_item_fields(rule)

    lines = [title, ""]

    for index, row in enumerate(rows, start=1):
        lines.append(_render_ranking_item(index=index, row=row, fields=item_fields, language=language))

    summary_template = config.get("summary_template")
    if summary_template:
        lines.extend(
            [
                "",
                "AI Summary:",
                _render_text_template(
                    summary_template,
                    data=data,
                    request=request,
                    top_row=rows[0],
                ),
            ]
        )

    return "\n".join(lines)


def _render_ranking_item(
    *,
    index: int,
    row: dict[str, Any],
    fields: list[dict[str, Any]],
    language: str,
) -> str:
    label_parts = []
    value = ""

    for field in fields:
        role = field.get("role")
        formatted = _format_row_field(row=row, field=field, language=language)

        if not formatted or formatted == "—":
            continue

        if role == "item_value":
            unit = field.get("unit")
            value = f"{formatted} {unit}".strip() if unit else formatted
            continue

        label_parts.append(formatted)

    label = " / ".join(label_parts) if label_parts else "—"
    if value:
        return f"{index}. {label} — {value}"

    return f"{index}. {label}"


def _format_row_field(
    *,
    row: dict[str, Any],
    field: dict[str, Any],
    language: str,
) -> str:
    value = _extract_first_row_value(row=row, field=field)

    if value is None:
        return ""

    formatter = field.get("formatter") or "text"
    return format_value(value=value, formatter=formatter, language=language)


def _extract_first_row_value(row: dict[str, Any], field: dict[str, Any]) -> Any:
    paths = []
    path = field.get("path")
    if path:
        paths.append(path)
    paths.extend(field.get("fallback_paths") or [])

    for candidate in paths:
        value = _extract_optional_path(row, candidate)
        if value not in [None, ""]:
            return value

    return None


def _extract_template_config(rule: dict[str, Any]) -> dict[str, Any]:
    for field in rule.get("fields") or []:
        if not isinstance(field, dict):
            continue

        config = field.get("template")
        if isinstance(config, dict):
            return config

    return {}


def _extract_item_fields(rule: dict[str, Any]) -> list[dict[str, Any]]:
    fields = []

    for field in rule.get("fields") or []:
        if not isinstance(field, dict):
            continue

        if field.get("path") and field.get("role"):
            fields.append(field)

    return fields


def _render_text_template(
    template: str,
    *,
    data: dict[str, Any],
    request: dict[str, Any],
    top_row: dict[str, Any],
) -> str:
    values = {
        **{key:value for key,value in data.items() if not isinstance(value,(dict,list))},
        "period_days": request.get("period_days") or data.get("period_days"),
        "top_product": top_row.get("product_key") or top_row.get("title") or top_row.get("product_name"),
    }

    try:
        return str(template).format(**values)
    except (KeyError, ValueError):
        return str(template)


def _extract_optional_path(data: Any, path: str) -> Any:
    try:
        return extract_path(data, path)
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def _render_compact(rule, data, request, language):
    from datetime import date
    config = _extract_template_config(rule)
    status = data.get('status') or 'ok'
    if status != 'ok':
        return (config.get('status_text') or {}).get(status, config.get('empty_text') or 'Недостаточно данных.')
    def value(path, source=data):
        if path.startswith('request.'):
            return _extract_optional_path(request, path.removeprefix('request.'))
        return _extract_optional_path(source, path)
    values = {}
    for field in rule.get('fields') or []:
        if field.get('path') and field.get('label'):
            values[field['label']] = format_value(value=value(field['path']), formatter=field.get('formatter') or 'text', language=language, options=field.get('options'))
    months = ('января','февраля','марта','апреля','мая','июня','июля','августа','сентября','октября','ноября','декабря')
    values['period']=config.get('default_period','')
    for name, prefix in (('period', ''), ('previous_period', 'previous_')):
        if not data.get(prefix+'date_from') or not data.get(prefix+'date_to'):
            continue
        start,end=date.fromisoformat(data[prefix+'date_from']),date.fromisoformat(data[prefix+'date_to'])
        values[name+'_duration']=format_value(value=(end-start).days+1,formatter='days',language=language,options={'decimals':0})
        values[name]=(f"{start.day}–{end.day} {months[end.month-1]}" if (start.year,start.month)==(end.year,end.month)
                          else f"{start.day} {months[start.month-1]} {start.year} — {end.day} {months[end.month-1]} {end.year}")
        if config.get('omit_same_year') and start.year==end.year and start.month!=end.month:
            values[name]=f'{start.day} {months[start.month-1]} — {end.day} {months[end.month-1]}'
    values['period_heading']=''
    if values.get('period'):
        duration=values.get('period_duration')
        values['period_heading']=(' · '+duration if duration else '')+'\n'+values['period']
    elif data.get('as_of'):
        values['period_heading']='\n'+format_value(value=data['as_of'],formatter='date',language=language)
    def noun(n):
        n=int(n);return 'заказ' if n%10==1 and n%100!=11 else 'заказа' if n%10 in (2,3,4) and n%100 not in (12,13,14) else 'заказов'
    if data.get('orders_count') is not None: values['orders_word']=noun(data['orders_count'])
    # Cancellation wording is configured by the existing answer rule, including omission at zero.
    cancelled_path=config.get('cancelled_path') or 'cancelled_orders_count'
    cancelled=value(cancelled_path) or 0
    values['cancelled_count']=format_value(value=cancelled,formatter='number',language=language)
    values['cancellation_line']=(config.get('cancellation_template') or '').format(**values) if cancelled else ''
    rows = value(config.get('rows_path') or 'rows') or []
    items=[]
    grouped_items={}
    for row in rows:
        row_values={}
        for field in config.get('item_fields') or []:
            row_values[field['name']]=format_value(value=value(field['path'],row),formatter=field.get('formatter') or 'text',language=language)
        if row.get('value') is not None:row_values['orders_word']=noun(row['value'])
        row_cancelled=row.get('cancelled_orders_count') or 0
        row_values['cancelled_count']=format_value(value=row_cancelled,formatter='number',language=language)
        row_values['cancellation_note']=(config.get('item_cancellation_template') or '').format(**row_values) if row_cancelled else ''
        if config.get('item_template'):
            line=config['item_template'].format(**row_values)
            if config.get('group_by'):
                group=format_value(value=value(config['group_by'],row),formatter='html_text' if config.get('telegram_format')=='html_bold' else 'text',language=language)
                grouped_items.setdefault(group,[]).append(line)
            else:items.append(line)
    if config.get('group_by'):
        items=[config.get('group_header_template','{group}:').format(group=group)+'\n\n'+'\n'.join(lines) for group,lines in grouped_items.items()]
        values['items']='\n\n'.join(items)
    else:values['items']='\n'.join(items)
    for section in config.get('sections') or []:
        section_items = []
        section_rows = value(section['rows_path']) or []
        if section.get('limit') is not None:section_rows=section_rows[:max(0,int(section['limit']))]
        for row in section_rows:
            item = {field['name']:format_value(value=_extract_first_row_value(row=row,field=field),
                    formatter=field.get('formatter', 'text'), language=language, options=field.get('options'))
                    for field in section['item_fields']}
            if '{orders_word}' in section['item_template']:
                item['orders_word']=noun(row.get('orders_count') if row.get('orders_count') is not None else row.get('value',0))
            section_items.append(section['item_template'].format(**item))
        values[section['name']] = '\n'.join(section_items) or section.get('empty_text', '')
    if rows and rows[0].get('value') is not None:
        n=int(rows[0]['value'])
        values['times_word']='раз' if n%10==1 and n%100!=11 or n%10 not in (2,3,4) or n%100 in (12,13,14) else 'раза'
    values['region_count']=str(len(rows))
    if config.get('item_template') and not rows:
        return config.get('empty_text') or 'Заказов за этот период нет.'
    complete = bool(rows) and sum(float(x.get('value') or 0) for x in rows)==data.get('orders_count')
    values['region_intro']=(config.get('complete_intro') if complete else config.get('partial_intro')) or ''
    values['region_intro']=values['region_intro'].format(**values)
    equal=bool(rows) and all(x.get('value')==rows[0].get('value') for x in rows)
    values['summary']=(config.get('equal_summary') if equal else config.get('ranked_summary')) or ''
    status=data.get('status') or 'ok'
    if status!='ok':return (config.get('status_text') or {}).get(status,config.get('empty_text') or 'Недостаточно данных.')
    return str(rule.get('title_template') or '').format(**values).strip()
