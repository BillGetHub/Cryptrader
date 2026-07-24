# Backtest

Backtests the RSI mean-reversion strategy defined in `CLAUDE.md` against historical
data, so the strategy can be validated against the project's success/failure
thresholds before anything touches the live bot in `References/LiveTradingBots/`.

Two free data sources are supported, picked with `--source`:

- `yfinance` (default): Yahoo Finance via the `yfinance` package. Free tier is
  subject to rate limiting (`YFRateLimitError`) if hit too often in a short
  span -- wait a minute or two and retry, or switch to `--source ccxt`.
- `ccxt`: a crypto exchange's own public REST API via `ccxt` -- no API key needed
  for OHLCV data. Defaults to Kraken, the same venue `bot.py` actually trades on,
  so backtest and live signals see identical prices (no Yahoo-vs-exchange
  discrepancy). **Known gotcha:** Kraken's public OHLC endpoint does not
  actually support deep historical pagination -- despite `fetch_data_ccxt()`
  requesting data back to `--period`, Kraken only ever returns its most recent
  ~720 candles regardless of the requested `since` (confirmed 2026-07-24:
  requesting 730 days of 1h data returned only ~721 bars, i.e. ~30 days). Use
  `--source ccxt --exchange kraken` for short lookback windows or live/recent
  signals only. **`--exchange binance` does not have this limitation**
  (confirmed 2026-07-24: `--symbol ETHUSDT --period 730d --interval 1h`
  returned exactly 17,520 bars, i.e. the full 730 days) -- use it for full-
  history backtests on genuine USDT pairs. `bot.py` still targets Kraken for
  live trading; this only affects which source to backtest against.

`--symbol` defaults to a bare pair like `BTCUSDT` -- it's auto-normalized to
whatever separator each source needs (`BTC-USDT` for yfinance, `BTC/USDT` for
ccxt) before being used, so the same bare symbol works with either `--source`.
A symbol that already contains `/` or `-` is left untouched. **Confirmed
gotcha (2026-07-24):** yfinance has no `ETH-USDT` ticker (404s) -- only fiat
tickers like `ETH-USD` exist there. For yfinance, pass the fiat pair
explicitly (e.g. `--symbol ETH-USD`) rather than relying on auto-
normalization; for genuine USDT pairs with full history, use
`--source ccxt --exchange binance` instead. ETH-USD (yfinance) and ETH/USDT
(Binance) were cross-checked on the same BTC-tuned strategy and produced
near-identical results (win rate 63.0% vs 62.2%, Sharpe -0.05 vs -0.11) --
USDT tracks USD closely enough that the fiat pair is a reasonable backtesting
proxy when a real USDT ticker isn't available on a given source.

Defaults reflect the confirmed baseline in CLAUDE.md (2026-07-24): 74.0% win
rate, +8.01% return, Sharpe +1.38, max drawdown -1.84%, worst rolling 30d
-1.27%, best rolling 30d +2.40%, 131 trades on BTC-USD 1h/730d. Sharpe and
drawdown clear CLAUDE.md's Success thresholds by a wide margin, but 30d
return (+2.40% best) is still short of +5%/30d -- closer than any prior
baseline, but not there yet. See CLAUDE.md for the full note.

- Entry: RSI(14) < 28
- Stop: volatility-adjusted -- 2.0x ATR(21), not a fixed percentage (`--enable-atr-stop`,
  part of the confirmed baseline; use `--stop-loss-pct` for a fixed-percentage stop instead)
- Size: 0.5R (percent of account balance risked per trade)
- Exit: stop hit, or RSI recovers to >= 29 (mean-reversion exit) -- **not** part of
  the original CLAUDE.md spec, it's an assumption needed to close a trade. Tune it
  with `--rsi-exit` like any other variable.

