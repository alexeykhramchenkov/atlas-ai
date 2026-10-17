"""Pure period ratios; an absent denominator is never a measured zero."""
from decimal import Decimal, ROUND_HALF_UP
from ai_chat.analysis.analysis_type.rank import run as rank


def ratio_percent(numerator, denominator):
    if numerator is None or denominator is None:return None
    a,b=Decimal(str(numerator)),Decimal(str(denominator))
    if not a.is_finite() or not b.is_finite() or a<0 or b<0:raise ValueError('Ratio requires finite nonnegative counts')
    if b==0:return None
    return float((a/b*100).quantize(Decimal('0.1'),rounding=ROUND_HALF_UP))


def rank_rates(rows, *, direction='desc', limit=5):
    known=[r for r in rows if r.get('rate_pct') is not None]
    unknown=[r for r in rows if r.get('rate_pct') is None]
    result=rank(rows=known,metric='rate_pct',direction=direction,limit=limit)['rows']
    return result+unknown[:max(0,limit-len(result))]
