# Validated Parameters Reference

A catalog of every tested configuration from this project's tuning history with
**win rate >= 70%**, for reuse when exploring other coins, other strategies, or
improved versions. All numbers below come from real backtests (1h candles,
730-day window) run and pasted during actual sessions -- nothing here is
estimated or re-derived from memory.

**Important scope note:** parameters tuned for one coin do not transfer to
another. BTCUSDT's confirmed baseline reused unchanged on ETH-USD and SOL-USD
(see "Tested and discarded" below) failed on both -- and ETHUSDT's own tuned
baseline (below) uses a genuinely different strategy shape than BTC's (no
ATR-stop, shorter RSI period, a much lower short-exit threshold). Each new
coin needs its own run through the tuning process (`grid_search.py`, then
hand-tune), not a copy of another coin's numbers.

**Data source note:** BTCUSDT results below were fetched as `BTC-USD` via
`yfinance` (Yahoo has no `BTC-USDT` ticker). ETHUSDT results were fetched as
genuine `ETH/USDT` via `--source ccxt --exchange binance` (Yahoo has no
`ETH-USDT` ticker either, and Kraken's ccxt pagination caps out around 30
days -- Binance has neither limitation, confirmed 2026-07-24). See
`Backtest/README.md` for the full symbol-normalization and data-source notes.

CLAUDE.md's Success/Failure thresholds, for reference:
- **Success**: return >= +5%/30d, Sharpe >= 1.2, drawdown <= 8%
- **Failure**: drawdown > 8%, return < -4%/30d, Sharpe < 0

# BTCUSDT

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

## BTCUSDT: tested and discarded (win rate >= 70%, but breaches a Failure condition)

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
the combined Sharpe negative. This is the curve-fitting lesson that motivated
tuning ETHUSDT properly on its own -- see below.

## BTCUSDT: strategies well under 70% win rate (ruled out at default settings)

Recorded so future sessions don't have to re-discover these are dead ends at
these settings -- none were deeply tuned, so a tuned version might behave
differently, but neither showed enough promise on a first real-data pass to
justify the effort.

| Strategy | Parameters | Win rate | Sharpe | Max DD | Verdict |
|---|---|---|---|---|---|
| Trend-following (MA crossover) | `--fast-ma-period 20 --slow-ma-period 50 --enable-short` | 36.8% | -0.16 | -9.73% | Breaches 2 Failure conditions |
| Bollinger Bands | `--bb-period 20 --bb-std-mult 2.0 --enable-short` | 63.7% | -0.30 | -5.18% | Breaches Sharpe Failure |
| Original CLAUDE.md spec | `--rsi-entry 25 --rsi-exit 50 --stop-loss-pct 1.4` (no short, no filters) | 35.4% | -0.76 | -12.40% | Breaches all 3 Failure conditions |

# ETHUSDT

## Confirmed baseline (2026-07-24)

Tuned independently from BTC via `grid_search.py` (grid shifted/widened once
BTC's ranges hit an edge on 4 parameters) then hand-bracketed, the same
process used for BTC. Notably **does not** use ATR-stop -- every ATR
variant tested made ETH's Sharpe worse, the opposite of what ATR-stop did
for BTC.

```
--rsi-entry 28 --rsi-exit 29 --rsi-period 12 --stop-loss-pct 4.5
--enable-short --short-rsi-entry 76 --short-rsi-exit 45
--enable-range-filter --range-ma-period 200 --range-max-distance-pct 2.5
```

| Metric | Value | vs. threshold |
|---|---|---|
| Win rate | 78.1% | -- |
| Trades | 105 (long 74, short 31) | -- |
| Total return (730d) | +3.55% | -- |
| Sharpe | +1.25 | clears >=1.2 |
| Max drawdown | -2.64% | clears <=8% |
| Worst rolling 30d | -1.53% | safe (Failure line is -4%) |
| Best rolling 30d | +1.33% | short of +5% target |

Same shape of result as BTC's journey: clears Sharpe and drawdown for
Success, still short on the 30-day return leg. Fetched via
`--source ccxt --exchange binance --symbol ETHUSDT` (genuine USDT pair, full
730-day history).

### What was tried and discarded reaching this baseline
- **Reusing BTC's exact tuned parameters unchanged**: 63.0% win rate (yfinance
  ETH-USD proxy) / 62.2% (genuine Binance ETH/USDT) -- both **breach the
  Sharpe < 0 Failure condition** (-0.05 and -0.11 respectively). Confirmed
  BTC's numbers don't transfer; motivated the independent tuning above.
- **ATR-stop on the ETH-tuned base** (ATR(21)x2.0, ATR(14)x2.0, ATR(21)x3.0):
  all three underperformed the plain fixed-percentage stop (Sharpe 0.46, 0.39,
  0.31 respectively, vs 0.83 for the fixed-stop grid result at the time).
  Fixed stop is genuinely better for ETH, not just an untried lever.
- **`--short-rsi-exit`** was bracketed through 54 (Sharpe 1.186) -> 51 (1.01,
  a non-monotonic dip) -> 48 (1.19) -> **45 (1.25, the peak)** -> 40 (0.94,
  confirms the peak). This single lever took Sharpe from 0.83 to 1.25.
