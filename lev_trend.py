from datetime import datetime
import backtrader as bt


class LevTrend(bt.Strategy):
    params = (
        ('short', 50),
        ('long', 100),
        ('short1', 20),
        ('long1', 50),
        ('aroon', 20),
        ('risk', 0.02),
    )

    def __init__(self, long_only):
        self.long_ppo = dict()
        self.short_ppo = dict()
        self.highest = dict()
        self.low_ppo = dict()
        self.high_ppo = dict()
        self.psar = dict()
        self.aroon = dict()
        self.risk = self.params.risk
        self.stop_loss = dict()
        self.long_only = long_only
        self.proxies = {
            'SPY': {
                'long': ['ULPIX', 1.0],
                'short': ['URPIX', 1.0],
            }
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
            self.low_ppo[sym] = bt.indicators.Lowest(
                self.short_ppo[sym], period=5)
            self.high_ppo[sym] = bt.indicators.Highest(
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

    def get_proxy_sym(self, proxy):
        return proxy[0]

    def get_proxy_leverage(self, proxy):
        return proxy[1]

    def next(self):
        for sym in self.getdatanames():
            if sym not in self.proxies:
                continue

            bars = self.getdatabyname(sym)

            proxy = self.proxies.get(sym)
            long_proxy = proxy['long']
            long_sym = self.get_proxy_sym(long_proxy)
            long_bars = self.getdatabyname(long_sym)
            short_proxy = proxy['short']
            short_sym = self.get_proxy_sym(short_proxy)
            short_bars = self.getdatabyname(short_sym)

            # Check for open long/short pos
            long_pos = self.broker.getposition(long_bars)
            short_pos = self.broker.getposition(short_bars)

            print('%s: cash %f\n'
                  '\t%s { close %f ppo %f sar %f low ppo %f long %s short %s }\n' %
                  (bars.datetime.datetime().isoformat(),
                   self.broker.getcash(),
                   sym,
                   bars.close[0],
                   self.short_ppo[sym][0],
                   self.psar[sym][0],
                   self.low_ppo[sym][0],
                   str(long_pos.size != 0),
                   str(short_pos.size != 0)))

            # Open long position, check stops
            if long_pos.size != 0:
                if long_bars.close[0] < self.stop_loss[long_sym] or \
                   bars.close[0] < self.psar[sym][0]:
                    reason = 'stop loss' if long_bars.close[0] < self.stop_loss[long_sym] \
                        else 'trailing stop'
                    self.sell(data=long_sym, exectype=bt.Order.Close)
                    self.stop_loss[long_sym] = None

                    print('%s: %s SELL reason %s' %
                          (self.datetime.datetime().isoformat(), long_sym,
                           reason))
            # Open short position, check stops
            elif short_pos.size != 0:
                if short_bars.close[0] < self.stop_loss[short_sym] or \
                   bars.close[0] > self.psar[sym][0]:
                    reason = 'stop loss' if short_bars.close[0] < self.stop_loss[short_sym] \
                        else 'trailing stop'
                    self.sell(data=short_sym, exectype=bt.Order.Close)
                    self.stop_loss[short_sym] = None

                    print('%s: %s SELL reason %s' %
                          (self.datetime.datetime().isoformat(), short_sym,
                           reason))
            # Check for entry
            else:
                long = self.short_ppo[sym][0] > 0.0 and \
                    self.short_ppo[sym][0] > self.low_ppo[sym][0] and \
                    self.aroon[sym][0] > 0.0

                short = self.short_ppo[sym][0] < 0.0 and \
                    self.short_ppo[sym][0] < self.high_ppo[sym][0] and \
                    self.aroon[sym][0] < 0.0 and \
                    not self.long_only

                # Open long
                if long and self.psar[sym][0] < bars.close[0]:
                    # Percent risk for proxy symbol
                    risk = (bars.close[0] - self.psar[sym][0]) / bars.close[0]

                    # Normalize risk to long symbol, with leverage factor
                    self.stop_loss[long_sym] = long_bars.close[0] - \
                        (long_bars.close[0] * risk *
                         self.get_proxy_leverage(long_proxy))

                    qty = min((self.risk * self.get_portfolio_value()) /
                              (long_bars.close[0] - self.stop_loss[long_sym]),
                              (self.get_portfolio_value() / len(self.proxies)) /
                              long_bars.close[0])
                    self.buy(data=long_sym, size=qty, exectype=bt.Order.Close)

                    print('%s: %s BUY qty %d stop %f' %
                          (self.datetime.datetime().isoformat(), long_sym, qty,
                           self.stop_loss[long_sym]))
                # Open short
                elif short and self.psar[sym][0] > bars.close[0]:
                    risk = (self.psar[sym][0] - bars.close[0]) / bars.close[0]

                    # Normalize risk to short symbol, with leverage factor
                    self.stop_loss[short_sym] = short_bars.close[0] - \
                        (short_bars.close[0] * risk *
                         self.get_proxy_leverage(short_proxy))

                    qty = min((self.risk * self.get_portfolio_value()) /
                              (short_bars.close[0] - self.stop_loss[short_sym]),
                              (self.get_portfolio_value() / len(self.proxies)) /
                              short_bars.close[0])
                    self.buy(data=short_sym, size=qty, exectype=bt.Order.Close)

                    print('%s: %s BUY qty %d stop %f' %
                          (self.datetime.datetime().isoformat(), short_sym, qty,
                           self.stop_loss[short_sym]))



