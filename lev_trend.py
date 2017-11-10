import backtrader as bt
import sys


class LevTrend(bt.Strategy):
    params = (
        ('short', 50),
        ('long', 100),
        ('short1', 13),
        ('long1', 34),
        ('long_psar', 0.005),
        ('short_psar', 0.01),
        ('atr', 22),
        ('long_atr_mult', 4.0),
        ('short_atr_mult', 3.0),
        ('risk', 0.02),
    )

    def __init__(self, long_only, stop_type):
        self.long_only = long_only
        self.stop_type = stop_type
        self.long_atr_multiplier = self.params.long_atr_mult
        self.short_atr_multiplier = self.params.short_atr_mult
        self.risk = self.params.risk
        self.long_ppo = dict()
        self.short_ppo = dict()
        self.low_ppo = dict()
        self.high_ppo = dict()
        self.long_psar = dict()
        self.short_psar = dict()
        self.atr = dict()
        self.lowest = dict()
        self.highest = dict()
        self.stop_loss = dict()
        self.trailing_stop = dict()
        self.proxies = {
            'SPY': {
                'long': ['ULPIX'],
                'short': ['SDS'],
            },
        }

        self._addsizer(bt.sizers.PercentSizer, percents=100)
        for sym in self.getdatanames():
            self.stop_loss[sym] = None
            self.trailing_stop[sym] = None

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
            self.long_psar[sym] = bt.indicators.PSAR(
                self.getdatabyname(sym), af=self.params.long_psar)
            self.short_psar[sym] = bt.indicators.PSAR(
                self.getdatabyname(sym), af=self.params.short_psar)
            self.atr[sym] = bt.indicators.AverageTrueRange(
                self.getdatabyname(sym), period=self.params.atr)
            self.lowest[sym] = bt.indicators.Lowest(
                self.getdatabyname(sym), period=self.params.atr)
            self.highest[sym] = bt.indicators.Highest(
                self.getdatabyname(sym), period=self.params.atr)

    def notify_order(self, order):
        if order.status in [bt.Order.Completed]:
            print('Executed %f' % order.executed.price)

    def get_cash_per_bucket(self):
        open_pos = 0
        for d in self.getdatanames():
            data = self.getdatabyname(d)
            pos = self.broker.getposition(data)
            open_pos += 1 if pos.size != 0 else 0

        return self.broker.getcash() / (len(self.proxies) - open_pos)

    @staticmethod
    def get_proxy_sym(proxy):
        return proxy[0]

    def set_trailing_stop(self, long, proxy, sym):
        if long:
            # PSAR exit
            if self.stop_type == 'psar':
                self.trailing_stop[sym[0]] = self.long_psar[proxy[0]][0]
            # Chandelier exit
            else:
                chandelier = self.highest[proxy[0]][0] - \
                    (self.atr[proxy[0]][0] * self.long_atr_multiplier)
                self.trailing_stop[sym[0]] = max(
                    0 if self.trailing_stop[sym[0]] is None
                    else self.trailing_stop[sym[0]], chandelier)
        else:
            # PSAR exit
            if self.stop_type == 'psar':
                self.trailing_stop[sym[0]] = self.short_psar[proxy[0]][0]
            # Chandelier exit
            else:
                chandelier = self.lowest[proxy[0]][0] + \
                    (self.atr[proxy[0]][0] * self.short_atr_multiplier)
                self.trailing_stop[sym[0]] = min(
                    sys.maxsize if self.trailing_stop[sym[0]] is None
                    else self.trailing_stop[sym[0]], chandelier)

    def enter_position(self, long, proxy, sym):
        self.set_trailing_stop(long, proxy, sym)

        # Make sure trailing stop is on right side of trade
        buy = (long and proxy[1].close[0] > self.trailing_stop[sym[0]]) or \
              (not long and proxy[1].close[0] < self.trailing_stop[sym[0]])

        if buy:
            # Calc risk per share based on proxy
            if long:
                risk = (proxy[1].close[0] - self.trailing_stop[sym[0]]) / \
                    proxy[1].close[0]
            else:
                risk = (self.trailing_stop[sym[0]] - proxy[1].close[0]) / \
                    proxy[1].close[0]

            # Normalize risk to symbol being traded to set stop loss
            self.stop_loss[sym[0]] = sym[1].close[0] - \
                (sym[1].close[0] * risk)

            cash_risk = self.risk * len(self.proxies) * self.get_cash_per_bucket()
            qty = min(cash_risk / (sym[1].close[0] - self.stop_loss[sym[0]]),
                      self.get_cash_per_bucket() / sym[1].close[0])
            self.buy(data=sym[0], size=qty, exectype=bt.Order.Close)

            print('%s: %s BUY qty %d stop %f' %
                  (self.datetime.datetime().isoformat(), sym[0], qty,
                   self.stop_loss[sym[0]]))
        else:
            self.trailing_stop[sym[0]] = None

    def exit_position(self, long, proxy, sym):
        self.set_trailing_stop(long, proxy, sym)

        # Did close cross the trailing stop
        sell = (long and proxy[1].close[0] < self.trailing_stop[sym[0]]) or \
               (not long and proxy[1].close[0] > self.trailing_stop[sym[0]])

        if sym[1].close[0] < self.stop_loss[sym[0]] or sell:
            reason = 'stop loss' if sym[1].close[0] < self.stop_loss[sym[0]] \
                else 'trailing stop'
            self.sell(data=sym[0], exectype=bt.Order.Close)
            self.stop_loss[sym[0]] = None
            self.trailing_stop[sym[0]] = None

            print('%s: %s SELL reason %s' %
                  (self.datetime.datetime().isoformat(), sym[0],
                   reason))

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
                  '\t%s { close %f trend ppo %f timing ppo %f '
                  'long sar %f short sar %f '
                  'atr %f lowest %f highest %f '
                  'high ppo %f low ppo %f '
                  'long %s short %s }\n'
                  '\t%s { close %f }\n' 
                  '\t%s { close %f }\n' %
                  (bars.datetime.datetime().isoformat(),
                   self.broker.getcash(),
                   sym,
                   bars.close[0],
                   self.long_ppo[sym][0],
                   self.short_ppo[sym][0],
                   self.long_psar[sym][0],
                   self.short_psar[sym][0],
                   self.atr[sym][0],
                   self.lowest[sym][0],
                   self.highest[sym][0],
                   self.high_ppo[sym][0],
                   self.low_ppo[sym][0],
                   str(long_pos.size != 0),
                   str(short_pos.size != 0),
                   long_sym,
                   long_bars.close[0],
                   short_sym,
                   short_bars.close[0]))

            # Check stops on open long pos
            if long_pos.size != 0:
                self.exit_position(True, [sym, bars], [long_sym, long_bars])
            # Check stops on open short pos
            elif short_pos.size != 0:
                self.exit_position(False, [sym, bars], [short_sym, short_bars])
            # Check for entry
            else:
                long = self.long_ppo[sym][0] > 0.0 and \
                    self.short_ppo[sym][0] > 0.0 and \
                    (self.short_ppo[sym][-1] < 0.0)

                short = not self.long_only and \
                    self.long_ppo[sym][0] < 0.0 and \
                    self.short_ppo[sym][0] < 0.0 and \
                    (self.short_ppo[sym][-1] > 0.0)

                # Long signal
                if long:
                    self.enter_position(True, [sym, bars],
                                        [long_sym, long_bars])
                # Short signal
                elif short:
                    self.enter_position(False, [sym, bars],
                                        [short_sym, short_bars])




