# Backtest

Backtests the RSI mean-reversion strategy defined in `CLAUDE.md` against historical
data, so the strategy can be validated against the project's success/failure
thresholds before anything touches the live bot in `References/LiveTradingBots/`.

Two free data sources are supported, picked with `--source`:

- `yfinance` (default): Yahoo Finance via the `yfinance` package.
- `ccxt`: a crypto exchange's own public REST API via `ccxt` -- no API key needed
  for OHLCV data. Defaults to Kraken, the same venue `bot.py` actually trades on,
  so backtest and live signals see identical prices (no Yahoo-vs-exchange
  discrepancy). It's also not subject to Yahoo's intraday history cap, though a
  long `--period` means more paginated API requests.

Defaults reflect the confirmed baseline in CLAUDE.md (2026-07-24), found via
`grid_search.py`: 79.8% win rate, +1.72% return, Sharpe +1.53, max drawdown
-0.42%, worst rolling 30d -0.30%, best rolling 30d +0.37% on BTC-USD 1h/730d.
Sharpe and drawdown now clear CLAUDE.md's Success thresholds, but 30d return
(+0.37% best) is far short of +5%/30d -- with only ~89 trades over 730 days
and 0.5R risk per trade, this is a very safe configuration but structurally
capped on absolute return. See CLAUDE.md for the full note.

- Entry: RSI(14) < 28
- Stop: 5.0% below entry
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
`--range-max-distance-pct` (default 2.5%) of the `--range-ma-period` (default
200) SMA -- filtering strong trends *out* instead of trading with them. This was
the single biggest improvement found in this project (Sharpe +0.06 -> +1.53
combined with the other baseline tuning).

## Install

```bash
cd Backtest
pip install -r requirements.txt
```

## Run

```bash
# Yahoo Finance (default)
python backtest.py --symbol BTC-USD --interval 1h --period 730d

# Kraken via ccxt -- free, no API key, matches the live bot's venue
python backtest.py --source ccxt --exchange kraken --symbol BTC/USD --interval 1h --period 730d
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
| `--symbol` | `BTC-USD` (yfinance) / `BTC/USD` (ccxt) | Yahoo ticker or ccxt unified symbol, depending on `--source` |
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
| `--range-max-distance-pct` | `2.5` | max %% distance from the SMA allowed for an entry (only with `--enable-range-filter`) |
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
python grid_search.py --symbol BTC-USD --interval 1h --period 730d
python grid_search.py --source ccxt --exchange kraken --symbol BTC/USD --interval 1h --period 730d --csv-out results.csv
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

## Known limitation in this environment

Neither Yahoo Finance nor Kraken's public API is reachable through this sandbox's
outbound network policy (both return a proxy 403), regardless of `--source`. The
simulation, metrics, and ccxt pagination logic are all verified against synthetic
OHLC data instead. Run this script somewhere with unrestricted internet access
(or adjust the environment's network policy) to fetch real data.
