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
    g.portfolio_value_proportion = [1, 0]

    # 创建子账户
    set_subportfolios([
        SubPortfolioConfig(context.portfolio.starting_cash * g.portfolio_value_proportion[0], 'stock'),
    ])

    # ==================== 策略1 全局变量 ====================
    g.s1_signal = ''
    g.s1_no_trading_today_signal = False
    g.s1_pass_january = True
    g.s1_pass_april = True
    g.s1_run_stoploss = True
    g.s1_hold_list = []
    g.s1_yesterday_HL_list = []
    g.s1_target_list = []
    g.s1_not_buy_again = []
    g.s1_stock_num = 3
    g.s1_up_price = 100
    g.s1_reason_to_sell = ''
    g.s1_stoploss_strategy = 3
    g.s1_stoploss_limit = 0.91
    g.s1_stoploss_market = 0.95
    g.s1_HV_control = False
    g.s1_HV_duration = 120
    g.s1_HV_ratio = 0.9
    g.s1_stockL = []
    g.s1_no_trading_buy = ['600036.XSHG', '518880.XSHG', '600900.XSHG']
    g.s1_no_trading_hold_signal = False
    g.s1_performance_data = {
        'net_values': {},
        'transactions': [],
        'start_value': 0,
    }

    # ==================== 注册定时任务 ====================
    # 策略1 (65382) - 双周调仓
    if g.portfolio_value_proportion[0] > 0:
        run_daily(s1_prepare_stock_list, '9:05')
        run_weekly(s1_weekly_adjustment, 2, '10:30')
        run_daily(s1_sell_stocks, time='10:00')
        run_daily(s1_trade_afternoon, time='14:25')
        run_daily(s1_trade_afternoon, time='14:55')
        run_daily(s1_close_account, '14:50')


# ============================================================
# 策略1: 优化概念动量的小市值量化策略 (65382)
# ============================================================

# 1-1 准备股票池
def s1_prepare_stock_list(context):
    subportfolio = context.subportfolios[0]
    g.s1_hold_list = []
    for position in list(subportfolio.long_positions.values()):
        stock = position.security
        g.s1_hold_list.append(stock)

    if g.s1_hold_list != []:
        df = get_price(g.s1_hold_list, end_date=context.previous_date, frequency='daily', fields=['close', 'high_limit', 'low_limit'], count=1, panel=False, fill_paused=False)
        df = df[df['close'] == df['high_limit']]
        g.s1_yesterday_HL_list = list(df.code)
    else:
        g.s1_yesterday_HL_list = []

    g.s1_no_trading_today_signal = s1_today_is_between(context)


# 1-2 选股模块
def s1_get_stock_list(context):
    final_list = []
    MKT_index = '399101.XSHE'

    initial_list = get_index_stocks(MKT_index)
    initial_list = s1_filter_new_stock(context, initial_list)
    initial_list = s1_filter_kcbj_stock(initial_list)
    initial_list = s1_filter_st_stock(initial_list)
    initial_list = s1_filter_paused_stock(initial_list)

    q = query(valuation.code).filter(valuation.code.in_(initial_list)).order_by(valuation.circulating_market_cap.asc()).limit(200)
    initial_list = list(get_fundamentals(q).code)

    initial_list = s1_filter_limitup_stock(context, initial_list)
    initial_list = s1_filter_limitdown_stock(context, initial_list)

    q = query(valuation.code, indicator.eps).filter(valuation.code.in_(initial_list)).order_by(valuation.market_cap.asc())
    df = get_fundamentals(q)
    stock_list = list(df.code)
    stock_list = stock_list[:100]

    stock_list = s1_get_concept_stock_list(context, stock_list)
    final_list = stock_list[:g.s1_stock_num * 2]
    log.info('[策略1]今日前10:%s' % final_list)

    return final_list