By default only the long side above is simulated, matching CLAUDE.md and `bot.py`.
`--enable-short` (off by default) adds an independent short leg with its own RSI
bands (`--short-rsi-entry 78` / `--short-rsi-exit 65` by default) -- **backtest-only**,
and part of the confirmed baseline above. Kraken spot, the venue `bot.py` trades on,
has no native short selling; that would require a margin/futures account with
liquidation risk and funding costs this harness doesn't model. Don't treat a
short-enabled result as ready for live trading.

`--enable-trend-filter` (off by default) only allows a long entry when price is
above the `--trend-ma-period` (default 200) simple moving average, and a short
entry only below it -- i.e. trade *with* the trend. **Tested and discarded**
(CLAUDE.md, 2026-07-24): hurt Sharpe/return at both a 200-bar and 500-bar SMA on
BTC-USD 1h/730d, likely because it's really a different strategy (buy-the-dip-in-
an-uptrend) rather than a refinement of RSI mean reversion.

`--enable-range-filter` (off by default, but part of the confirmed baseline when
on) is the opposite hypothesis: RSI mean reversion tends to work best when price
is *ranging* near its average and worst in strong trends either direction, so
this only allows an entry (long or short) when price is within
`--range-max-distance-pct` (default 3.0%) of the `--range-ma-period` (default
200) SMA -- filtering strong trends *out* instead of trading with them. This was
the single biggest improvement found in this project (Sharpe +0.06 -> +1.53 at
2.5% distance, then widened to 3.0% to trade a little Sharpe for more trade
frequency -> +1.31 Sharpe, 114 trades vs 89). Not a smooth tradeoff: 4% and 5%
distance both dropped Sharpe well below 1.2 (0.25 and 0.57), so 3% is a
verified local sweet spot, not the start of a predictable curve.

`--enable-atr-stop` (off by default, but part of the confirmed baseline when
on) replaces the fixed `--stop-loss-pct` stop with one sized off recent
volatility: stop distance = `--atr-multiplier` * ATR(`--atr-period`) at entry,
instead of the same fixed percentage regardless of how calm or volatile the
market currently is. **The single biggest improvement of the whole project**:
tested against the fixed 5.0% stop on real data (2026-07-24) and roughly
4.6x'd total return (+1.75% -> +8.01%) while also raising Sharpe (+1.31 ->
+1.38). Both ATR parameters were bracketed and confirmed as local peaks --
`--atr-multiplier` 1.5 and 2.5 were both worse (Sharpe 1.14 and 0.99 vs 2.0's
1.38); `--atr-period` 10 and 30 were both worse (Sharpe 1.21 and 1.16 vs 21's
1.38).

## Install

```bash
cd Backtest
pip install -r requirements.txt
```

## Run

```bash
# Yahoo Finance (default)
python backtest.py --symbol BTCUSDT --interval 1h --period 730d

# Kraken via ccxt -- free, no API key, matches the live bot's venue
python backtest.py --source ccxt --exchange kraken --symbol BTCUSDT --interval 1h --period 730d
```

Output reports total return, annualized Sharpe, max drawdown, win rate, and the
worst/best rolling 30-day return, then compares them against the CLAUDE.md
thresholds:

- Success: return >= +5%/30d, Sharpe >= 1.2, drawdown <= 8%
- Failure: drawdown > 8%, return < -4%/30d, Sharpe < 0

## Options

