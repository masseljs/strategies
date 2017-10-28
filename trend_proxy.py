from datetime import datetime, timedelta
import backtrader as bt


class TrendProxy(bt.Strategy):
    params = (
        ('ema', 65),
        ('short', 20),
        ('long', 50),
        ('aroon', 5),
        ('atr', 22),
        ('atr_mult', 3.0),
        ('risk', 0.02),
    )

    def __init__(self, entry):
        self.ema = dict()
        self.ppo = dict()
        self.highest = dict()
        self.aroon = dict()
        self.atr = dict()
        self.atrMultiplier = self.params.atr_mult
        self.risk = self.params.risk
        self.stopLoss = dict()
        self.chandelier = dict()
        self.entry = entry
        self.proxies = {
            'ULPIX': 'SPY',
        }

        self._addsizer(bt.sizers.PercentSizer, percents=100)
        for sym in self.getdatanames():
            self.stopLoss[sym] = None
            self.chandelier[sym] = None

            self.atr[sym] = bt.indicators.AverageTrueRange(
                self.getdatabyname(sym), period=self.params.atr)
            self.aroon[sym] = bt.indicators.AroonOsc(
                self.getdatabyname(sym), period=self.params.aroon)
            self.ema[sym] = bt.indicators.EMA(
                self.getdatabyname(sym), period=self.params.ema)
            self.ppo[sym] = bt.indicators.PPO(
                self.getdatabyname(sym), period1=self.params.short,
                period2=self.params.long, period_signal=1)
            self.highest[sym] = bt.indicators.Highest(
                self.getdatabyname(sym), period=self.params.atr)

    def notify_order(self, order):
        if order.status in [bt.Order.Completed]:
            print('Executed %f' % order.executed.price)

    def get_last_ema(self, bars, offset):
        last_bar = bars.buflen() == len(bars)
        if last_bar or \
           bars.datetime.datetime(1).weekday() < \
                bars.datetime.datetime().weekday():
            offset -= 1

        if offset == 0:
            return self.ema[bars._name][0]

        prev = (bars.datetime.datetime() -
                timedelta(days=bars.datetime.datetime().weekday())) + \
            timedelta(days=4, weeks=-offset)

        index = 0
        for i in range(-1, -15, -1):
            dt = bars.datetime.datetime(i).date()
            if dt <= prev.date():
                index = i
                break

        return self.ema[bars._name][index]

    def next(self):
        for sym in self.getdatanames():
            if sym not in self.proxies:
                continue

            bars = self.getdatabyname(sym)
            proxy_sym = self.proxies.get(sym)
            proxy_bars = self.getdatabyname(proxy_sym)

            chandelier = self.highest[sym][0] - \
                (self.atr[sym][0] * self.atrMultiplier)
            chandelier_proxy = self.highest[proxy_sym][0] - \
                (self.atr[proxy_sym][0] * self.atrMultiplier)
            trend_proxy = self.ppo[proxy_sym][0] > 0.0 if self.entry == 'ppo' \
                else self.get_last_ema(proxy_bars, 1) > self.get_last_ema(proxy_bars, 2)
            aroon_proxy = self.aroon[proxy_sym][0] > 0.0 and trend_proxy
            pos = self.broker.getposition(bars)

            print('%s: cash %f\n'
                  '\t%s { close %f ppo %f chandelier %f atr %f }\n'
                  '\t%s { close %f ppo %f chandelier %f atr %f }' %
                  (bars.datetime.datetime().isoformat(),
                   self.broker.getcash(),
                   proxy_sym,
                   proxy_bars.close[0],
                   self.ppo[proxy_sym][0],
                   chandelier_proxy,
                   self.atr[proxy_sym][0],
                   sym,
                   bars.close[0],
                   self.ppo[sym][0],
                   chandelier,
                   self.atr[sym][0],))

            if pos.size == 0:
                if aroon_proxy and chandelier_proxy < proxy_bars.close[0]:
                    # Percent risk for proxy symbol
                    risk = (proxy_bars.close[0] - chandelier_proxy) / \
                        proxy_bars.close[0]
                    # Normalize risk to current symbol, with leverage factor
                    self.stopLoss[sym] = bars.close[0] - \
                        (bars.close[0] * risk * 2.0)
                    # Track trailing stop of proxy symbol
                    self.chandelier[sym] = chandelier_proxy

                    qty = min((self.risk * self.broker.getcash()) /
                              (bars.close[0] - self.stopLoss[sym]),
                              (self.broker.getcash() * 0.5) / bars.close[0])
                    self.buy(data=sym, size=qty, exectype=bt.Order.Close)

                    print('%s: %s BUY qty %d stop %f' %
                          (self.datetime.datetime().isoformat(), sym, qty,
                           self.stopLoss[sym]))
            else:
                # Move stop loss to break even?
                #if chandelier > self.getposition(data).price:
                #  self.stopLoss[d] = self.getposition(data).price

                # Never lower trailing stop?
                self.chandelier[sym] = max(self.chandelier[sym],
                                           chandelier_proxy)

                # Tighten trailing stop?

                if bars.close[0] < self.stopLoss[sym] or \
                   proxy_bars.close[0] < self.chandelier[sym]:

                    reason = 'stop loss' if bars.close[0] < self.stopLoss[sym] \
                        else 'trailing stop'
                    self.sell(data=sym, exectype=bt.Order.Close)
                    self.stopLoss[sym] = None
                    self.chandelier[sym] = None

                    print('%s: %s SELL reason %s' %
                          (self.datetime.datetime().isoformat(), sym,
                           reason))


if __name__ == '__main__':
    symbols = ['ULPIX']

    cerebro = bt.Cerebro()
    cerebro.addstrategy(PPOTrend)

    for s in symbols:
        data = bt.feeds.YahooFinanceData(dataname=s,
                                         fromdate=datetime(2006, 1, 1),
                                         todate=datetime.today(),
                                         swapcloses=True,
                                         adjclose=False)
        cerebro.adddata(data)
        cerebro.resampledata(data, timeframe=bt.TimeFrame.Weeks)

    cerebro.addanalyzer(bt.analyzers.Transactions, _name='transactions')
    cerebro.addanalyzer(bt.analyzers.SQN, _name='sqn')
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')

    s = cerebro.run()[0]

    # print(strategies[0].analyzers.transactions.get_analysis())
    print(s.analyzers.sqn.get_analysis())
    print(s.analyzers.sharpe.get_analysis())

    #cerebro.plot()
