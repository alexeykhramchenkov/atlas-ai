"""Additional seller intents in the existing Router request shape."""
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# number, question, metric, dataset, analysis, entity, default period
QUESTIONS = [
 (1,'Сколько заказов сегодня?','orders_today','orders','metric_value','store',1),
 (2,'Заказов стало больше или меньше, чем на прошлой неделе?','orders_week_change','orders','metric_value','store',7),
 (3,'Какие товары стали заказывать чаще?','orders_growth','orders','best','product',7),
 (4,'У каких товаров сильнее всего упали заказы?','orders_decline','orders','worst','product',7),
 (5,'Какие товары вообще не заказывали за месяц?','zero_orders','orders','worst','product',30),
 (6,'Какие товары пора пополнить?','replenishment_risk','stocks','worst','product',7),
 (7,'На сколько дней хватит остатков этого товара?','stock_days','stocks','metric_value','product',7),
 (8,'Какие размеры скоро закончатся?','size_stock_days','stocks','worst','variant',7),
 (9,'Сколько штук нужно довезти на ближайшие две недели?','replenishment_qty','stocks','best','product',7),
 (10,'Какие товары лежат на складе и почти не продаются?','stagnant_stock','stocks','worst','product',30),
 (14,'Сколько маркетплейс удержал за комиссии, доставку и хранение?','wb_expenses','realization','metric_value','store',30),
 (16,'Сколько потратили на рекламу за неделю?','ads_spend','ads','metric_value','store',7),
 (17,'Какие товары получили заказы из рекламы?','ads_orders','ads','best','product',7),
 (18,'На какие товары тратим рекламу, но заказов нет?','ads_without_orders','ads','worst','product',7),
 (19,'Сколько стоит один заказ из рекламы?','ads_cpo','ads','metric_value','store',7),
 (20,'Какие рекламные кампании стали работать хуже?','ads_decline','ads','worst','store',7),
 (21,'Какие товары смотрят, но не заказывают?','views_without_orders','funnel','worst','product',7),
 (22,'Какие товары добавляют в корзину, но не оформляют заказ?','carts_without_orders','funnel','worst','product',7),
 (23,'У каких товаров упала конверсия?','conversion_decline','funnel','worst','product',7),
 (25,'Что изменилось в заказах после изменения цены?','price_change_orders','prices','metric_value','product',7),
 (26,'Какой процент заказанных товаров выкупают?','buyout_rate','funnel','metric_value','store',7),
 (27,'Какие товары чаще отменяют?','cancelled_orders','orders','best','product',7),
 (28,'Какие товары чаще возвращают?','return_count','sales','best','product',7),
 (29,'На что покупатели чаще всего жалуются в отзывах?','review_complaints','feedbacks','best','product',30),
 (30,'Какой регион даёт больше всего заказов по всему магазину?','regions_store','orders','best','region',7),
]
BY_METRIC={q[2]:q for q in QUESTIONS}
PRODUCT_REQUIRED={'stock_days','size_stock_days','price_change_orders'}


def normalize(text):return ' '.join(text.lower().replace('ё','е').strip().rstrip('?!.').split())


