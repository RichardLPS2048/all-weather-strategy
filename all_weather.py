from jqdata import *
import pandas as pd
import numpy as np
import math
import datetime

# -------------------- 运行调度函数 --------------------
def initialize(context):
    set_benchmark("000300.XSHG")
    set_option("avoid_future_data", True)
    set_option("use_real_price", True)
    set_trading_costs()
    log.set_level("order", "error")

    g.portfolio_value_proportion = [1.0]  # 全天候 100%
    g.positions = {0: {}}
    g.daily_holdings = []
    g.strategy_returns = {}

    # 全天候策略调度
    run_daily(all_weather_prepare, "9:10")
    run_daily(all_weather_adjust, "9:35")

    run_daily(check_stop_loss, "14:50")
    run_daily(end_trade, "14:59")
    run_daily(record_daily_holdings, "15:00")

    process_initialize(context)


def process_initialize(context):
    g.strategys = {}
    if g.portfolio_value_proportion[0] > 0:
        g.strategys["全天候策略"] = All_Weather_Strategy(context, index=0, name="全天候策略")
        g.strategy_returns["全天候策略"] = 0.0
        log.info(f"初始化策略: 全天候策略, 资金占比: {g.portfolio_value_proportion[0]*100:.1f}%")


# -------------------- 调度函数 --------------------
def all_weather_prepare(context):
    if "全天候策略" in g.strategys:
        g.strategys["全天候策略"].prepare()


def all_weather_adjust(context):
    if "全天候策略" in g.strategys:
        g.strategys["全天候策略"].adjust()


# -------------------- 全局止损检查 --------------------
def check_stop_loss(context):
    if not hasattr(g, 'strategys') or not g.strategys:
        return
    for strategy_name, strategy in g.strategys.items():
        if hasattr(strategy, 'check_stop_loss'):
            try:
                strategy.check_stop_loss()
            except Exception as e:
                log.error(f"{strategy_name} 止损检查出错: {str(e)}")


# -------------------- 尾盘处理 --------------------
def end_trade(context):
    marked = {s for d in g.positions.values() for s in d}
    for stock in context.portfolio.positions:
        if stock not in marked:
            if order_target_value(stock, 0):
                log.info(f"end_trade清仓未记录持仓: {stock}")


