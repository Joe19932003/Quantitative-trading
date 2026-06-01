# 克隆自聚宽文章：https://www.joinquant.com/post/68972
# 标题：2018-2025年化收益率96%小市值策略，适合小资金量
# 作者：别亏

# 多策略组合文件
# 由以下策略合并而成：
# - 策略1 (50%): 优化概念动量的小市值量化策略 (65382) - 作者：潮汐量化
# - 策略2 (50%): 涨停基因小市值优化策略 (64877) - 作者：Loylee
# 生成时间：2026-03-25

from jqdata import *
from jqfactor import *
import numpy as np
import pandas as pd
from datetime import time
import datetime
import math


# ============================================================
# 初始化函数
# ============================================================
def initialize(context):
    # 开启防未来函数
    set_option('avoid_future_data', True)
    # 设定基准
    set_benchmark('399101.XSHE')
    # 用真实价格交易
    set_option('use_real_price', True)
    # 设置交易成本
    set_order_cost(
        OrderCost(
            open_tax=0,
            close_tax=0.001,
            open_commission=0.0003,
            close_commission=0.0003,
            min_commission=0.5,
        ),
        type="stock",
    )

    # 在 initialize 中增加
    set_slippage(PriceRelatedSlippage(0.02), type='stock')

    # 过滤order中低于error级别的日志
    log.set_level('order', 'error')
    log.set_level('system', 'error')
    log.set_level('strategy', 'debug')

    # 权重配置 - 各策略权重相等
    g.portfolio_value_proportion = [0, 1]

    # 创建子账户
    set_subportfolios([
        SubPortfolioConfig(context.portfolio.starting_cash * g.portfolio_value_proportion[0], 'stock'),
        SubPortfolioConfig(context.portfolio.starting_cash * g.portfolio_value_proportion[1], 'stock'),
    ])

    # ==================== 策略2 全局变量 ====================
    g.s2_no_trading_today_signal = False
    g.s2_pass_april = True
    g.s2_run_stoploss = True
    g.s2_hold_list = []
    g.s2_yesterday_HL_list = []
    g.s2_target_list = []
    g.s2_not_buy_again = []
    g.s2_filter_loss_black = True
    g.s2_loss_black = {}
    g.s2_stock_num = 3
    g.s2_up_price = 30
    g.s2_limit_days_window = 3 * 250
    g.s2_init_stock_count = 1000
    g.s2_reason_to_sell = ''
    g.s2_HV_control = False
    g.s2_HV_duration = 120
    g.s2_HV_ratio = 0.9
    g.s2_stockL = []
    g.s2_no_trading_buy = []
    g.s2_no_trading_hold_signal = False

    # 策略2 (64877) - 周频调仓
    if g.portfolio_value_proportion[1] > 0:
        run_daily(s2_prepare_stock_list, '9:05')
        run_weekly(s2_weekly_adjustment, 1, '10:05')
        run_daily(s2_trade_afternoon, time='10:20')
        run_daily(s2_trade_afternoon, time='14:55')
        run_daily(s2_close_account, '14:50')

# ============================================================
# 策略2: 涨停基因小市值优化策略 (64877)
# ============================================================

# 1-1 准备股票池
def s2_prepare_stock_list(context):
    subportfolio = context.subportfolios[1]
    g.s2_hold_list = []
    for position in list(subportfolio.long_positions.values()):
        stock = position.security
        g.s2_hold_list.append(stock)

    if g.s2_hold_list != []:
        df = get_price(g.s2_hold_list, end_date=context.previous_date, frequency='daily', fields=['close', 'high_limit', 'low_limit'], count=1, panel=False, fill_paused=False)
        df = df[df['close'] == df['high_limit']]
        g.s2_yesterday_HL_list = list(df.code)
    else:
        g.s2_yesterday_HL_list = []

    g.s2_no_trading_today_signal = s2_today_is_between(context)


def s2_get_history_highlimit(context, stock_list, days=3*250, p=0.10):
    df = get_price(
        stock_list,
        end_date=context.previous_date,
        frequency="daily",
        fields=["close", "high_limit"],
        count=days,
        panel=False,
    )
    df = df[df["close"] == df["high_limit"]]
    grouped_result = df.groupby('code').size().reset_index(name='count')
    grouped_result = grouped_result.sort_values(by=["count"], ascending=False)
    result_list = grouped_result["code"].tolist()[:int(len(grouped_result)*p)]
    log.info(f"[策略2]筛选前合计{len(grouped_result)}个，筛选后合计{len(result_list)}个")
    return result_list