| Flag | Default | Notes |
|---|---|---|
| `--source` | `yfinance` | `yfinance` or `ccxt` |
| `--exchange` | `kraken` | ccxt exchange id, only used with `--source ccxt` (any exchange ccxt supports) |
| `--symbol` | `BTCUSDT` | Bare pair auto-normalized per source (`BTC-USDT` for yfinance, `BTC/USDT` for ccxt); a symbol already containing `/` or `-` is used as-is |
| `--interval` | `1h` | `1m`,`5m`,`15m`,`30m`,`1h`,`1d` |
| `--period` | `730d` | Yahoo caps intraday history: `1h` ~730 days, `1m` ~7 days (`1d` has no cap). ccxt has no such cap, but longer periods mean more paginated requests. |
| `--rsi-period` | `14` | |
| `--rsi-entry` | `28` | |
| `--rsi-exit` | `29` | mean-reversion exit, not in spec |
| `--stop-loss-pct` | `5.0` | |
| `--position-size-r` | `0.5` | |
| `--enable-short` | off | backtest-only, see caveat above; part of the confirmed baseline when on |
| `--short-rsi-entry` | `78` | short when RSI rises above this (only with `--enable-short`) |
| `--short-rsi-exit` | `65` | cover when RSI falls back to this (only with `--enable-short`) |
| `--enable-trend-filter` | off | longs only above the trend SMA, shorts only below it; tested and discarded |
| `--trend-ma-period` | `200` | SMA period in bars (only with `--enable-trend-filter`) |
| `--enable-range-filter` | off | entries only within `--range-max-distance-pct` of the range SMA; part of the confirmed baseline when on |
| `--range-ma-period` | `200` | SMA period in bars (only with `--enable-range-filter`) |
| `--range-max-distance-pct` | `3.0` | max %% distance from the SMA allowed for an entry (only with `--enable-range-filter`) |
| `--enable-atr-stop` | off | volatility-adjusted stop instead of the fixed `--stop-loss-pct`; part of the confirmed baseline when on |
| `--atr-period` | `21` | ATR period in bars (only with `--enable-atr-stop`) |
| `--atr-multiplier` | `2.0` | stop distance as a multiple of ATR (only with `--enable-atr-stop`) |
| `--initial-balance` | `10000` | |
| `--csv-out` | none | optional path to dump the equity curve |

## Scientific-approach workflow (per CLAUDE.md)

Change one flag at a time, re-run, and compare the printed metrics against the
current baseline before treating a change as an improvement:

```bash
python backtest.py --rsi-entry 25   # vs. baseline --rsi-entry 28
```

Per CLAUDE.md, confirm with the project owner before adopting a new baseline.

## Joint grid search

One-variable-at-a-time tuning can get stuck at a local maximum -- moving any
single lever from that point makes things worse, even though a *combination*
of moves might not. `grid_search.py` fetches the data once, then re-runs the
(fast, local, no-network) simulation for every combination in a parameter grid
centered on the local optimum found by hand:

```bash
python grid_search.py --symbol BTCUSDT --interval 1h --period 730d
python grid_search.py --source ccxt --exchange kraken --symbol BTCUSDT --interval 1h --period 730d --csv-out results.csv
```

It prints how many combinations clear a 70% win rate, how many clear CLAUDE.md's
Success thresholds (return >= +5%/30d, Sharpe >= 1.2, drawdown <= 8% -- using
the actual rolling 30-day return, not the total-period return), and how many
still hit a Failure condition, then the top results ranked by `--sort-by`
(`win_rate`, `sharpe`, or `return`; default `sharpe`, since that's the current
gap versus Success). Edit the `*_GRID` constants at the top of `grid_search.py`
to widen, narrow, or shift the search -- the default grid (~972 combinations,
~30-40s on 730 days of hourly data) covers: `--stop-loss-pct`, `--rsi-entry`,
`--rsi-exit`, `--short-rsi-entry`, `--short-rsi-exit`, `--rsi-period`, and
`--range-max-distance-pct`, always with `--enable-short` and
`--enable-range-filter` on (`--range-ma-period` fixed at 200, confirmed best by
hand). Entry/exit bands that would overlap (e.g. `--rsi-entry` >= `--rsi-exit`,
which causes whipsaw trades -- see the "known trap" below) are skipped
automatically.

**Known trap:** the long entry threshold must stay below the exit threshold
(and the short entry must stay above the short exit). If they cross, a
position can open and then immediately satisfy the exit condition on the next
bar, producing a flood of near-instant whipsaw trades that look like more
data but are actually noise -- trade count spikes and every metric gets worse.