# -------------------- 每日持仓记录 --------------------
def record_daily_holdings(context):
    current_date = context.current_dt.strftime("%Y-%m-%d")
    total_portfolio_value = context.portfolio.total_value
    current_data = get_current_data()

    strategy_holdings = {}
    for strategy_name, strategy in g.strategys.items():
        index = strategy.index
        holdings = g.positions[index]
        strategy_hold_value = 0.0
        stock_details = []

        for stock, amount in holdings.items():
            if stock in context.portfolio.positions:
                pos = context.portfolio.positions[stock]
                price = pos.price
                value = amount * price
                strategy_hold_value += value
                profit = (price - pos.avg_cost) * amount if pos.avg_cost > 0 else 0
                profit_rate = (price - pos.avg_cost) / pos.avg_cost * 100 if pos.avg_cost > 0 else 0

                stock_details.append({
                    "stock_code": stock,
                    "stock_name": current_data[stock].name if stock in current_data else "未知",
                    "hold_amount": amount,
                    "avg_cost": round(pos.avg_cost, 2),
                    "current_price": round(price, 2),
                    "hold_value": round(value, 2),
                    "profit": round(profit, 2),
                    "profit_rate": round(profit_rate, 2)
                })

        strategy_allocated_value = total_portfolio_value * g.portfolio_value_proportion[index]
        strategy_profit = strategy_hold_value - strategy_allocated_value if strategy_allocated_value > 0 else 0
        strategy_profit_rate = strategy_profit / strategy_allocated_value * 100 if strategy_allocated_value > 0 else 0
        g.strategy_returns[strategy_name] += strategy_profit

        strategy_holdings[strategy_name] = {
            "strategy_index": index,
            "allocated_ratio": round(g.portfolio_value_proportion[index] * 100, 1),
            "hold_value": round(strategy_hold_value, 2),
            "hold_ratio": round(strategy_hold_value / total_portfolio_value * 100, 2) if total_portfolio_value > 0 else 0,
            "profit": round(strategy_profit, 2),
            "profit_rate": round(strategy_profit_rate, 2),
            "cumulative_profit": round(g.strategy_returns[strategy_name], 2),
            "stock_details": stock_details
        }

    total_hold_value = sum([s["hold_value"] for s in strategy_holdings.values()])
    total_cash = round(context.portfolio.cash, 2)
    total_profit = round(total_portfolio_value - context.portfolio.starting_cash, 2)
    total_profit_rate = round(total_profit / context.portfolio.starting_cash * 100, 2) if context.portfolio.starting_cash > 0 else 0

    holding_record = {
        "date": current_date,
        "total_portfolio_value": round(total_portfolio_value, 2),
        "total_cash": total_cash,
        "total_hold_value": round(total_hold_value, 2),
        "total_profit": total_profit,
        "total_profit_rate": total_profit_rate,
        "strategy_holdings": strategy_holdings
    }
    g.daily_holdings.append(holding_record)

    log.info(f"\n=== {current_date} 持仓汇总 ===")
    log.info(f"总账户市值: {total_portfolio_value:.2f} | 现金: {total_cash:.2f} | 持仓市值: {total_hold_value:.2f}")
    log.info(f"总收益: {total_profit:.2f} | 总收益率: {total_profit_rate:.2f}%")

    for strategy_name, details in strategy_holdings.items():
        log.info(f"\n【{strategy_name}】")
        log.info(f"  配置占比: {details['allocated_ratio']}% | 实际持仓占比: {details['hold_ratio']}%")
        log.info(f"  持仓市值: {details['hold_value']:.2f} | 当日收益: {details['profit']:.2f} ({details['profit_rate']:.2f}%)")
        log.info(f"  累计收益: {details['cumulative_profit']:.2f}")
        if details["stock_details"]:
            log.info(f"  持仓明细:")
            for stock in details["stock_details"]:
                log.info(f"    {stock['stock_code']}({stock['stock_name']}): 持仓{stock['hold_amount']}股 | 成本{stock['avg_cost']} | 当前{stock['current_price']} | 收益{stock['profit']}({stock['profit_rate']}%)")
        else:
            log.info(f"  持仓明细: 无持仓")

    record(总市值=total_portfolio_value, 现金=total_cash, 持仓市值=total_hold_value, 总收益率=total_profit_rate)
    for name, details in strategy_holdings.items():
        record(**{f"{name}_持仓占比": details["hold_ratio"], f"{name}_收益率": details["profit_rate"]})