def s2_get_start_point(context, stock_list, days=3*250):
    df = get_price(
        stock_list,
        end_date=context.previous_date,
        frequency="daily",
        fields=["open", "low", "close", "high_limit"],
        count=days,
        panel=False,
    )
    stock_start_point = {}
    stock_price_bias = {}
    current_data = get_current_data()
    for code, group in df.groupby('code'):
        group = group.sort_values('time')
        limit_hit_rows = group[group['close'] == group['high_limit']]
        if not limit_hit_rows.empty:
            latest_limit_hit = limit_hit_rows.iloc[-1]
            latest_limit_index = latest_limit_hit.name
            previous_rows = group[group.index <= latest_limit_index].iloc[::-1]
            for idx, row in previous_rows.iterrows():
                if row['close'] < row['open']:
                    stock_start_point[code] = row['low']
                    break
    for code, start_point in stock_start_point.items():
        last_price = current_data[code].last_price
        bias = last_price / start_point
        stock_price_bias[code] = bias
    sorted_list = sorted(stock_price_bias.items(), key=lambda x: x[1], reverse=False)
    return [i[0] for i in sorted_list]


# 1-2 选股模块
def s2_get_stock_list(context):
    final_list = []
    yesterday = context.previous_date
    initial_list = get_all_securities("stock", yesterday).index.tolist()

    initial_list = s2_filter_new_stock(context, initial_list)
    initial_list = s2_filter_kcbj_stock(initial_list)
    initial_list = s2_filter_st_stock(initial_list)
    initial_list = s2_filter_paused_stock(initial_list)

    if g.s2_filter_loss_black:
        initial_list = s2_filter_loss_black(context, initial_list, days=20)

    q = query(
        valuation.code, indicator.eps
    ).filter(
        valuation.code.in_(initial_list)
    ).order_by(
        valuation.market_cap.asc()
    )
    df = get_fundamentals(q)
    initial_list = df['code'].tolist()[:g.s2_init_stock_count]

    initial_list = s2_filter_limitup_stock(context, initial_list)
    initial_list = s2_filter_limitdown_stock(context, initial_list)

    initial_list = s2_get_history_highlimit(context, initial_list, g.s2_limit_days_window)
    initial_list = s2_get_start_point(context, initial_list, g.s2_limit_days_window)

    stock_list = s2_get_stock_industry(initial_list)
    final_list = stock_list[:g.s2_stock_num * 2]
    log.info('[策略2]今日前10:%s' % final_list)

    return final_list


# 1-3 整体调整持仓
def s2_weekly_adjustment(context):
    subportfolio = context.subportfolios[1]
    if g.s2_no_trading_today_signal == False:
        current_data = get_current_data()
        s2_close_no_trading_hold(context)
        g.s2_not_buy_again = []
        g.s2_target_list = s2_get_stock_list(context)
        target_list = g.s2_target_list[:g.s2_stock_num * 2]
        log.info('[策略2]' + str(target_list))

        for stock in g.s2_hold_list:
            if (stock not in target_list) and (stock not in g.s2_yesterday_HL_list) and (current_data[stock].last_price < current_data[stock].high_limit):
                log.info("[策略2]卖出[%s]" % (stock))
                if stock in subportfolio.long_positions:
                    position = subportfolio.long_positions[stock]
                    s2_close_position(position)
            else:
                log.info("[策略2]已持有[%s]" % (stock))

        s2_buy_security(context, target_list)

        for position in list(subportfolio.long_positions.values()):
            stock = position.security
            g.s2_not_buy_again.append(stock)


# 1-4 调整昨日涨停股票
def s2_check_limit_up(context):
    subportfolio = context.subportfolios[1]
    now_time = context.current_dt
    if g.s2_yesterday_HL_list != []:
        for stock in g.s2_yesterday_HL_list:
            if stock in subportfolio.long_positions and subportfolio.long_positions[stock].closeable_amount > -100:
                current_data = get_price(stock, end_date=now_time, frequency='1m', fields=['close', 'high_limit'], skip_paused=False, fq='pre', count=1, panel=False, fill_paused=True)
                if current_data.iloc[0, 0] < current_data.iloc[0, 1]:
                    log.info("[策略2][%s]涨停打开，卖出" % (stock))
                    position = subportfolio.long_positions[stock]
                    s2_close_position(position)
                    g.s2_reason_to_sell = 'limitup'
                else:
                    log.info("[策略2][%s]涨停，继续持有" % (stock))


