# src/learning01/main.py
from jqdata import *

def initialize(context):
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)
    g.security = '000001.XSHE'
    g.short_ma = 5
    g.long_ma = 20
    run_daily(trade, time='9:35')

def trade(context):
    sec = g.security
    df = attribute_history(sec, g.long_ma, '1d', ['close'])
    if len(df) < g.long_ma:
        return
    ma_short = df['close'][-g.short_ma:].mean()
    ma_long = df['close'].mean()
    pos = context.portfolio.positions.get(sec)
    if ma_short > ma_long and (pos is None or pos.total_amount == 0):
        order_value(sec, context.portfolio.available_cash)
    elif ma_short < ma_long and pos is not None and pos.total_amount > 0:
        order_target(sec, 0)