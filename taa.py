from datetime import datetime, timedelta
import pandas_market_calendars as mcal
import backtrader as bt


class TAA(bt.Strategy):
    params = (
        ('ema', 65),
        ('short', 13),
        ('long', 34),
        ('signal', 1),
    )

    # Keep 0.05 allocated at all times to cash
    allocations = {
        'allstate': {
            'SPY': 0.05,
            'IWM': 0.20,
            'ALL': 0.05,
            'VNQ': 0.15,
            'EEM': 0.25,
            'AGG': 0.25,
        },
        'spot': {
            'SPY': 0.05,
            'IWM': 0.20,
            'VNQ': 0.15,
            'EEM': 0.25,
            'EFA': 0.05,
            'IEF': 0.20,
            # 'BWX': 0.05, International bond, no closely correlated etf
        }
    }

    def __init__(self, name):
        print(name)
        self.ema = dict()
        self.macd = dict()
        self.allocation = self.allocations[name]

        self._addsizer(bt.sizers.PercentSizer, percents=100)
        oldest = datetime.now()
        for d in self.getdatanames():
            if d not in self.allocation:
                continue
            data = self.getdatabyname(d)
            dt = data.datetime.datetime(-data.buflen() + 1)
            if dt < oldest:
                oldest = dt

            self.ema[d] = bt.indicators.EMA(
                self.getdatabyname(d), period=self.params.ema)
            self.macd[d] = bt.indicators.MACD(
                self.getdatabyname(d), period_me1=self.params.short,
                period_me2=self.params.long,
                period_signal=self.params.signal)

        # Rebalance last day of week on last full week of quarter
        self.rebalance = set()
        cal = mcal.get_calendar('NYSE')
        end_of_week = None
        days = cal.valid_days(oldest, datetime.now())
        for i in range(0, len(days) - 1):
            curr = days[i]
            next = days[i + 1]
            if curr.month % 3 != 0:
                continue
            if curr.weekday() > next.weekday():
                end_of_week = curr
            if curr.month != next.month:
                self.rebalance.add(end_of_week.date())
                end_of_week = None

    def notify_order(self, order):
        if order.status in [bt.Order.Completed]:
            print('Executed %d at %f' %
                  (order.executed.size,
                   order.executed.price))

    def get_last_ema(self, data, offset):
        last_bar = data.buflen() == len(data)
        if last_bar or \
              data.datetime.datetime(1).weekday() < data.datetime.datetime().weekday():
            offset -= 1

        if offset == 0:
            return self.ema[data._name][0]

        prev = (data.datetime.datetime() -
                timedelta(days=data.datetime.datetime().weekday())) + \
            timedelta(days=4, weeks=-offset)

        index = 0
        for i in range(-1, -15, -1):
            dt = data.datetime.datetime(i).date()
            if dt <= prev.date():
                index = i
                break

        return self.ema[data._name][index]

    def get_portfolio_value(self):
        value = 0.0
        for d in self.getdatanames():
            data = self.getdatabyname(d)
            pos = self.broker.getposition(data)
            value += (pos.size * data.close[0])

        return value + self.broker.get_cash()

    def next(self):
        for d in self.getdatanames():
            if d not in self.allocation:
                continue
            tmp = "SPY" if d in ['SPY', 'IWM', 'EFA'] else d
            signal = self.getdatabyname(tmp)
            data = self.getdatabyname(d)

            trend = self.get_last_ema(signal, 1) > self.get_last_ema(signal, 2)
            #trend = self.get_last_ema(data, 1) > self.get_last_ema(data, 2)
            value = self.get_portfolio_value()
            pos = self.broker.getposition(data)
            rebal = data.datetime.datetime().date() in self.rebalance

            if rebal:
                print('%s: %s close %f ema %f curr %f last %f val %f cash %f' %
                      (data.datetime.datetime().isoformat(), d,
                       data.close[0], self.ema[d][0], self.get_last_ema(data, 1),
                       self.get_last_ema(data, 2), value, self.broker.get_cash()))

            if rebal:
                desired_qty = int((self.allocation[d] * value) / data.close[0])
                # No position, check for buy
                if pos.size == 0:
                    # Buy
                    if trend:
                        self.buy(data=d, size=desired_qty, exectype=bt.Order.Close)
                        print('%s: %s BUY qty %d' %
                              (self.datetime.datetime().isoformat(), d,
                               desired_qty))
                # Open position, check for sell or rebalance
                else:
                    # Sell
                    if not trend and d not in ["AGG", "IEF"]:
                        self.sell(data=d, exectype=bt.Order.Close)
                        print('%s: %s SELL qty %d' %
                              (self.datetime.datetime().isoformat(), d,
                               pos.size))
                    # Rebalance open positions
                    else:
                        qty = abs(desired_qty - pos.size)
                        if qty != 0:
                            print('%s: %s REBALANCE %s current qty: %d '
                                  'desired qty: %d' %
                                  (self.datetime.datetime().isoformat(), d,
                                   ("BUY" if desired_qty > pos.size
                                    else "SELL"),
                                   pos.size, desired_qty))
                            # Under allocated, buy shares
                            if desired_qty > pos.size:
                                self.buy(data=d, size=qty, exectype=bt.Order.Close)
                            # Over allocated, sell shares
                            else:
                                self.sell(data=d, size=qty, exectype=bt.Order.Close)


if __name__ == '__main__':
    symbols = [
        'SPY',
        'IWM',
        'ALL',
        'EEM',
        'VNQ',
        'AGG'
    ]

    cerebro = bt.Cerebro()
    cerebro.addstrategy(TAA)

    for s in symbols:
      data = bt.feeds.YahooFinanceData(dataname=s,
                                       fromdate=datetime(2006, 1, 1),
                                       todate=datetime.today(),
                                       swapcloses=True,
                                       adjclose=False)
      cerebro.adddata(data)

    cerebro.addanalyzer(bt.analyzers.Transactions, _name='transactions')
    cerebro.addanalyzer(bt.analyzers.SQN, _name='sqn')
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')

    s = cerebro.run()[0]

    print(strategies[0].analyzers.transactions.get_analysis())
    print(s.analyzers.sqn.get_analysis())
    print(s.analyzers.sharpe.get_analysis())