# 1-5 如果昨天有股票卖出，剩余的金额今天早上买入
def s2_check_remain_amount(context):
    subportfolio = context.subportfolios[1]
    if g.s2_reason_to_sell == 'limitup':
        g.s2_hold_list = []
        for position in list(subportfolio.long_positions.values()):
            stock = position.security
            g.s2_hold_list.append(stock)
        if len(g.s2_hold_list) < g.s2_stock_num:
            target_list = s2_get_stock_list(context)
            target_list = s2_filter_not_buy_again(target_list)
            target_list = target_list[:min(g.s2_stock_num, len(target_list))]
            log.info('[策略2]有余额可用' + str(round((subportfolio.available_cash), 2)) + '元。' + str(target_list))
            s2_buy_security(context, target_list)
        g.s2_reason_to_sell = ''
    else:
        g.s2_reason_to_sell = ''


# 1-6 下午检查交易
def s2_trade_afternoon(context):
    if g.s2_no_trading_today_signal == False:
        s2_check_limit_up(context)
        if g.s2_HV_control == True:
            s2_check_high_volume(context)
        s2_huanshou(context)
        s2_check_remain_amount(context)


# 3-2 调整放量股票
def s2_check_high_volume(context):
    subportfolio = context.subportfolios[1]
    current_data = get_current_data()
    for stock in subportfolio.long_positions:
        if current_data[stock].paused == True:
            continue
        if current_data[stock].last_price == current_data[stock].high_limit:
            continue
        if subportfolio.long_positions[stock].closeable_amount == 0:
            continue
        df_volume = get_bars(stock, count=g.s2_HV_duration, unit='1d', fields=['volume'], include_now=True, df=True)
        if df_volume['volume'].values[-1] > g.s2_HV_ratio * df_volume['volume'].values.max():
            position = subportfolio.long_positions[stock]
            r = s2_close_position(position)
            log.info(f"[策略2][{stock}]天量，卖出, close_position: {r}")
            g.s2_reason_to_sell = 'limitup'


# 策略2 过滤函数
def s2_filter_paused_stock(stock_list):
    current_data = get_current_data()
    return [stock for stock in stock_list if not current_data[stock].paused]


def s2_filter_st_stock(stock_list):
    current_data = get_current_data()
    return [stock for stock in stock_list
            if not current_data[stock].is_st
            and 'ST' not in current_data[stock].name
            and '*' not in current_data[stock].name
            and '退' not in current_data[stock].name]


def s2_filter_kcbj_stock(stock_list):
    for stock in stock_list[:]:
        if stock[0] == '4' or stock[0] == '8' or stock[:2] == '68':
            stock_list.remove(stock)
    return stock_list


def s2_filter_limitup_stock(context, stock_list):
    subportfolio = context.subportfolios[1]
    last_prices = history(1, unit='1m', field='close', security_list=stock_list)
    current_data = get_current_data()
    return [stock for stock in stock_list if stock in subportfolio.long_positions
            or last_prices[stock][-1] < current_data[stock].high_limit]


def s2_filter_limitdown_stock(context, stock_list):
    subportfolio = context.subportfolios[1]
    last_prices = history(1, unit='1m', field='close', security_list=stock_list)
    current_data = get_current_data()
    return [stock for stock in stock_list if (stock in subportfolio.long_positions
            or last_prices[stock][-1] > current_data[stock].low_limit)]


def s2_filter_new_stock(context, stock_list):
    yesterday = context.previous_date
    return [stock for stock in stock_list if not yesterday - get_security_info(stock).start_date < datetime.timedelta(days=375)]


def s2_filter_not_buy_again(stock_list):
    return [stock for stock in stock_list if stock not in g.s2_not_buy_again]


def s2_filter_loss_black(context, stock_list, days=20):
    result_list = []
    for stock in stock_list:
        if (
            stock in g.s2_loss_black.keys()
            and context.current_dt - g.s2_loss_black[stock]
            < datetime.timedelta(days=days)
        ):
            log.info(
                f"[策略2]{stock}由于近期止损被过滤, 止损时间：{g.s2_loss_black[stock]}"
            )
            continue
        result_list.append(stock)
    return result_list


def s2_get_stock_industry(stock):
    result = get_industry(security=stock)
    selected_stocks = []
    industry_list = []
    for stock_code, info in result.items():
        industry_name = info['sw_l2']['industry_name']
        if industry_name not in industry_list:
            industry_list.append(industry_name)
            selected_stocks.append(stock_code)
            if len(industry_list) == 10:
                break
    return selected_stocks