## Alternative strategies

Three more scripts, built to test whether a genuinely different approach beats
threshold-tuning the RSI signal further. **All three tested and discarded**
(CLAUDE.md, 2026-07-24) -- none beat the RSI baseline, and two actively breach
Failure conditions with default parameters. None have been tuned further
beyond their defaults; a tuned version of any of them might do better, but
none showed enough promise on a first real-data pass to justify the effort
the way the ATR-stop refinement did.

**`trend_strategy.py`** -- classic fast/slow moving-average crossover trend
following. Genuinely complementary to the RSI approach rather than a variant
of it: the range filter above specifically *excludes* trending periods, so
this strategy trades exactly the conditions RSI mean reversion sits out.
Long while the fast SMA is above the slow SMA, short (opt-in) while below,
exit on trend flip or stop hit. **Result at defaults (20/50 SMA):** 405
trades, 36.8% win rate, -1.68% return, Sharpe -0.16, max drawdown -9.73% --
breaches two Failure conditions. Likely whipsawing badly on this data; a much
slower MA pair might behave differently but wasn't tested.

```bash
python trend_strategy.py --symbol BTCUSDT --interval 1h --period 730d
python trend_strategy.py --fast-ma-period 20 --slow-ma-period 50 --enable-short
```

**`bollinger_strategy.py`** -- Bollinger Band mean reversion, an alternative
math family to RSI for the same "buy oversold, sell overbought" idea: entries
are measured in standard deviations from a rolling average instead of RSI's
momentum oscillator. Long when price closes below the lower band, short
(opt-in) above the upper band, exit on reversion to the middle band or stop
hit. **Result at defaults (20-period, 2 std dev):** 669 trades, 63.7% win
rate, -2.21% return, Sharpe -0.30, max drawdown -5.18% -- breaches the Sharpe
Failure condition (drawdown stays safe).

```bash
python bollinger_strategy.py --symbol BTCUSDT --interval 1h --period 730d
python bollinger_strategy.py --bb-period 20 --bb-std-mult 2.0 --enable-short
```

**`multi_asset.py`** -- runs the confirmed RSI+range-filter strategy
independently across several pairs (BTC/ETH/SOL by default) with capital split
evenly, then combines the daily-resampled equity curves into one portfolio.
Tests diversification rather than a new signal: spreading the same edge across
less-than-perfectly-correlated assets can raise portfolio Sharpe without
raising any single position's risk. Note the portfolio Sharpe is computed on
*daily* returns (different pairs' fetched bars don't align hour-to-hour), so
it isn't directly comparable to `backtest.py`'s hourly Sharpe -- compare each
symbol's own per-asset Sharpe in the printed breakdown instead for an apples-
to-apples check against the single-asset baseline. **Result** (BTC/ETH/SOL,
BTC-tuned parameters reused unchanged): BTC alone matched the single-asset
baseline exactly (Sharpe +1.31), but ETH (-0.67) and SOL (-1.62) both did
badly with those same numbers, dragging the combined portfolio to Sharpe -0.51
-- a curve-fitting lesson, not evidence diversification itself doesn't work:
the parameters were extensively grid-searched specifically for BTC's
behavior, so there was no reason to expect them to transfer unchanged.
A fair test would need each asset's own tuned parameters, not attempted here.

```bash
python multi_asset.py --interval 1h --period 730d
python multi_asset.py --source ccxt --exchange kraken --symbols "BTCUSDT,ETHUSDT,SOLUSDT" --enable-short --enable-range-filter
```

## Known limitation in this environment

Neither Yahoo Finance nor Kraken's public API is reachable through this sandbox's
outbound network policy (both return a proxy 403), regardless of `--source`. The
simulation, metrics, and ccxt pagination logic -- for `backtest.py` and all three
alternative-strategy scripts above -- are all verified against synthetic OHLC
data instead. Run these somewhere with unrestricted internet access (or adjust
the environment's network policy) to fetch real data.
