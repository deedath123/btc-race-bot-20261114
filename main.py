"""cbBTC capitulation fisher for the make.fun 24h bars-replay race.

Long only, one position, minute bars. This edition's dev window is a
grinding sell-off (BTC down about 5% over the day with one capitulation
bottom and a sharp bounce), so a trend rider cannot pass the dev gate here:
every EMA/momentum variant bled fees chasing a falling tape. This bot does
the opposite trade. It waits for a real washout, then fishes the bounce.

Entry (flat, off cooldown): the close sits at least 2.5% under the highest
close of the trailing 480 bars (a genuine capitulation, not a routine dip)
AND the trailing 15-bar momentum has turned up by more than +0.10% (the
bounce has actually started, so the bot is not catching a falling knife).
The buy spends all cash and fills at the next bar's open.
Exit (first that fires): +0.80% over the entry mark (take the bounce),
the close falls 0.50% under the peak close since entry after a 10-bar
minimum hold (trailing lock), 0.80% under the entry mark (hard stop), or
300 bars held. A 60-bar cooldown follows every exit: a full round trip
costs about 26 bps, so the bot trades only the one move that pays for it.

Everything is arithmetic on the bars seen so far: no clock, no randomness,
no files, so two runs of the same window give the same orders.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYMBOL = "CBBTC"
WINDOW = 480
DD_TH = 0.025
REV_LOOK = 15
REV_TH = 0.001
TAKE = 0.008
TRAIL = 0.005
HARD_STOP = 0.008
MAX_HOLD_BARS = 300
COOLDOWN_BARS = 60
MIN_HOLD_TRAIL = 10
MAX_SLIPPAGE_BPS = 150
MIN_NOTIONAL = 1_000_000


class Fisher:
    def __init__(self):
        self.closes = []
        self.entry_mark = None
        self.peak = None
        self.held_bars = 0
        self.cooldown = 0

    def on_batch(self, state, batch):
        bar = None
        for b in batch["bars"]:
            if b["symbol"] == SYMBOL:
                bar = b
        if bar is None:
            return []
        close = int(bar["c"])
        self.closes.append(close)
        if len(self.closes) <= WINDOW:
            return []
        holding = state.positions.get(SYMBOL)
        orders = []
        if holding is not None and holding.qty > 0:
            self.held_bars += 1
            if self.peak is None or close > self.peak:
                self.peak = close
            sell = False
            if self.entry_mark is not None and close >= self.entry_mark * (1 + TAKE):
                sell = True
            elif (self.peak is not None and self.held_bars >= MIN_HOLD_TRAIL
                    and close <= self.peak * (1 - TRAIL)):
                sell = True
            elif self.entry_mark is not None and close <= self.entry_mark * (1 - HARD_STOP):
                sell = True
            elif self.held_bars >= MAX_HOLD_BARS:
                sell = True
            if sell:
                orders.append({
                    "side": "sell",
                    "symbol": SYMBOL,
                    "qty": holding.qty,
                    "max_slippage_bps": MAX_SLIPPAGE_BPS,
                })
                self.entry_mark = None
                self.peak = None
                self.held_bars = 0
                self.cooldown = COOLDOWN_BARS
            return orders
        if state.warming_up:
            return []
        if self.cooldown > 0:
            self.cooldown -= 1
            return []
        roll_max = max(self.closes[-WINDOW:])
        drawdown = close / roll_max - 1
        momentum = self.closes[-1] / self.closes[-1 - REV_LOOK] - 1
        if drawdown <= -DD_TH and momentum > REV_TH:
            stake = state.cash
            if stake >= MIN_NOTIONAL:
                orders.append({
                    "side": "buy",
                    "symbol": SYMBOL,
                    "notional_quote_units": stake,
                    "max_slippage_bps": MAX_SLIPPAGE_BPS,
                })
                self.entry_mark = close
                self.peak = close
                self.held_bars = 0
        return orders


FISHER = Fisher()
makefun_bars.run(FISHER.on_batch)
