from datetime import datetime
import backtrader as bt


class PPOTrendProxy(bt.Strategy):
    params = (
        ('short', 50),
        ('long', 100),
        ('short1', 20),
        ('long1', 50),
        ('aroon', 20),
        ('risk', 0.02),
    )

    def __init__(self):
        self.long_ppo = dict()
        self.short_ppo = dict()
        self.highest = dict()
        self.lowest_ppo = dict()
        self.psar = dict()
        self.aroon = dict()
        self.risk = self.params.risk
        self.stop_loss = dict()
        self.chandelier = dict()
        self.proxies = {
            'SPY': ['SPY', 1.0],
        }

        self._addsizer(bt.sizers.PercentSizer, percents=100)
        for sym in self.getdatanames():
            self.stop_loss[sym] = None

            self.aroon[sym] = bt.indicators.AroonOsc(
                self.getdatabyname(sym), period=self.params.aroon)
            self.long_ppo[sym] = bt.indicators.PPO(
                self.getdatabyname(sym), period1=self.params.short,
                period2=self.params.long, period_signal=1)
            self.short_ppo[sym] = bt.indicators.PPO(
                self.getdatabyname(sym), period1=self.params.short1,
                period2=self.params.long1, period_signal=1)
            self.lowest_ppo[sym] = bt.indicators.Lowest(
                self.short_ppo[sym], period=5)
            self.psar[sym] = bt.indicators.PSAR(
                self.getdatabyname(sym), af=0.001)

    def notify_order(self, order):
        if order.status in [bt.Order.Completed]:
            print('Executed %f' % order.executed.price)

    def get_portfolio_value(self):
        value = 0.0
        for d in self.getdatanames():
            data = self.getdatabyname(d)
            pos = self.broker.getposition(data)
            value += (pos.size * data.close[0])

        return value + self.broker.get_cash()

    def next(self):
        for sym in self.getdatanames():
            if sym not in self.proxies:
                continue

            bars = self.getdatabyname(sym)
            proxy_data = self.proxies.get(sym)
            proxy_sym = proxy_data[0]
            proxy_bars = self.getdatabyname(proxy_sym)

            long_trend = self.long_ppo[proxy_sym][0] > 0.0
            trend_proxy = self.short_ppo[proxy_sym][0] > 0.0 and \
                self.short_ppo[proxy_sym][0] > self.lowest_ppo[proxy_sym][0]
            aroon_proxy = self.aroon[proxy_sym][0] > 0.0 and trend_proxy
            pos = self.broker.getposition(bars)

            print('%s: cash %f signal %s\n'
                  '\t%s { close %f ppo %f sar %f lowest ppo %f }\n'
                  '\t%s { close %f ppo %f sar %f lowest ppo %f }' %
                  (bars.datetime.datetime().isoformat(),
                   self.broker.getcash(),
                   ("Long" if long_trend else "Short"),
                   proxy_sym,
                   proxy_bars.close[0],
                   self.short_ppo[proxy_sym][0],
                   self.psar[proxy_sym][0],
                   self.lowest_ppo[proxy_sym][0],
                   sym,
                   bars.close[0],
                   self.short_ppo[sym][0],
                   self.psar[sym][0],
                   self.lowest_ppo[sym][0]))

            if pos.size == 0:
                if aroon_proxy and self.psar[proxy_sym][0] < proxy_bars.close[0]:
                    # Percent risk for proxy symbol
                    risk = (proxy_bars.close[0] - self.psar[proxy_sym][0]) / \
                        proxy_bars.close[0]
                    # Normalize risk to current symbol, with leverage factor
                    self.stop_loss[sym] = bars.close[0] - \
                        (bars.close[0] * risk * proxy_data[1])

                    qty = min((self.risk * self.get_portfolio_value()) /
                              (bars.close[0] - self.stop_loss[sym]),
                              (self.get_portfolio_value() / len(self.proxies)) /
                              bars.close[0])
                    self.buy(data=sym, size=qty, exectype=bt.Order.Close)

                    print('%s: %s BUY qty %d stop %f' %
                          (self.datetime.datetime().isoformat(), sym, qty,
                           self.stop_loss[sym]))
            else:
                # Move stop loss to break even?
                #if chandelier > self.getposition(data).price:
                #  self.stop_loss[d] = self.getposition(data).price

                # Never lower trailing stop?

                # Tighten trailing stop?

                if bars.close[0] < self.stop_loss[sym] or \
                   proxy_bars.close[0] < self.psar[proxy_sym][0]:

                    reason = 'stop loss' if bars.close[0] < self.stop_loss[sym] \
                        else 'trailing stop'
                    self.sell(data=sym, exectype=bt.Order.Close)
                    self.stop_loss[sym] = None

                    print('%s: %s SELL reason %s' %
                          (self.datetime.datetime().isoformat(), sym,
                           reason))