# 策略2 换手率计算
def s2_huanshoulv(context, stock, is_avg=False):
    if is_avg:
        start_date = context.current_dt - datetime.timedelta(days=20)
        end_date = context.previous_date
        df_volume = get_price(stock, end_date=end_date, frequency='daily', fields=['volume'], count=20)
        df_cap = get_valuation(stock, end_date=end_date, fields=['circulating_cap'], count=1)
        circulating_cap = df_cap['circulating_cap'].iloc[0] if not df_cap.empty else 0
        if circulating_cap == 0:
            return 0.0
        df_volume['turnover_ratio'] = df_volume['volume'] / (circulating_cap * 10000)
        return df_volume['turnover_ratio'].mean()
    else:
        date_now = context.current_dt
        df_vol = get_price(stock, start_date=date_now.date(), end_date=date_now, frequency='1m', fields=['volume'],
                           skip_paused=False, fq='pre', panel=True, fill_paused=False)
        volume = df_vol['volume'].sum()
        date_pre = context.previous_date
        df_circulating_cap = get_valuation(stock, end_date=date_pre, fields=['circulating_cap'], count=1)
        circulating_cap = df_circulating_cap['circulating_cap'].iloc[0] if not df_circulating_cap.empty else 0
        if circulating_cap == 0:
            return 0.0
        turnover_ratio = volume / (circulating_cap * 10000)
        return turnover_ratio


def s2_huanshou(context):
    subportfolio = context.subportfolios[1]
    current_data = get_current_data()
    shrink, expand = 0.003, 0.1
    for stock in subportfolio.long_positions:
        if current_data[stock].paused == True:
            continue
        if current_data[stock].last_price >= current_data[stock].high_limit * 0.97:
            continue
        if subportfolio.long_positions[stock].closeable_amount == 0:
            continue
        rt = s2_huanshoulv(context, stock, False)
        avg = s2_huanshoulv(context, stock, True)
        if avg == 0:
            continue
        r = rt / avg
        action, icon = '', ''
        if avg < 0.003:
            action, icon = '缩量', ''
        elif rt > expand and r > 2:
            action, icon = '放量', ''
        if action:
            position = subportfolio.long_positions[stock]
            r = s2_close_position(position)
            log.info(f"[策略2]{action} {stock} {get_security_info(stock).display_name} 换手率:{rt:.2%}->均:{avg:.2%} 倍率:{r:.1f}x {icon} close_position: {r}")
            g.s2_reason_to_sell = 'limitup'


# 策略2 交易模块
def s2_order_target_value_(security, value):
    return order_target_value(security, value, pindex=1)


def s2_open_position(security, value):
    order = s2_order_target_value_(security, value)
    if order != None and order.filled > 0:
        return True
    return False


def s2_close_position(position):
    security = position.security
    order = s2_order_target_value_(security, 0)
    if order != None:
        if order.status == OrderStatus.held and order.filled == order.amount:
            return True
    return False


def s2_buy_security(context, target_list, cash=0, buy_number=0):
    subportfolio = context.subportfolios[1]
    position_count = len(subportfolio.long_positions)
    target_num = g.s2_stock_num
    if cash == 0:
        cash = subportfolio.total_value
    if buy_number == 0:
        buy_number = target_num
    bought_num = 0
    print('[策略2]---------------------buy_number：%s' % buy_number)
    if target_num > position_count:
        value = cash / (target_num)
        for stock in target_list:
            # 修复：不在持仓中的股票才买入
            if stock not in subportfolio.long_positions:
                if bought_num < buy_number:
                    if s2_open_position(stock, value):
                        g.s2_not_buy_again.append(stock)
                        bought_num += 1
                        if len(subportfolio.long_positions) == target_num:
                            break


# 策略2 判断是否为空仓期
def s2_today_is_between(context):
    today = context.current_dt.strftime('%m-%d')
    if g.s2_pass_april is True:
        if (('04-01' <= today) and (today <= '04-30')) or (('01-01' <= today) and (today <= '01-30')):
            return True
        else:
            return False
    else:
        return False


# 策略2 清仓后次日资金可转
def s2_close_account(context):
    subportfolio = context.subportfolios[1]
    if g.s2_no_trading_today_signal == True:
        if len(g.s2_hold_list) != 0 and g.s2_no_trading_hold_signal == False:
            for stock in g.s2_hold_list:
                if stock in subportfolio.long_positions:
                    position = subportfolio.long_positions[stock]
                    if s2_close_position(position):
                        log.info("[策略2]卖出[%s]" % (stock))
                    else:
                        log.info("[策略2]卖出[%s]错误！！！！！" % (stock))
            s2_buy_security(context, g.s2_no_trading_buy)
            g.s2_no_trading_hold_signal = True


# 策略2 清仓小市值不交易期间股票
def s2_close_no_trading_hold(context):
    subportfolio = context.subportfolios[1]
    if g.s2_no_trading_hold_signal == True:
        for stock in g.s2_hold_list:
            if stock in subportfolio.long_positions:
                position = subportfolio.long_positions[stock]
                s2_close_position(position)
                log.info("[策略2]卖出[%s]" % (stock))
        g.s2_no_trading_hold_signal = False