- **Trend-following** (`--fast-ma-period 20 --slow-ma-period 50 --enable-short`
  on Binance ETH/USDT): 455 trades, 36.5% win rate, Sharpe -0.16, max drawdown
  **-11.30%** -- breaches 3 Failure conditions at once (worse than on BTC).
- **Bollinger Bands** (`--bb-period 20 --bb-std-mult 2.0 --enable-short` on
  Binance ETH/USDT): 757 trades, 63.8% win rate, Sharpe -0.77, max drawdown
  -9.16% -- breaches 2 Failure conditions.

Both alternative signals failed harder on ETH than on BTC (more trades,
deeper drawdowns) -- reinforces that the range-filtered RSI mean-reversion
approach fits this market's actual behavior, rather than being an accident
of BTC-specific tuning.

# BNBUSDT

## Confirmed baseline (2026-07-24)

Tuned independently via three successive widening passes of `grid_search.py`
(first pass hit the edge on rsi_entry, rsi_exit, rsi_period, and
range_max_distance_pct; second pass already cleared Sharpe/drawdown Success
but hit the edge again on stop_loss_pct, rsi_exit, short_rsi_entry, and
short_rsi_exit; third pass widened those further and fixed rsi_period at its
twice-confirmed peak of 12). Every parameter dimension is now confirmed
bracketed -- none sit on a search-range edge. Does **not** use ATR-stop
(not swept for BNB, matching ETH's finding rather than BTC's).

```
--rsi-entry 27 --rsi-exit 29 --rsi-period 12 --stop-loss-pct 5.0
--enable-short --short-rsi-entry 78 --short-rsi-exit 45
--enable-range-filter --range-ma-period 200 --range-max-distance-pct 4.0
```

| Metric | Value | vs. threshold |
|---|---|---|
| Win rate | 75.7% | -- |
| Trades | 152 | -- |
| Total return (730d) | +3.56% | -- |
| Sharpe | +1.51 | clears >=1.2 (best of all three coins: BTC 1.38, ETH 1.25, BNB 1.51) |
| Max drawdown | -1.32% | clears <=8% |
| Worst rolling 30d | -0.71% | safe (Failure line is -4%) |
| Best rolling 30d | +0.80% | short of +5% target |

Same shape of result as BTC's and ETH's: clears Sharpe and drawdown for
Success, still short on the 30-day return leg. Fetched via
`--source ccxt --exchange binance --symbol BNBUSDT` (genuine USDT pair, full
730-day history).

Shares ETH's RSI period (12, not BTC's 14) and absence of an ATR-stop, but
its own values elsewhere -- rsi-entry 27 (vs BTC/ETH's 28), short-rsi-exit 45
(matching ETH, not BTC's 65), range filter widened to 4.0% (vs BTC/ETH's
3.0%/2.5%-3.0%). Confirms again that each coin needs its own tuning pass
rather than reused parameters.

### What was tried and discarded reaching this baseline
- **Bollinger Bands** (`--bb-period 20 --bb-std-mult 2.0 --enable-short` on
  Binance BNB/USDT): 685 trades, 63.6% win rate (long 67.0%, short 59.9%),
  Sharpe -0.36, max drawdown -6.94%, **worst rolling 30d -4.11% -- breaches
  the -4%/30d Failure line outright**, not just a soft Sharpe miss. The only
  alternative-strategy test across all three coins to breach a hard Failure
  threshold rather than just falling short of Success.
- **Trend-following** (`--fast-ma-period 20 --slow-ma-period 50 --enable-short`
  on Binance BNB/USDT): not yet run to completion -- command issued but
  result not yet captured. Given trend-following breached 2-3 Failure
  conditions on both BTC and ETH, expected to underperform here too, but
  not confirmed.

## Tools to reproduce or extend any of this

- `Backtest/backtest.py` -- the RSI+range-filter+ATR-stop strategy (single run)
- `Backtest/grid_search.py` -- joint parameter search over the same strategy
- `Backtest/trend_strategy.py`, `Backtest/bollinger_strategy.py` -- alternative signals
- `Backtest/multi_asset.py` -- portfolio runner across multiple symbols

All support `--source ccxt --exchange <id> --symbol <PAIR>` for other coins.
**Confirmed 2026-07-24: `--exchange binance` has none of Kraken's ~30-day
pagination cap** -- it delivers the full 730-day window for genuine USDT
pairs (used to produce all the ETHUSDT results above). Kraken remains capped
at ~30 days; yfinance has no `*-USDT` tickers at all, only fiat pairs like
`ETH-USD` (confirmed by a live 404). Recommended per-source symbol pattern:
`--source ccxt --exchange binance --symbol <COIN>USDT` for genuine full-
history USDT data, or `--source yfinance --symbol <COIN>-USD` as a close
fiat proxy if Binance access isn't available -- see `Backtest/README.md` for
the full normalization details and the ETH-USD-vs-ETH/USDT cross-check that
validated the proxy is reasonable.