# 1-3 整体调整持仓
def s1_weekly_adjustment(context):
    subportfolio = context.subportfolios[0]
    if g.s1_no_trading_today_signal == True:
        return
    s1_close_no_trading_hold(context)
    g.s1_not_buy_again = []
    g.s1_target_list = s1_get_stock_list(context)
    target_list = g.s1_target_list[:g.s1_stock_num * 2]
    log.info('[策略1]目标列表: %s' % str(target_list))

    for stock in g.s1_hold_list:
        if (stock not in target_list) and (stock not in g.s1_yesterday_HL_list):
            log.info("[策略1]卖出[%s]" % (stock))
            position = subportfolio.long_positions[stock]
            s1_close_position(position)
        else:
            log.info("[策略1]已持有[%s]" % (stock))

    s1_buy_security(context, target_list)

    for position in list(subportfolio.long_positions.values()):
        stock = position.security
        g.s1_not_buy_again.append(stock)


# 1-4 调整昨日涨停股票
def s1_check_limit_up(context):
    subportfolio = context.subportfolios[0]
    now_time = context.current_dt
    if g.s1_yesterday_HL_list == []:
        return
    for stock in g.s1_yesterday_HL_list:
        if stock in subportfolio.long_positions and subportfolio.long_positions[stock].closeable_amount > -100:
            current_data = get_price(stock, end_date=now_time, frequency='1m', fields=['close', 'high_limit'], skip_paused=False, fq='pre', count=1, panel=False, fill_paused=True)
            if current_data.iloc[0, 0] < current_data.iloc[0, 1]:
                log.info("[策略1][%s]涨停打开，卖出" % (stock))
                position = subportfolio.long_positions[stock]
                s1_close_position(position)
                g.s1_reason_to_sell = 'limitup'
            else:
                log.info("[策略1][%s]涨停，继续持有" % (stock))


# 1-5 如果昨天有股票卖出，剩余的金额今天早上买入
def s1_check_remain_amount(context):
    subportfolio = context.subportfolios[0]
    if g.s1_reason_to_sell == 'limitup':
        g.s1_hold_list = []
        for position in list(subportfolio.long_positions.values()):
            stock = position.security
            g.s1_hold_list.append(stock)
        if len(g.s1_hold_list) < g.s1_stock_num:
            target_list = s1_get_stock_list(context)
            target_list = s1_filter_not_buy_again(target_list)
            target_list = target_list[:min(g.s1_stock_num, len(target_list))]
            log.info('[策略1]有余额可用' + str(round((subportfolio.available_cash), 2)) + '元。' + str(target_list))
            s1_buy_security(context, target_list)
        g.s1_reason_to_sell = ''
    else:
        g.s1_reason_to_sell = ''


# 1-6 下午检查交易
def s1_trade_afternoon(context):
    if g.s1_no_trading_today_signal == False:
        s1_check_limit_up(context)
        if g.s1_HV_control == True:
            s1_check_high_volume(context)
        s1_huanshou(context)
        s1_check_remain_amount(context)


# 1-7 止盈止损
def s1_sell_stocks(context):
    subportfolio = context.subportfolios[0]
    if g.s1_run_stoploss == False:
        return
    
    if g.s1_stoploss_strategy == 1:
        for stock in list(subportfolio.long_positions.keys()):
            if subportfolio.long_positions[stock].price >= subportfolio.long_positions[stock].avg_cost * 2:
                order_target_value(stock, 0, pindex=0)
                log.debug("[策略1]收益100%止盈,卖出{}".format(stock))
            elif subportfolio.long_positions[stock].price < subportfolio.long_positions[stock].avg_cost * g.s1_stoploss_limit:
                order_target_value(stock, 0, pindex=0)
                log.debug("[策略1]收益止损,卖出{}".format(stock))
                g.s1_reason_to_sell = 'stoploss'
    elif g.s1_stoploss_strategy == 2:
        stock_df = get_price(security=get_index_stocks('399101.XSHE'), end_date=context.previous_date, frequency='daily', fields=['close', 'open'], count=1, panel=False)
        down_ratio = (stock_df['close'] / stock_df['open']).mean()
        if down_ratio <= g.s1_stoploss_market:
            g.s1_reason_to_sell = 'stoploss'
            log.debug("[策略1]大盘惨跌,平均降幅{:.2%}".format(down_ratio))
            for stock in list(subportfolio.long_positions.keys()):
                order_target_value(stock, 0, pindex=0)
    elif g.s1_stoploss_strategy == 3:
        stock_df = get_price(security=get_index_stocks('399101.XSHE'), end_date=context.previous_date, frequency='daily', fields=['close', 'open'], count=1, panel=False)
        down_ratio = (stock_df['close'] / stock_df['open']).mean()
        if down_ratio <= g.s1_stoploss_market:
            g.s1_reason_to_sell = 'stoploss'
            log.debug("[策略1]大盘惨跌,平均降幅{:.2%}".format(down_ratio))
            for stock in list(subportfolio.long_positions.keys()):
                order_target_value(stock, 0, pindex=0)
        else:
            for stock in list(subportfolio.long_positions.keys()):
                if subportfolio.long_positions[stock].price < subportfolio.long_positions[stock].avg_cost * g.s1_stoploss_limit:
                    order_target_value(stock, 0, pindex=0)
                    log.debug("[策略1]收益止损,卖出{}".format(stock))
                    g.s1_reason_to_sell = 'stoploss'


