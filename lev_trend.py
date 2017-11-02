import backtrader as bt


class LevTrend(bt.Strategy):
    params = (
        ('short', 65),
        ('long', 170),
        ('short1', 13),
        ('long1', 34),
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
                'long': ['ULPIX'],
                'short': ['URPIX'],
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

    def enter_position(self, long, proxy, sym):
        # Percent risk for proxy symbol
        risk = (proxy[1].close[0] - self.psar[proxy[0]][0]) / proxy[1].close[0] \
            if long \
            else (self.psar[proxy[0]][0] - proxy[1].close[0]) / proxy[1].close[0]

        # Normalize risk to symbol being traded
        self.stop_loss[sym[0]] = sym[1].close[0] - \
            (sym[1].close[0] * risk)

        qty = min((self.risk * self.get_portfolio_value()) /
                  (sym[1].close[0] - self.stop_loss[sym[0]]),
                  (self.get_portfolio_value() / len(self.proxies)) /
                  sym[1].close[0])
        self.buy(data=sym[0], size=qty, exectype=bt.Order.Close)

        print('%s: %s BUY qty %d stop %f' %
              (self.datetime.datetime().isoformat(), sym[0], qty,
               self.stop_loss[sym[0]]))

    def exit_position(self, long, proxy, sym):
        psar_exit = (long and proxy[1].close[0] < self.psar[proxy[0]][0]) or \
            (not long and proxy[1].close[0] > self.psar[proxy[0]][0])
        if sym[1].close[0] < self.stop_loss[sym[0]] or \
           psar_exit:
            reason = 'stop loss' if sym[1].close[0] < self.stop_loss[sym[0]] \
                else 'trailing stop'
            self.sell(data=sym[0], exectype=bt.Order.Close)
            self.stop_loss[sym[0]] = None

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
                    self.short_ppo[sym][0] > self.low_ppo[sym][0] and \
                    self.aroon[sym][0] > 0.0

                short = self.long_ppo[sym][0] < 0.0 and \
                    self.short_ppo[sym][0] < 0.0 and \
                    self.short_ppo[sym][0] < self.high_ppo[sym][0] and \
                    self.aroon[sym][0] < 0.0 and \
                    not self.long_only

                # Open long
                if long and self.psar[sym][0] < bars.close[0]:
                    self.enter_position(True, [sym, bars],
                                        [long_sym, long_bars])
                # Open short
                elif short and self.psar[sym][0] > bars.close[0]:
                    self.enter_position(False, [sym, bars],
                                        [short_sym, short_bars])




