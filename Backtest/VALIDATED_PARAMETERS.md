# Validated Parameters Reference

A catalog of every tested configuration from this project's tuning history with
**win rate >= 70%**, for reuse when exploring other coins, other strategies, or
improved versions. All numbers below come from real backtests (BTC-USD, 1h
candles, 730-day window, via `yfinance`) run and pasted during actual sessions --
nothing here is estimated or re-derived from memory.

**Important scope note:** every parameter set below was tuned specifically for
BTC-USD's behavior over this exact 2024-2026 window. When this project's own
confirmed baseline was reused unchanged on ETH-USD and SOL-USD (see
`multi_asset.py` results below), it failed on both -- these numbers are a
starting point for other coins, not a drop-in. Re-run the tuning process
(`grid_search.py`, then hand-tune) per asset.

CLAUDE.md's Success/Failure thresholds, for reference:
- **Success**: return >= +5%/30d, Sharpe >= 1.2, drawdown <= 8%
- **Failure**: drawdown > 8%, return < -4%/30d, Sharpe < 0

## The one configuration that passed full Success

Only one tested configuration in this entire project cleared **all three**
Success conditions simultaneously with no Failure breach. It requires real
leveraged/margin position sizing, not just the base strategy, and the safety
margin is razor-thin -- **not recommended as a live template as-is**, recorded
here for completeness and as a reference point, not an endorsement.

```
--rsi-entry 28 --rsi-exit 29 --stop-loss-pct 5.0 --position-size-r 6.7
--enable-short --short-rsi-entry 78 --short-rsi-exit 65
--enable-range-filter --range-ma-period 200 --range-max-distance-pct 2.5
```

| Metric | Value | vs. threshold |
|---|---|---|
| Win rate | 79.8% | -- |
| Trades | 89 (long 79, short 10) | -- |
| Total return (730d) | +25.27% | -- |
| Sharpe | +1.53 | clears >=1.2 |
| Max drawdown | -5.69% | clears <=8% |
| Worst rolling 30d | -3.99% | clears (Failure line is -4%; margin = 0.01pp) |
| Best rolling 30d | +5.03% | clears >=5% (margin = 0.03pp) |

Caveats (all still apply, unchanged from when this was first found):
- `position-size-r 6.7` (13.4x the base 0.5R) implies ~1.34x actual notional
  leverage given the 5% stop -- real borrowed margin, not just "invest more."
- No fees, slippage, funding costs, or liquidation risk are modeled. At
  margins this thin (0.01-0.03 percentage points), real trading costs alone
  could flip this back to failing.
- The short leg (10 of 89 trades) is backtest-only -- Kraken spot can't
  execute it without a separate margin/futures account.
- One historical 730-day window. Being exactly on the boundary on one
  backtest is not evidence it holds in a different period.

Nearby leverage levels that did **not** pass (for context on how narrow this
window is): `--position-size-r 6.5` stayed safe (no Failure breach) but fell
just short of the return target (best 30d +4.88%, vs +5% needed).
`--position-size-r 7.0` cleared the return target (+5.26%) but breached the
Failure line on worst 30d (-4.16%, vs the -4% limit). 6.7 is the single point
found where both sides work at once.

## Confirmed baselines (win rate >= 70%, clear Failure, but short of full Success)

These are the safer, non-leveraged reference points -- each cleared every
Failure condition and usually 2 of 3 Success conditions (Sharpe, drawdown),
but none cleared the 30-day return target. Listed oldest to newest; each
superseded the last as the project's official CLAUDE.md baseline.

### Current baseline (2026-07-24) -- ATR-based stop
```
--rsi-entry 28 --rsi-exit 29 --enable-atr-stop --atr-period 21 --atr-multiplier 2.0
--enable-short --short-rsi-entry 78 --short-rsi-exit 65
--enable-range-filter --range-ma-period 200 --range-max-distance-pct 3.0
```
74.0% win rate, 131 trades, +8.01% return (730d), Sharpe +1.38, max drawdown
-1.84%, worst 30d -1.27%, best 30d +2.40%. Closest any non-leveraged baseline
got to the return target. Replacing the fixed stop with a volatility-adjusted
one (this change alone) roughly 4.6x'd return over the prior baseline.