# -------------------- 策略基类 --------------------
class Strategy:
    def __init__(self, context, index, name):
        self.context = context
        self.index = index
        self.name = name
        self.stock_sum = 1
        self.hold_list = []
        self.def_stocks = ["511260.XSHG", "518880.XSHG", "512800.XSHG"]
        self.stop_loss_rate = 0.12

        stop_loss_key = f'stop_loss_{self.index}'
        if not hasattr(g, stop_loss_key):
            setattr(g, stop_loss_key, {})
        self.stop_loss_tracking = getattr(g, stop_loss_key)

    def get_total_value(self):
        if not g.positions[self.index]:
            return 0
        return sum(self.context.portfolio.positions[key].price * value for key, value in g.positions[self.index].items())

    def get_min_trade_value(self):
        strategy_total_value = self.context.portfolio.total_value * g.portfolio_value_proportion[self.index]
        if strategy_total_value <= 100000:
            return 2000
        elif strategy_total_value <= 500000:
            ratio = (strategy_total_value - 100000) / 400000
            return int(2000 + ratio * 40000)
        else:
            threshold = strategy_total_value * 0.012
            return min(50000, max(8000, int(threshold)))

    def _adjust(self, targets):
        current_data = get_current_data()
        self.hold_list = list(g.positions[self.index].keys())
        portfolio = self.context.portfolio
        target_value = self.context.portfolio.total_value * g.portfolio_value_proportion[self.index]

        for stock in self.hold_list:
            if stock not in targets:
                self.order_target_value_(stock, 0)

        min_trade_value = self.get_min_trade_value()
        for stock, weight in targets.items():
            target = target_value * weight
            price = current_data[stock].last_price
            value = g.positions[self.index].get(stock, 0) * price
            if value - target > max(min_trade_value, price * 100):
                self.order_target_value_(stock, target)

        for stock, weight in targets.items():
            target = target_value * weight
            price = current_data[stock].last_price
            value = g.positions[self.index].get(stock, 0) * price
            if min(target - value, portfolio.available_cash) > max(min_trade_value, price * 100):
                self.order_target_value_(stock, target)

    def order_target_value_(self, security, value):
        current_data = get_current_data()
        if current_data[security].paused:
            return False
        if current_data[security].last_price == current_data[security].high_limit:
            return False
        if current_data[security].last_price == current_data[security].low_limit:
            return False

        price = current_data[security].last_price
        current_position = g.positions[self.index].get(security, 0)
        target_position = (int(value / price) // 100) * 100 if price != 0 else 0

        if target_position == 0 and value > 0:
            return False

        adjustment = target_position - current_position
        closeable_amount = self.context.portfolio.positions[security].closeable_amount if security in self.context.portfolio.positions else 0
        if adjustment < 0 and closeable_amount == 0:
            return False

        if adjustment != 0:
            o = order(security, adjustment)
            if o:
                if adjustment > 0:
                    price = current_data[security].last_price
                    if security not in self.stop_loss_tracking:
                        self.stop_loss_tracking[security] = price
                filled = o.filled if o.is_buy else -o.filled
                g.positions[self.index][security] = filled + current_position
                if g.positions[self.index][security] == 0:
                    g.positions[self.index].pop(security, None)
                self.hold_list = list(g.positions[self.index].keys())
                return True
        return False

    def filter_basic_stock(self, stock_list):
        current_data = get_current_data()
        return [
            stock for stock in stock_list
            if not current_data[stock].paused
            and not current_data[stock].is_st
            and "ST" not in current_data[stock].name
            and "*" not in current_data[stock].name
            and "退" not in current_data[stock].name
            and not (stock[0] == "4" or stock[0] == "8" or stock[:2] == "68" or stock[:2] == "30")
            and not self.context.previous_date - get_security_info(stock).start_date < datetime.timedelta(375)
        ]

    def filter_limitup_limitdown_stock(self, stock_list):
        current_data = get_current_data()
        return [
            stock for stock in stock_list
            if current_data[stock].last_price < current_data[stock].high_limit
            and current_data[stock].last_price > current_data[stock].low_limit
        ]

    def filter_limitup_stock(self, stock_list, days):
        df = get_price(stock_list, end_date=self.context.previous_date, frequency="daily",
                       fields=["close", "high_limit"], count=days, panel=False)
        df = df[df["close"] == df["high_limit"]]
        filterd_stocks = df.code.drop_duplicates().tolist()
        return [stock for stock in stock_list if stock not in filterd_stocks]

    def check_stop_loss(self):
        if self.stop_loss_rate <= 0:
            return []
        current_data = get_current_data()
        stop_loss_stocks = []
        for stock in list(g.positions[self.index].keys()):
            if current_data[stock].paused:
                continue
            current_price = current_data[stock].last_price
            position = self.context.portfolio.positions[stock]
            if stock not in self.stop_loss_tracking:
                try:
                    hist_data = attribute_history(stock, 20, '1d', ['high'])
                    if not hist_data.empty:
                        self.stop_loss_tracking[stock] = max(position.avg_cost, current_price, hist_data['high'].max())
                    else:
                        self.stop_loss_tracking[stock] = max(position.avg_cost, current_price)
                except:
                    self.stop_loss_tracking[stock] = max(position.avg_cost, current_price)
            else:
                self.stop_loss_tracking[stock] = max(self.stop_loss_tracking[stock], current_price)

            highest_price = self.stop_loss_tracking[stock]
            if current_price <= highest_price * (1 - self.stop_loss_rate):
                stop_loss_stocks.append(stock)

        for stock in stop_loss_stocks:
            if self.order_target_value_(stock, 0):
                del self.stop_loss_tracking[stock]
        return stop_loss_stocks


# -------------------- 全天候策略 --------------------
class All_Weather_Strategy(Strategy):
    def __init__(self, context, index, name):
        super().__init__(context, index, name)

        self.rebalance_threshold = 0.15
        self.etf_allocations = {}
        self.valid_etf_pools = {}
        self.rebalance_price = {}

        self.period_count = 20
        self.cycle_period = 20
        self.trade_threshold = 0.05
        self.min_listing_days = 125
        self.stop_loss_rate = 0

        self.etf_pool_all = {
            "equity": ['510300.XSHG', '159915.XSHE'],
            "commodities": ['518880.XSHG'],
            "bonds": ['161716.XSHE'],
            "foreign_equity": ['513100.XSHG']
        }

        self.equity_etfs = set(self.etf_pool_all.get("equity", [])) | set(self.etf_pool_all.get("foreign_equity", []))

    def get_ES(self, stock, lag=120):
        hStocks = history(lag, '1d', 'close', stock, df=True)
        daily_returns = hStocks.resample('D').last().pct_change().fillna(value=0, method=None, axis=0).iloc[:, 0].values
        sorted_returns = sorted(daily_returns)

        a = 1 - 0.90
        sum_value = 0
        for i in range(len(sorted_returns)):
            if i < (lag * a):
                sum_value += sorted_returns[i]
        ES = -(sum_value / (lag * a)) if lag * a > 0 else 0

        price_data = history(250, '1d', 'close', stock, df=True)
        daily_returns_long = price_data.resample('D').last().pct_change().fillna(value=0, method=None, axis=0).iloc[:, 0].values
        short_vol = pd.Series(daily_returns_long).rolling(10).std().iloc[-1] * np.sqrt(252)
        long_vol = pd.Series(daily_returns_long).std() * np.sqrt(252)
        short_vol = short_vol.item() if isinstance(short_vol, pd.Series) else short_vol
        long_vol = long_vol.item() if isinstance(long_vol, pd.Series) else long_vol
        adjustment_factor = short_vol / long_vol if long_vol > 0 else 1
        ES *= adjustment_factor

        if stock in self.equity_etfs:
            score = self.get_ETF_momentum(stock)
            ES = self.adjust_ES(ES, score)
        return ES

    def get_portfolio_ES(self, asset_class, stock_list, weights, lag=120):
        hStocks = history(lag, '1d', 'close', stock_list, df=True)
        daily_returns = hStocks.resample('D').last().pct_change().fillna(value=0, method=None, axis=0).values
        weight_vector = np.array([weights.get(stock, 0) for stock in stock_list]).reshape(-1, 1)
        portfolio_returns = daily_returns.dot(weight_vector).squeeze()
        sorted_returns = sorted(portfolio_returns)

        a = 1 - 0.90
        sum_value = 0
        for i in range(len(sorted_returns)):
            if i < (lag * a):
                sum_value += sorted_returns[i]
        ES = -(sum_value / (lag * a)) if lag * a > 0 else 0

        price_data = history(250, '1d', 'close', stock_list, df=True)
        daily_returns_long = price_data.resample('D').last().pct_change().fillna(value=0, method=None, axis=0).values
        portfolio_returns_long = np.dot(daily_returns_long, weight_vector).squeeze()
        portfolio_returns_series = pd.Series(portfolio_returns_long)

        short_vol = portfolio_returns_series.rolling(10).std().iloc[-1] * np.sqrt(252)
        long_vol = portfolio_returns_series.std() * np.sqrt(252)
        adjustment_factor = short_vol / long_vol if long_vol > 0 else 1
        ES *= adjustment_factor

        if asset_class in ['equity', 'foreign_equity']:
            score = self.get_portfolio_momentum(stock_list, weights)
            ES = self.adjust_ES(ES, score)
        return ES

    def get_ETF_momentum(self, etf, momentum_day=25):
        df = attribute_history(etf, momentum_day, '1d', ['close'])
        y = np.log(df.close)
        x = np.arange(len(y))
        slope, intercept = np.polyfit(x, y, 1)
        annualized_returns = math.pow(math.exp(slope), 250) - 1
        r_squared = 1 - (sum((y - (slope * x + intercept)) ** 2) / ((len(y) - 1) * np.var(y, ddof=1)))
        score = annualized_returns * r_squared
        return score

    def get_portfolio_momentum(self, etf_list, weights=None, momentum_day=25):
        price_data = history(momentum_day, '1d', 'close', etf_list, df=True)
        if price_data.empty:
            return np.nan
        if weights is None:
            weights = {etf: 1 / len(etf_list) for etf in etf_list}
        weight_sum = float(sum(list(weights.values())))
        weights = {etf: w / weight_sum for etf, w in weights.items()}
        portfolio_prices = sum(price_data[etf] * weights[etf] for etf in etf_list)
        y = np.log(portfolio_prices.dropna())
        x = np.arange(len(y))
        if len(y) < momentum_day:
            return np.nan
        slope, intercept = np.polyfit(x, y, 1)
        annualized_returns = math.pow(math.exp(slope), 250) - 1
        r_squared = 1 - (sum((y - (slope * x + intercept)) ** 2) / ((len(y) - 1) * np.var(y, ddof=1)))
        return annualized_returns * r_squared

    def adjust_ES(self, ES, score, beta=5, min_ratio=0.75, max_ratio=1.25):
        adjustment_factor = max_ratio - (max_ratio - min_ratio) / (1 + np.exp(-beta * score))
        return ES * adjustment_factor

    def get_ma_signal(self, stock):
        return 1

    def calculate_asset_class_ES(self):
        asset_ES = {}
        etf_ES = {}
        valid_etf_pools = {}
        today = self.context.current_dt.date()

        for asset_class, stock_list in self.etf_pool_all.items():
            valid_etfs = []
            for stock in stock_list:
                start_date = get_security_info(stock).start_date
                if start_date is None:
                    continue
                elif (today - start_date).days > self.min_listing_days:
                    valid_etfs.append(stock)

            valid_etf_pools[asset_class] = valid_etfs
            if not valid_etfs:
                asset_ES[asset_class] = np.nan
                continue

            etf_ES_values = {}
            for stock in valid_etfs:
                etf_ES_values[stock] = self.get_ES(stock)
            etf_ES.update(etf_ES_values)

            if len(valid_etfs) == 1:
                asset_ES[asset_class] = etf_ES[valid_etfs[0]]
            else:
                weights = {etf: 1 / len(valid_etfs) for etf in valid_etfs}
                asset_ES[asset_class] = self.get_portfolio_ES(asset_class, valid_etfs, weights)

        return asset_ES, etf_ES, valid_etf_pools

    def calculate_asset_allocations(self, asset_ES_results):
        risk_budget = {
            "bonds": 0.4,
            "equity": 1.5,
            "foreign_equity": 1.5,
            "commodities": 1.2
        }

        inv_ES = {}
        for asset_class, es_value in asset_ES_results.items():
            if es_value > 0 and not np.isnan(es_value):
                inv_ES[asset_class] = (1 / es_value) * risk_budget.get(asset_class, 1.0)
            else:
                inv_ES[asset_class] = 0

        total_inv_ES = float(sum(list(inv_ES.values())))
        if total_inv_ES > 0:
            asset_allocations = {k: round(v / total_inv_ES, 3) for k, v in inv_ES.items()}
        else:
            asset_allocations = inv_ES
        return asset_allocations

    def calculate_etf_allocations(self, asset_allocations, valid_etf_pools, etf_ES_results):
        etf_allocations = {}
        ema_signals = {etf: self.get_ma_signal(etf) for asset_class, etfs in valid_etf_pools.items() for etf in etfs}

        unused_funds = 0
        active_asset_allocations = {}

        for asset_class, etfs in valid_etf_pools.items():
            total_asset_weight = asset_allocations.get(asset_class, 0)
            valid_etfs = []
            for etf in etfs:
                if asset_class in ["equity", "foreign_equity"] and ema_signals.get(etf, 0) == 1:
                    valid_etfs.append(etf)
                elif asset_class in ["bonds", "commodities"]:
                    valid_etfs.append(etf)

            if asset_class in ["equity", "foreign_equity"]:
                if not valid_etfs:
                    unused_funds += total_asset_weight
                else:
                    active_asset_allocations[asset_class] = total_asset_weight
            else:
                active_asset_allocations[asset_class] = total_asset_weight

        total_active_weight = float(sum(list(active_asset_allocations.values())))
        if total_active_weight > 0:
            scale_factor = 1 + (unused_funds / total_active_weight)
            active_asset_allocations = {k: v * scale_factor for k, v in active_asset_allocations.items()}

        for asset_class, etfs in valid_etf_pools.items():
            if asset_class not in active_asset_allocations:
                continue
            total_asset_weight = active_asset_allocations[asset_class]

            valid_etfs = []
            for etf in etfs:
                if asset_class in ["equity", "foreign_equity"] and ema_signals.get(etf, 0) == 1:
                    valid_etfs.append(etf)
                elif asset_class in ["bonds", "commodities"]:
                    valid_etfs.append(etf)

            if len(valid_etfs) == 1:
                etf_allocations[valid_etfs[0]] = round(total_asset_weight, 3)
            else:
                etf_inv_ES = {etf: 1 / etf_ES_results[etf] if etf_ES_results[etf] > 0 else 0 for etf in etfs}
                total_etf_inv_ES = float(sum(list(etf_inv_ES.values())))
                if total_etf_inv_ES > 0:
                    etf_weights = {etf: etf_inv_ES[etf] / total_etf_inv_ES for etf in etfs}
                    for etf in etfs:
                        etf_allocations[etf] = round(etf_weights[etf] * total_asset_weight, 3)

        return etf_allocations

    def need_rebalance(self):
        for etf in g.positions[self.index]:
            if etf in self.rebalance_price and etf in self.context.portfolio.positions:
                current_price = self.context.portfolio.positions[etf].price
                old_price = self.rebalance_price[etf]
                if old_price != 0:
                    if abs(current_price - old_price) / old_price > self.rebalance_threshold:
                        return True
        return False

    def prepare_trade(self):
        asset_ES_results, etf_ES_results, valid_etf_pools = self.calculate_asset_class_ES()
        asset_allocations = self.calculate_asset_allocations(asset_ES_results)
        etf_allocations = self.calculate_etf_allocations(asset_allocations, valid_etf_pools, etf_ES_results)

        for etf in etf_allocations.keys():
            if etf in self.context.portfolio.positions:
                self.rebalance_price[etf] = self.context.portfolio.positions[etf].price
            else:
                self.rebalance_price[etf] = 0
        return etf_allocations, valid_etf_pools

    def prepare(self):
        if self.period_count == self.cycle_period or self.need_rebalance():
            self.period_count = 0
            self.etf_allocations, self.valid_etf_pools = self.prepare_trade()
        else:
            self.period_count += 1

    def adjust(self):
        if not hasattr(self, 'etf_allocations') or not self.etf_allocations:
            return

        strategy_total_value = self.context.portfolio.total_value * g.portfolio_value_proportion[self.index]

        sell_orders = {}
        for position in self.context.portfolio.positions.values():
            etf = position.security
            if etf in g.positions[self.index]:
                current_value = position.value
                target_value = self.etf_allocations.get(etf, 0) * strategy_total_value
                if target_value < current_value:
                    sell_orders[etf] = target_value

        buy_orders = {}
        for etf, allocation in self.etf_allocations.items():
            target_value = allocation * strategy_total_value
            current_value = 0
            if etf in self.context.portfolio.positions:
                current_value = self.context.portfolio.positions[etf].value
            if target_value > current_value:
                buy_orders[etf] = target_value

        for etf, target_value in sell_orders.items():
            if etf in self.context.portfolio.positions:
                current_value = self.context.portfolio.positions[etf].value
                if target_value > 0:
                    if (current_value - target_value) / target_value > self.trade_threshold and (current_value - target_value) > 1000:
                        self.order_target_value_(etf, target_value)
                elif target_value == 0 and current_value > 1000:
                    self.order_target_value_(etf, target_value)

        for etf, target_value in buy_orders.items():
            if etf in list(self.context.portfolio.positions.keys()):
                current_value = self.context.portfolio.positions[etf].value
            else:
                current_value = 1
            cash = self.context.portfolio.available_cash
            if (target_value - current_value) / target_value > self.trade_threshold and (target_value - current_value) > 1000:
                if cash >= target_value * self.trade_threshold:
                    self.order_target_value_(etf, target_value)


# -------------------- 辅助函数 --------------------
def get_ema(data, window, alpha=None):
    if alpha is None:
        alpha = 2.0 / (window + 1)
    return data.ewm(alpha=alpha, adjust=False).mean()


def get_ma(data, window):
    return data.rolling(window).mean()


def set_trading_costs():
    set_slippage(FixedSlippage(0.002), type="stock")
    set_slippage(FixedSlippage(0.001), type="fund")
    set_order_cost(OrderCost(
        open_tax=0, close_tax=0.0005,
        open_commission=0.85 / 10000, close_commission=0.85 / 10000,
        close_today_commission=0, min_commission=5,
    ), type="stock")
    set_order_cost(OrderCost(
        open_tax=0, close_tax=0,
        open_commission=0.5 / 10000, close_commission=0.5 / 10000,
        close_today_commission=0, min_commission=5
    ), type='fund')
    set_order_cost(OrderCost(
        open_tax=0, close_tax=0,
        open_commission=0, close_commission=0,
        close_today_commission=0, min_commission=0
    ), type='mmf')