def resolve_seller_question(question, memory, context, *, resolve_explicit, resolve_reference, resolve_registered=None):
    text=normalize(question)
    if re.search(r'\bне\s+(?:нужно\s+|надо\s+|стоит\s+)?(?:пополн|пополня|довоз|довез|закуп)',text):
        return {**context,'question_type':'simple','is_valid_question':False,'error_code':'unsupported_metric','message':'Расчёт товаров, которые не нужно пополнять, пока не поддерживается.'}
    exact=next((q for q in QUESTIONS if normalize(q[1])==text),None)
    aliases={
      'сколько продаж сегодня':'orders_today','сколько было заказов сегодня':'orders_today',
      'сколько денег съела реклама':'ads_spend','сколько потратили на рекламу':'ads_spend',
      'какие товары не заказывают':'zero_orders','какие товары не продавались за месяц':'zero_orders',
      'какие товары заканчиваются':'replenishment_risk','на сколько дней хватит остатков':'stock_days',
      'какие размеры заканчиваются':'size_stock_days','какие его размеры скоро закончатся':'size_stock_days','какие размеры этого товара скоро закончатся':'size_stock_days',
      'какой процент выкупа':'buyout_rate','сколько отмен':'cancelled_orders',
      'куда чаще всего заказывают по всему магазину':'regions_store',
      'какие товары чаще всего возвращают':'return_count',
    }
    metric=exact[2] if exact else aliases.get(text)
    period_followup=bool(re.fullmatch(r'а?\s*за (?:неделю|месяц|\d+ д(?:ня|ней))',text)) and memory.get('last_metric') in BY_METRIC
    if period_followup:metric=memory['last_metric']
    patterns=[(r'^сколько (?:штук )?(?:нужно )?довезти(?: .*)?$','replenishment_qty'),
      (r'^(?:на сколько|насколько) дней хватит (?:этого|его) товара','stock_days'),(r'^(?:на сколько|насколько) дней хватит остатков','stock_days'),
      (r'^какие (?:его |этого товара )?размеры .*(?:законч|заканч)','size_stock_days'),
      (r'^что изменилось .*после изменения цены','price_change_orders')]
    if not metric:
        metric=next((m for pattern,m in patterns if re.search(pattern,text)),None)
    # Same recognized question with an explicit standard period remains supported.
    if not metric:
        base=re.sub(r' за (?:последни[ех] )?(?:неделю|месяц|\d+ д(?:ня|ней))$','',text)
        metric=next((q[2] for q in QUESTIONS if re.sub(r' за (?:неделю|месяц)$','',normalize(q[1]))==base),None)
    if metric is None and ('товар' in text or 'остат' in text) and any(w in text for w in ('законч','заканч','пополн')):
        return None  # Existing deterministic risk route remains unchanged.
    if resolve_registered is not None and not period_followup:
        registered=resolve_registered(question)
        if registered is None and metric is None:return None
        # Keep the existing scalar cancellation intent; this addition ranks products.
        if registered=='cancelled_orders' and metric is None:return None
        metric=metric or registered
    if not metric:return None
    _,_,_,dataset,analysis,entity,days=BY_METRIC[metric]
    if re.search(r'за (?:последни[ех] )?месяц',text):days=30
    elif re.search(r'за (?:последни[ех] )?неделю',text):days=7
    else:
        numeric_period=re.search(r'за (\d+) д(?:ня|ней)',text)
        if numeric_period:days=max(1,min(int(numeric_period[1]),90))
    today=datetime.now(ZoneInfo('Europe/Moscow')).date()
    end=today if metric=='orders_today' else today-timedelta(days=1)
    req={**context,'is_valid_question':True,'question_type':'simple','dataset':dataset,'analysis':analysis,
         'metric':metric,'entity':entity,'scope':'store' if entity in {'store','region','campaign'} else 'product',
         'period_days':days,'date_from':(end-timedelta(days=days-1)).isoformat(),'date_to':end.isoformat(),
         'answer_scope':'single' if analysis=='metric_value' else 'top','limit':1 if analysis=='metric_value' else 5}
    product_reference=any(marker in text for marker in ('этого товара','этому товару','его','него'))
    explicit_article=bool(re.search(r'\b\d{6,12}\b',text))
    product_dovoz=metric=='replenishment_qty' and (explicit_article or product_reference or 'для товара' in text)
    if metric in PRODUCT_REQUIRED or product_dovoz:
        # An explicit article/name always wins; memory is only used for a product reference.
        base=normalize(BY_METRIC[metric][1])
        product_text=re.sub(r' за (?:последни[ех] )?(?:неделю|месяц|\d+ д(?:ня|ней))$','',text)
        explicit=not period_followup and (explicit_article or (not product_reference and product_text!=base and product_text not in aliases and metric!='size_stock_days'))
        product=resolve_explicit(question) if explicit else None
        if not explicit:product=resolve_reference('этот товар' if period_followup or metric=='size_stock_days' else question,memory)
        if not product or not product.get('product_key'):
            return {**req,'is_valid_question':False,'error_code':'unclear_question','message':'По какому товару? Напиши название или артикул WB.'}
        req.update(product_key=product['product_key'],product=product)
        if product.get('match_type')=='memory' and not re.search(r'за (?:последни[ех] )?(?:неделю|месяц|\d+ д(?:ня|ней))',text):
            for k in ('date_from','date_to'):
                if memory.get(k):req[k]=memory[k]
            from datetime import date
            req['period_days']=(date.fromisoformat(req['date_to'])-date.fromisoformat(req['date_from'])).days+1
    return req
