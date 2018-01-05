from datetime import datetime, timedelta
from strategies.email_client import EmailClient
import pandas_market_calendars as mcal
import backtrader as bt


class TAA(bt.Strategy):
    params = (
        ('ema', 65),
    )

    # Keep 0.05 allocated at all times to cash
    allocations = {
        'allstate': {
            'SPY': 0.10,
            'IWM': 0.15,
            'ALL': 0.05,
            'VNQ': 0.20,
            'EEM': 0.25,
            'AGG': 0.20,
        },
    }

    def __init__(self, name):
        self.ema = dict()
        self.name = name
        self.rebalance = False
        self.last_rebalance = None
        self.allocation = self.allocations[self.name]

        self._addsizer(bt.sizers.PercentSizer, percents=100)
        oldest = datetime.now()
        for d in self.getdatanames():
            if d not in self.allocation:
                continue

            bars = self.getdatabyname(d)
            dt = bars.datetime.datetime(-bars.buflen() + 1)
            if dt < oldest:
                oldest = dt

            self.ema[d] = bt.indicators.EMA(
                self.getdatabyname(d), period=self.params.ema)

        # Rebalance last day of week on 2nd last full week of quarter
        self.rebalance_dates = set()
        cal = mcal.get_calendar('NYSE')
        end_of_week = []
        days = cal.valid_days(oldest, datetime(2050, 12, 31, 23, 59))
        for i in range(0, len(days) - 1):
            curr = days[i]
            next = days[i + 1]
            if curr.month % 3 != 0:
                continue
            if curr.weekday() > next.weekday():
                end_of_week.append(curr)
            if curr.month != next.month:
                self.rebalance_dates.add(end_of_week[-2].date())
                end_of_week.clear()

    def notify_order(self, order):
        if order.status in [bt.Order.Completed]:
            print('Executed %d at %f' %
                  (order.executed.size,
                   order.executed.price))

    def get_last_ema(self, bars, offset):
        last_bar = bars.buflen() == len(bars)
        if last_bar or bars.datetime.datetime(1).weekday() < \
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

    def get_portfolio_value(self):
        value = 0.0
        for d in self.getdatanames():
            bars = self.getdatabyname(d)
            pos = self.broker.getposition(bars)
            value += (pos.size * bars.close[0])

        return value + self.broker.get_cash()

    def stop(self):
        text = '{0}\n---------------\n'.format(self.name.title())
        for d in self.allocation:
            bars = self.getdatabyname(d)
            pos = self.broker.getposition(bars)
            allocation = self.allocation[d] * 100 if pos.size != 0 else 0
            text += '%s: %d%%\n' % (d, allocation)

        if self.rebalance:
            print('\n' + text)
            email = EmailClient()
            email.send_message('{0} {1}'.format(self.name, self.last_rebalance),
                               text)

    def next(self):
        for d in self.getdatanames():
            if d not in self.allocation:
                continue

            tmp = 'SPY' if d in ['SPY', 'IWM', 'VNQ', 'EEM'] else d
            signal = self.getdatabyname(tmp)
            bars = self.getdatabyname(d)

            trend = self.get_last_ema(signal, 1) > self.get_last_ema(signal, 2)
            value = self.get_portfolio_value()
            pos = self.broker.getposition(bars)
            self.rebalance = bars.datetime.datetime().date() in \
                self.rebalance_dates

            if self.rebalance:
                print('%s: %s close %f ema %f curr %f last %f val %f cash %f' %
                      (bars.datetime.datetime().isoformat(), d,
                       bars.close[0], self.ema[d][0],
                       self.get_last_ema(bars, 1),
                       self.get_last_ema(bars, 2), value,
                       self.broker.get_cash()))

                self.last_rebalance = bars.datetime.datetime().date()
                desired_qty = int((self.allocation[d] * value) / bars.close[0])
                # No position, check for buy
                if pos.size == 0:
                    # Buy
                    if trend:
                        self.buy(data=d, size=desired_qty,
                                 exectype=bt.Order.Close)
                        print('%s: %s BUY qty %d' %
                              (self.datetime.datetime().isoformat(), d,
                               desired_qty))
                # Open position, check for sell or rebalance
                else:
                    # Sell (never sell bond allocation)
                    if not trend and d not in ["AGG"]:
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
                                self.buy(data=d, size=qty,
                                         exectype=bt.Order.Close)
                            # Over allocated, sell shares
                            else:
                                self.sell(data=d, size=qty,
                                          exectype=bt.Order.Close)