# 3-2 调整放量股票
def s1_check_high_volume(context):
    subportfolio = context.subportfolios[0]
    current_data = get_current_data()
    for stock in subportfolio.long_positions:
        if current_data[stock].paused == True:
            continue
        if current_data[stock].last_price == current_data[stock].high_limit:
            continue
        if subportfolio.long_positions[stock].closeable_amount == 0:
            continue
        df_volume = get_bars(stock, count=g.s1_HV_duration, unit='1d', fields=['volume'], include_now=True, df=True)
        if df_volume['volume'].values[-1] > g.s1_HV_ratio * df_volume['volume'].values.max():
            log.info("[策略1][%s]天量，卖出" % stock)
            position = subportfolio.long_positions[stock]
            s1_close_position(position)


# 策略1 过滤函数
def s1_filter_paused_stock(stock_list):
    current_data = get_current_data()
    return [stock for stock in stock_list if not current_data[stock].paused]


def s1_filter_st_stock(stock_list):
    current_data = get_current_data()
    return [stock for stock in stock_list
            if not current_data[stock].is_st
            and 'ST' not in current_data[stock].name
            and '*' not in current_data[stock].name
            and '退' not in current_data[stock].name]


def s1_filter_kcbj_stock(stock_list):
    for stock in stock_list[:]:
        if stock[0] == '4' or stock[0] == '8' or stock[:2] == '68' or stock[:2] == '30':
            stock_list.remove(stock)
    return stock_list


def s1_filter_limitup_stock(context, stock_list):
    subportfolio = context.subportfolios[0]
    last_prices = history(1, unit='1m', field='close', security_list=stock_list)
    current_data = get_current_data()
    return [stock for stock in stock_list if stock in subportfolio.long_positions
            or last_prices[stock][-1] < current_data[stock].high_limit]


def s1_filter_limitdown_stock(context, stock_list):
    subportfolio = context.subportfolios[0]
    last_prices = history(1, unit='1m', field='close', security_list=stock_list)
    current_data = get_current_data()
    return [stock for stock in stock_list if (stock in subportfolio.long_positions
            or last_prices[stock][-1] > current_data[stock].low_limit)]


def s1_filter_new_stock(context, stock_list):
    yesterday = context.previous_date
    return [stock for stock in stock_list if not yesterday - get_security_info(stock).start_date < datetime.timedelta(days=375)]


def s1_filter_not_buy_again(stock_list):
    return [stock for stock in stock_list if stock not in g.s1_not_buy_again]


# 策略1 换手率计算
def s1_huanshoulv(context, stock, is_avg=False):
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


