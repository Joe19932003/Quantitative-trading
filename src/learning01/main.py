# src/learning01/main.py
from bullet_trade import *
import numpy as np

def initialize(context):
    g.security = '000001.XSHE'   # 平安银行，代码格式为 "sh.600000" 或 "000001.XSHE"? BulletTrade 通常用聚宽代码格式
    # 注意：baostock 内部使用 "sh.600000"，但 BulletTrade 的数据提供器会自动转换，这里用聚宽代码即可
    g.short_ma = 5
    g.long_ma = 20
    # 每天开盘后 5 分钟执行交易
    schedule_function(trade, date_rules.every_day(), time_rules.market_open(minutes=5))

def trade(context, data):
    sec = g.security
    # 获取历史收盘价（返回 numpy 数组）
    closes = history_bars(sec, g.long_ma, '1d', 'close')
    if len(closes) < g.long_ma:
        return
    ma_short = np.mean(closes[-g.short_ma:])
    ma_long = np.mean(closes)
    pos = context.portfolio.positions.get(sec)
    if ma_short > ma_long and (pos is None or pos.amount == 0):
        order_value(sec, context.portfolio.cash)
    elif ma_short < ma_long and pos is not None and pos.amount > 0:
        order_target(sec, 0)