### Prior baseline -- fixed 5.0% stop
```
--rsi-entry 28 --rsi-exit 29 --stop-loss-pct 5.0
--enable-short --short-rsi-entry 78 --short-rsi-exit 65
--enable-range-filter --range-ma-period 200 --range-max-distance-pct 3.0
```
76.3% win rate, 114 trades, +1.75% return, Sharpe +1.31, max drawdown -0.42%,
best 30d +0.38%.

### Prior baseline -- 2.5% range filter (before widening to 3.0%)
```
--rsi-entry 28 --rsi-exit 29 --stop-loss-pct 5.0
--enable-short --short-rsi-entry 78 --short-rsi-exit 65
--enable-range-filter --range-ma-period 200 --range-max-distance-pct 2.5
```
79.8% win rate (highest of any non-leveraged config), 89 trades, Sharpe +1.53
(highest Sharpe of any non-leveraged config), max drawdown -0.42% -- but
only 89 trades meant lower absolute return than the two baselines above. This
is the un-leveraged base that the "full Success" leveraged result above was
built on top of.

### Win-rate-focused baseline (no range filter)
```
--rsi-entry 27 --rsi-exit 30 --stop-loss-pct 4.5
--enable-short --short-rsi-entry 78 --short-rsi-exit 62
```
71.5% win rate, 207 trades, +0.18% return, Sharpe +0.06, max drawdown -2.01%,
worst 30d -0.84%, best 30d +1.05%. Clears Failure only -- Sharpe far short of
1.2. Notable mainly as the first configuration to cross 70% win rate; single-
variable tuning alone (without the range filter) couldn't get Sharpe higher
than this.

## Tested and discarded (win rate >= 70%, but breaches a Failure condition)

### Naive multi-asset diversification (BTC/ETH/SOL, BTC-tuned parameters reused unchanged)
```
python multi_asset.py --enable-short --enable-range-filter
# uses the ATR-stop baseline's parameters, applied unchanged to all 3 symbols
```
Combined portfolio: 70.8% win rate (>=70%, qualifies on that filter alone),
226 trades, -0.60% return, **Sharpe -0.51 (breaches the Sharpe < 0 Failure
condition)**, max drawdown -0.86%. Per-asset breakdown: BTC-USD alone matched
its own baseline exactly (76.3% win, Sharpe +1.31), but ETH-USD (Sharpe -0.67)
and SOL-USD (Sharpe -1.62) both did badly with BTC's tuned numbers, dragging
the combined Sharpe negative. This is a curve-fitting lesson, not proof
diversification doesn't work -- no ETH/SOL-specific tuning was attempted.

## Strategies tested with win rate well under 70% (ruled out at default settings)

Recorded so future sessions don't have to re-discover these are dead ends at
these settings -- none were deeply tuned, so a tuned version might behave
differently, but neither showed enough promise on a first real-data pass to
justify the effort.

| Strategy | Parameters | Win rate | Sharpe | Max DD | Verdict |
|---|---|---|---|---|---|
| Trend-following (MA crossover) | `--fast-ma-period 20 --slow-ma-period 50 --enable-short` | 36.8% | -0.16 | -9.73% | Breaches 2 Failure conditions |
| Bollinger Bands | `--bb-period 20 --bb-std-mult 2.0 --enable-short` | 63.7% | -0.30 | -5.18% | Breaches Sharpe Failure |
| Original CLAUDE.md spec | `--rsi-entry 25 --rsi-exit 50 --stop-loss-pct 1.4` (no short, no filters) | 35.4% | -0.76 | -12.40% | Breaches all 3 Failure conditions |

## Tools to reproduce or extend any of this

- `Backtest/backtest.py` -- the RSI+range-filter+ATR-stop strategy (single run)
- `Backtest/grid_search.py` -- joint parameter search over the same strategy
- `Backtest/trend_strategy.py`, `Backtest/bollinger_strategy.py` -- alternative signals
- `Backtest/multi_asset.py` -- portfolio runner across multiple symbols

All support `--source ccxt --exchange <id> --symbol <PAIR>` for other coins,
though note Kraken's ccxt pagination is capped at ~30 days of history (see
`Backtest/README.md` "Known gotcha") -- use `--source yfinance` with a ticker
like `ETH-USD` or `SOL-USD` for full-history backtests on other coins.