def s1_huanshou(context):
    subportfolio = context.subportfolios[0]
    current_data = get_current_data()
    shrink, expand = 0.003, 0.1
    for stock in subportfolio.long_positions:
        if current_data[stock].paused == True:
            continue
        if current_data[stock].last_price >= current_data[stock].high_limit * 0.97:
            continue
        if subportfolio.long_positions[stock].closeable_amount == 0:
            continue
        rt = s1_huanshoulv(context, stock, False)
        avg = s1_huanshoulv(context, stock, True)
        if avg == 0:
            continue
        r = rt / avg
        action, icon = '', ''
        if avg < 0.003:
            action, icon = '缩量', ''
        elif rt > expand and r > 2:
            action, icon = '放量', ''
        if action:
            log.info(f"[策略1]{action} {stock} {get_security_info(stock).display_name} 换手率:{rt:.2%}->均:{avg:.2%} 倍率:{r:.1f}x {icon}")
            position = subportfolio.long_positions[stock]
            s1_close_position(position)
            g.s1_reason_to_sell = 'limitup'


# 策略1 交易模块
def s1_order_target_value_(security, value):
    return order_target_value(security, value, pindex=0)


def s1_open_position(security, value):
    order = s1_order_target_value_(security, value)
    if order != None and order.filled > 0:
        return True
    return False


def s1_close_position(position):
    security = position.security
    order = s1_order_target_value_(security, 0)
    if order != None:
        if order.status == OrderStatus.held and order.filled == order.amount:
            return True
    return False


def s1_buy_security(context, target_list, cash=0, buy_number=0):
    subportfolio = context.subportfolios[0]
    position_count = len(subportfolio.long_positions)
    target_num = g.s1_stock_num
    if cash == 0:
        cash = subportfolio.total_value
    if buy_number == 0:
        buy_number = target_num
    bought_num = 0
    if target_num > position_count:
        value = cash / (target_num)
        for stock in target_list:
            # 修复：不在持仓中的股票才买入
            if stock not in subportfolio.long_positions:
                if bought_num < buy_number:
                    if s1_open_position(stock, value):
                        g.s1_not_buy_again.append(stock)
                        bought_num += 1
                        if len(subportfolio.long_positions) == target_num:
                            break


# 策略1 判断是否为空仓期
def s1_today_is_between(context):
    today = context.current_dt.strftime('%m-%d')
    if (('01-01' <= today) and (today <= '01-30')):
        if g.s1_pass_january is True:
            return True
        else:
            return False
    elif (('04-01' <= today) and (today <= '04-30')):
        if g.s1_pass_april is True:
            return True
        else:
            return False
    else:
        return False


# 策略1 清仓后次日资金可转
def s1_close_account(context):
    subportfolio = context.subportfolios[0]
    if g.s1_no_trading_today_signal == True:
        if len(g.s1_hold_list) != 0 and g.s1_no_trading_hold_signal == False:
            for stock in g.s1_hold_list:
                if stock in subportfolio.long_positions:
                    position = subportfolio.long_positions[stock]
                    if s1_close_position(position):
                        log.info("[策略1]卖出[%s]" % (stock))
                    else:
                        log.info("[策略1]卖出[%s]错误！！！！！" % (stock))
            s1_buy_security(context, g.s1_no_trading_buy)
            g.s1_no_trading_hold_signal = True


# 策略1 清仓小市值不交易期间股票
def s1_close_no_trading_hold(context):
    subportfolio = context.subportfolios[0]
    if g.s1_no_trading_hold_signal == True:
        for stock in g.s1_hold_list:
            if stock in subportfolio.long_positions:
                position = subportfolio.long_positions[stock]
                s1_close_position(position)
                log.info("[策略1]卖出[%s]" % (stock))
        g.s1_no_trading_hold_signal = False


# 策略1 概念动量相关函数
def s1_calculate_concept_momentum(stock_list, end_date, lookback_days=20):
    if not stock_list:
        return 0
    momentums = []
    for stock in stock_list:
        try:
            df = get_price(stock, end_date=end_date, count=lookback_days, fields=['close'])
            if len(df) >= lookback_days and df['close'].iloc[0] > 0:
                start_price = df['close'].iloc[0]
                end_price = df['close'].iloc[-1]
                stock_momentum = (end_price / start_price - 1) * 100
                momentums.append(stock_momentum)
        except Exception as e:
            continue
    if momentums:
        return np.mean(momentums)
    else:
        return 0


