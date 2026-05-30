# 基础python联系，择时交易练习# 导入函数库
from jqdata import *
import pandas as pd
import numpy as np

# 初始化函数，设定基准等等
def initialize(context):
    # 设定平安银行股价为基准值
    set_benchmark('000001.XSHG')
    # 开启动态复权模式(真实价格)
    set_option('use_real_price', True)
    # 输出内容到日志 log.info()
    log.info('初始函数开始运行且全局只运行一次')
    # 过滤掉order系列API产生的比error级别低的log
    # log.set_level('order', 'error')

    ### 股票相关设定 ###
    # 股票类每笔交易时的手续费是：买入时佣金万分之三，卖出时佣金万分之三加千分之一印花税, 每笔交易佣金最低扣5块钱
    set_order_cost(OrderCost(close_tax=0.001, open_commission=0.0003, close_commission=0.0003, min_commission=5), type='stock')

    ## 运行函数（reference_security为运行时间的参考标的；传入的标的只做种类区分，因此传入'000300.XSHG'或'510300.XSHG'是一样的）
      # 开盘前运行
    run_daily(before_market_open, time='before_open', reference_security='000300.XSHG')
      # 开盘时运行
    run_daily(market_open, time='open', reference_security='000300.XSHG')
      # 收盘后运行
    run_daily(after_market_close, time='after_close', reference_security='000300.XSHG')

    g.security = '000001.XSHE'
    g.short_period = 5
    g.long_period = 10
    g.cut_off_percent = 0.01 # 当股价的短期均线低于长期均线的10%，则卖出
    g.cut_in_percent = 0.01 # 当股价的短期均线高于长期均线的20%，则买入


## 开盘前运行函数
def before_market_open(context):
    # 输出运行时间
    log.info('函数运行时间(before_market_open):'+str(context.current_dt.time()))


## 开盘时运行函数
def market_open(context):
    log.info('函数运行时间(market_open):'+str(context.current_dt.time()))
    security = g.security
    # 获取股票的收盘价
    close_short_data = get_bars(security, count=g.short_period, unit='1d', fields=['close'])
    close_long_data = get_bars(security, count=g.long_period, unit='1d', fields=['close'])

    # # 取得过去五天的平均价格
    # ema_short = close_short_data['close'].mean()
    # ema_long = close_long_data['close'].mean()

    # 使用 ewm 计算 EMA，span 参数就是均线周期
    # adjust=False 时，直接用公式 EMA_t = α * price_t + (1-α) * EMA_{t-1}
    # 改用EMA计算短期均线和长期均线
    ema_short = pd.Series(close_short_data).ewm(span=g.short_period, adjust=False).mean().iloc[-1]
    ema_long = pd.Series(close_long_data).ewm(span=g.long_period, adjust=False).mean().iloc[-1]

    # 取得当前的现金
    cash = context.portfolio.available_cash

    cut_in_price = (1 + g.cut_in_percent) * ema_long
    cut_off_price = (1 - g.cut_off_percent) * ema_long
    log.info("今日短期均线为{0}, 长期均线为{1}, 当前可用资金为{2}, cut_in_price{3}, cut_off_price{4}".format(ema_short, ema_long, cash, cut_in_price, cut_off_price))
    # 如果短期均线高于长期均线的g.cut_in_percent%, 则全仓买入
    if (ema_short > (1 + g.cut_in_percent) * ema_long) and (cash > 0):
        # 记录这次买入
        log.info("短期均线高于长期均线的 %s%%, 买入 %s" % (g.cut_in_percent*100, security))
        print("当前可用资金为{0}, position_value为{1}".format(cash, context.portfolio.positions_value))
        # 用所有 cash 买入股票
        order_value(security, cash)
    # 如果短期均线低于长期均线的g.cut_off_percent%, 则空仓卖出
    elif (ema_short < (1 - g.cut_off_percent)*ema_long) and (context.portfolio.positions[security].closeable_amount > 0):
        # 记录这次卖出
        log.info("短期均线低于长期均线的 %s%%, 卖出 %s" % (g.cut_off_percent*100, security))
        # 卖出所有股票,使这只股票的最终持有量为0
        order_target(security, 0)

## 收盘后运行函数
def after_market_close(context):
    log.info(str('函数运行时间(after_market_close):'+str(context.current_dt.time())))
    #得到当天所有成交记录
    trades = get_trades()
    for _trade in trades.values():
        log.info('成交记录：'+str(_trade))
    log.info('一天结束')
    log.info('##############################################################')