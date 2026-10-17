from collections import defaultdict


def build_followup_answer(action, result, facts):
    rows=result['rows']
    title=lambda r:r.get('title') or r['product_key']
    if action=='priority':
        lines=['📋 Что пополнить первым', '']
        for i,r in enumerate(rows,1):
            state='доступный остаток уже нулевой' if r['stock_qty']==0 else f"{r['stock_qty']:g} шт. · ≈ {round(r['days_left'],1):g} дн."
            lines += [f"{i}. {title(r)}",state, '']
        lines += ['Порядок: сначала нулевой остаток, затем меньший запас в днях. При равном запасе — больше заказов.',
                  'Количество к закупке не рассчитываю: срок поставки неизвестен.']
    elif action=='sizes':
        groups=defaultdict(lambda:defaultdict(float))
        for f in facts:
            name=f.get('size_name') or ('ID размера '+str(f.get('variant_key') or 'не указан'))
            groups[f['product_key']][name]+=float(f.get('quantity') or 0)
        lines=['📏 Остатки по размерам · склады WB','']
        for r in rows:
            lines += [title(r)]
            sizes=groups[r['product_key']]
            lines += [f"• {size}: {qty:g} шт." for size,qty in sorted(sizes.items(),key=lambda item:(0,int(item[0])) if item[0].isdigit() else (1,item[0]))] if sizes else ['Нет детализации на эту дату.']
            lines += ['']
        lines += ['Размеры, отсутствующие в отчёте, не считаю автоматически нулевыми.']
    elif action=='sales':
        groups=defaultdict(list)
        for f in facts:groups[f['product_key']].append(f)
        lines=['📈 Как заказывали эти товары',f"{result['date_from']} — {result['date_to']}",'']
        for r in rows:
            data=groups[r['product_key']]
            orders=sum(float(f.get('orders_count') or 0) for f in data)
            cancelled=sum(float(f.get('cancelled_orders_count') or 0) for f in data)
            lines += [title(r), f"Заказы: {orders:g} · отмены: {cancelled:g} · без отмен: {orders-cancelled:g}"]
            dates=[f"{f['snapshot_date'][5:]}: {float(f.get('orders_count') or 0)-float(f.get('cancelled_orders_count') or 0):g}" for f in data if float(f.get('orders_count') or 0)>float(f.get('cancelled_orders_count') or 0)]
            lines += [('По дням без отмен: '+', '.join(dates)) if dates else 'Заказов без отмен не было.','']
        lines += ['Это заказы, а не подтверждённые выкупы.']
    else:raise ValueError('Unknown stock followup')
    lines += [f"Остатки на {result['snapshot_date'][:10]}."]
    if result.get('stale'):lines+=['⚠️ Архивный срез.']
    return '\n'.join(lines)