def s1_calculate_concept_momentum_neutralized(stock_list, end_date, lookback_days=20, industry_info=None):
    if not stock_list:
        return 0
    raw_momentum = s1_calculate_concept_momentum(stock_list, end_date, lookback_days)
    if industry_info is None:
        return raw_momentum
    industry_groups = {}
    for stock in stock_list:
        if stock in industry_info:
            industry = industry_info[stock]
            industry_groups.setdefault(industry, []).append(stock)
    industry_momentums = []
    for industry, industry_stocks in industry_groups.items():
        if industry_stocks:
            ind_momentum = s1_calculate_concept_momentum(industry_stocks, end_date, lookback_days)
            industry_momentums.append(ind_momentum)
    if industry_momentums:
        avg_industry_momentum = np.mean(industry_momentums)
        neutralized_momentum = raw_momentum - avg_industry_momentum
        return neutralized_momentum
    return raw_momentum


def s1_get_industry_dict(stock_list, date=None, industry_type='sw_l1'):
    industry_dict = {}
    industry_info = get_industry(stock_list, date=date)
    for stock in stock_list:
        if stock in industry_info:
            if industry_type in industry_info[stock]:
                industry_series = industry_info[stock][industry_type]
                if len(industry_series) > 0:
                    latest_date = max(industry_series.keys())
                    industry_code = industry_series[latest_date]
                    industry_dict[stock] = industry_code
                else:
                    industry_dict[stock] = None
            else:
                industry_dict[stock] = None
        else:
            industry_dict[stock] = None
    return industry_dict


def s1_get_concept_stock_list(context, stock_list):
    """根据概念板块热门度选择股票，如果失败则返回原始列表"""
    try:
        log.info("[策略1]根据概念板块热门度选择股票")
        concepts_df = get_concepts()

        if concepts_df is None or concepts_df.empty:
            log.info("[策略1]概念数据为空，使用备选方案")
            return stock_list

        concept_hotness = {}
        end_date = context.previous_date

        for concept_id in concepts_df.index:
            try:
                concept_stocks = get_concept_stocks(concept_id)
                filtered_stocks = [stock for stock in concept_stocks if stock in stock_list]
                if not filtered_stocks:
                    continue
                industry_dict = s1_get_industry_dict(filtered_stocks)
                concept_momentum = s1_calculate_concept_momentum_neutralized(filtered_stocks, end_date, lookback_days=20, industry_info=industry_dict)
                if len(filtered_stocks) > 0:
                    concept_hotness[concept_id] = {
                        'name': concepts_df.loc[concept_id, 'name'],
                        'momentum': concept_momentum,
                        'stocks': filtered_stocks
                    }
            except Exception as e:
                continue

        if not concept_hotness:
            log.info("[策略1]未找到匹配的概念，使用备选方案")
            return stock_list

        sorted_concepts = sorted(
            concept_hotness.items(),
            key=lambda x: x[1]['momentum'],
            reverse=True
        )

        selected_stocks = []
        selected_concepts = []

        for concept_id, concept_info in sorted_concepts:
            if len(selected_concepts) >= 10:
                break
            concept_name = concept_info['name']
            if concept_name not in selected_concepts:
                selected_concepts.append(concept_name)
                concept_stocks = concept_info['stocks']
                if concept_stocks:
                    q = query(
                        valuation.code,
                        valuation.market_cap
                    ).filter(valuation.code.in_(concept_stocks)).order_by(valuation.market_cap.asc())
                    df = get_fundamentals(q)
                    if not df.empty:
                        selected_stock = df['code'].iloc[0]
                        selected_stocks.append(selected_stock)
                        log.info("[策略1]热门概念: %s (动量: %.2f%%), 选择股票: %s" % (concept_name, concept_info['momentum'], selected_stock))

        # 如果概念选股结果为空，返回原始列表
        if not selected_stocks:
            log.info("[策略1]概念选股结果为空，使用备选方案")
            return stock_list

        return selected_stocks

    except Exception as e:
        log.info(f"[策略1]概念选股出错: {e}，使用备选方案")
        return stock_list
