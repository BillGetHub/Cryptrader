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

- Entry: RSI(14) < 25
- Stop: 1.4% below entry
- Size: 0.5R (percent of account balance risked per trade)
- Exit: stop hit, or RSI recovers to >= 50 (mean-reversion exit) -- **not** part of
  the CLAUDE.md spec, it's a default assumption needed to close a trade. Tune it
  with `--rsi-exit` like any other variable.

By default only the long side above is simulated, matching CLAUDE.md and `bot.py`.
`--enable-short` (off by default) adds an independent short leg with its own RSI
bands (`--short-rsi-entry` / `--short-rsi-exit`) -- **backtest-only**. Kraken spot,
the venue `bot.py` trades on, has no native short selling; that would require a
margin/futures account with liquidation risk and funding costs this harness
doesn't model. Don't treat a short-enabled result as ready for live trading.

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
| `--rsi-entry` | `25` | |
| `--rsi-exit` | `50` | mean-reversion exit, not in spec |
| `--stop-loss-pct` | `1.4` | |
| `--position-size-r` | `0.5` | |
| `--enable-short` | off | backtest-only, see caveat above |
| `--short-rsi-entry` | `75` | short when RSI rises above this (only with `--enable-short`) |
| `--short-rsi-exit` | `65` | cover when RSI falls back to this (only with `--enable-short`) |
| `--initial-balance` | `10000` | |
| `--csv-out` | none | optional path to dump the equity curve |

## Scientific-approach workflow (per CLAUDE.md)

Change one flag at a time, re-run, and compare the printed metrics against the
current baseline before treating a change as an improvement:

```bash
python backtest.py --rsi-entry 20   # vs. baseline --rsi-entry 25
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

It prints how many combinations clear a 70% win rate and the top results
ranked by win rate (Sharpe as tiebreaker). Edit the `*_GRID` constants at the
top of `grid_search.py` to widen, narrow, or shift the search -- the default
grid (~486 combinations, ~10-15s on 730 days of hourly data) covers:
`--stop-loss-pct`, `--rsi-entry`, `--rsi-exit`, `--short-rsi-entry`,
`--short-rsi-exit`, `--rsi-period`, always with `--enable-short` on. Entry/exit
bands that would overlap (e.g. `--rsi-entry` >= `--rsi-exit`, which causes
whipsaw trades -- see the "known trap" below) are skipped automatically.

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
