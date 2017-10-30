from datetime import datetime, timedelta
import backtrader as bt


class Trend(bt.Strategy):
    params = (
        ('ema', 65),
        ('short', 20),
        ('long', 50),
        ('aroon', 5),
        ('atr', 22),
        ('atr_mult', 4.5),
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
            bars = self.getdatabyname(sym)

            chandelier = self.highest[sym][0] - \
                (self.atr[sym][0] * self.atrMultiplier)
            trend = self.ppo[sym][0] > 0.0 if self.entry == 'ppo' \
                else self.get_last_ema(bars, 1) > self.get_last_ema(bars, 2)
            aroon = self.aroon[sym][0] > 0.0 and trend
            pos = self.broker.getposition(bars)

            print('%s: cash %f\n'
                  '\t%s { close %f ppo %f chandelier %f atr %f }' %
                  (bars.datetime.datetime().isoformat(),
                   self.broker.getcash(),
                   sym,
                   bars.close[0],
                   self.ppo[sym][0],
                   chandelier,
                   self.atr[sym][0]))

            if pos.size == 0:
                if aroon and chandelier < bars.close[0]:
                    # Risk per share
                    risk = bars.close[0] - chandelier
                    # Set stops
                    self.stopLoss[sym] = chandelier
                    self.chandelier[sym] = chandelier

                    qty = min((self.risk * self.broker.getcash()) / risk,
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
                                           chandelier)

                # Tighten trailing stop?

                if bars.close[0] < self.stopLoss[sym] or \
                   bars.close[0] < self.chandelier[sym]:

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
