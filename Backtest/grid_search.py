"""Joint grid search over the RSI strategy's parameters, built on backtest.py.

Single-variable tuning (see README.md) hit a local maximum at 68.5% win rate
and couldn't clear it moving one lever at a time. This sweeps combinations of
levers together, fetching the data once and re-running the (fast, local,
no-network) simulation for every combination in the grid.

A joint search combining --enable-short with --enable-range-filter (only
trade when price is within X% of a 200-bar SMA -- i.e. filter OUT strong
trends, since RSI mean reversion works best range-bound) found a baseline
with 89 trades and Sharpe +1.53 at 2.5% range distance. Manually widening
the distance to trade a little Sharpe for more frequency found the current
confirmed baseline in CLAUDE.md (2026-07-24): 76.3% win rate, +1.75% return,
Sharpe +1.31, max drawdown -0.42%, 114 trades on BTC-USD 1h/730d --
    --rsi-entry 28 --rsi-exit 29 --stop-loss-pct 5.0
    --enable-short --short-rsi-entry 78 --short-rsi-exit 65
    --enable-range-filter --range-ma-period 200 --range-max-distance-pct 3.0
Note this isn't a monotonic tradeoff: 4% and 5% distance both dropped Sharpe
well below 1.2 (0.25 and 0.57) before 3% was found to be a local sweet spot,
so don't assume "more distance = more trades = smoothly less Sharpe" holds
outside the range already tested. Sharpe and drawdown clear CLAUDE.md's
Success thresholds, but 30d return (+0.38% best) is far short of +5%/30d --
even at 114 trades over 730 days with 0.5R risk per trade, this is a very
safe configuration but structurally capped on absolute return (see CLAUDE.md
for the full note; getting all three Success conditions at once likely needs
more frequent trading still or larger sizing, not just more threshold
tuning).

The *_GRID constants below are edited freely as tuning moves to new assets or
regions -- they are a scratch workspace, not a record. BTC's, ETH's, and
BNB's confirmed baselines are recorded permanently in CLAUDE.md and
Backtest/VALIDATED_PARAMETERS.md regardless of what the grid currently
contains (see VALIDATED_PARAMETERS.md for full per-coin detail). ETH's and
BNB's tuning both found their optimum far from BTC's on short_rsi_exit (45
vs BTC's 65) and rsi_period (12 vs BTC's 14) -- proof these are genuinely
asset-specific levers, not just tuning noise.

As of 2026-07-24 the grid is re-centered for a fresh BTC pass: the
multi-asset portfolio test surfaced that BTC's confirmed baseline (tuned and
validated only on Yahoo's BTC-USD) drops from Sharpe +1.38 to +0.59 when its
exact parameters are re-run on genuine Binance BTCUSDT data -- no longer
clearing the >=1.2 Success bar. BTC has never been tuned directly on
Binance, unlike ETH and BNB. This pass searches a space centered on BTC's
known Yahoo-tuned optimum (28/29/5.0/78/65/14/3.0) but wide enough either
side to let Binance's genuinely different price data find its own optimum,
the same way ETH's and BNB's grids started centered on a known region and
then widened toward wherever the edge-hits pointed. Note this grid does not
sweep --enable-atr-stop (matching how ETH/BNB were tuned) -- the plan is to
find the best fixed-stop config here first, then test adding ATR-stop on
top as a follow-up, mirroring exactly how the original Yahoo-data ATR-stop
win was discovered (found after the fixed-stop baseline, not as part of the
initial joint search).

Note: total_return_pct is the return over the whole fetched period, not a
30-day figure -- use worst_30d_return_pct / best_30d_return_pct to check
against CLAUDE.md's actual +5%/30d and -4%/30d thresholds.

Usage:
    python grid_search.py --symbol BTCUSDT --interval 1h --period 730d
    python grid_search.py --source ccxt --exchange kraken --symbol BTCUSDT --interval 1h --period 730d
    python grid_search.py --sort-by sharpe --top-n 20
"""
import argparse
import itertools
import time

import pandas as pd

from backtest import DEFAULT_SYMBOL, INTERVAL_BARS_PER_YEAR, compute_metrics, fetch_data, simulate

STOP_LOSS_PCT_GRID = [4.0, 4.5, 5.0, 5.5, 6.0]  # centered on BTC's Yahoo-tuned 5.0
RSI_ENTRY_GRID = [26, 27, 28, 29]  # centered on BTC's Yahoo-tuned 28
RSI_EXIT_GRID = [28, 29, 30, 31]  # centered on BTC's Yahoo-tuned 29
SHORT_RSI_ENTRY_GRID = [74, 76, 78, 80]  # centered on BTC's Yahoo-tuned 78
SHORT_RSI_EXIT_GRID = [45, 55, 65, 75]  # spans both BTC's Yahoo-tuned 65 and ETH/BNB's 45
RSI_PERIOD_GRID = [12, 14]  # BTC's Yahoo-tuned 14 vs ETH/BNB's shared 12 -- genuinely unknown for BTC/Binance
RANGE_MAX_DISTANCE_PCT_GRID = [2.5, 3.0, 3.5, 4.0]  # centered on BTC's Yahoo-tuned 3.0
RANGE_MA_PERIOD = 200  # confirmed best against 100 and 300 by hand (on BTC); not swept here

SORT_KEYS = {
    "win_rate": ["win_rate_pct", "sharpe"],
    "sharpe": ["sharpe", "win_rate_pct"],
    "return": ["best_30d_return_pct", "sharpe"],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Joint grid search for the RSI strategy's parameters.")
    parser.add_argument("--source", default="yfinance", choices=["yfinance", "ccxt"])
    parser.add_argument("--exchange", default="kraken")
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--interval", default="1h", choices=sorted(INTERVAL_BARS_PER_YEAR))
    parser.add_argument("--period", default="730d")
    parser.add_argument("--position-size-r", type=float, default=0.5)
    parser.add_argument("--initial-balance", type=float, default=10000.0)
    parser.add_argument(
        "--sort-by",
        default="sharpe",
        choices=sorted(SORT_KEYS),
        help="ranking used for the printed top results (default: sharpe, since that's the "
        "current CLAUDE.md Success gap). win_rate and return are also available.",
    )
    parser.add_argument("--top-n", type=int, default=15, help="how many top results to print")
    parser.add_argument("--csv-out", default=None, help="optional path to write every combination's results")
    args = parser.parse_args()
    if args.symbol is None:
        args.symbol = DEFAULT_SYMBOL[args.source]
    return args


def main() -> None:
    args = parse_args()

    print(f"Fetching {args.symbol} {args.interval} data ({args.source})...")
    df = fetch_data(args)
    print(f"Got {len(df)} bars. Sweeping the grid...")

    combos = [
        combo
        for combo in itertools.product(
            STOP_LOSS_PCT_GRID,
            RSI_ENTRY_GRID,
            RSI_EXIT_GRID,
            SHORT_RSI_ENTRY_GRID,
            SHORT_RSI_EXIT_GRID,
            RSI_PERIOD_GRID,
            RANGE_MAX_DISTANCE_PCT_GRID,
        )
        if combo[1] < combo[2] and combo[3] > combo[4]  # rsi_entry < rsi_exit, short_entry > short_exit
    ]
    print(f"{len(combos)} valid combinations (entry/exit bands non-overlapping).")

    start = time.time()
    results = []
    for i, (
        stop_loss_pct,
        rsi_entry,
        rsi_exit,
        short_rsi_entry,
        short_rsi_exit,
        rsi_period,
        range_max_distance_pct,
    ) in enumerate(combos):
        result = simulate(
            df,
            rsi_period,
            rsi_entry,
            rsi_exit,
            stop_loss_pct,
            args.position_size_r,
            args.initial_balance,
            enable_short=True,
            short_rsi_entry=short_rsi_entry,
            short_rsi_exit=short_rsi_exit,
            enable_range_filter=True,
            range_ma_period=RANGE_MA_PERIOD,
            range_max_distance_pct=range_max_distance_pct,
        )
        metrics = compute_metrics(
            result["equity"], result["trades"], args.initial_balance, INTERVAL_BARS_PER_YEAR[args.interval]
        )
        results.append(
            {
                "stop_loss_pct": stop_loss_pct,
                "rsi_entry": rsi_entry,
                "rsi_exit": rsi_exit,
                "short_rsi_entry": short_rsi_entry,
                "short_rsi_exit": short_rsi_exit,
                "rsi_period": rsi_period,
                "range_max_distance_pct": range_max_distance_pct,
                "win_rate_pct": metrics["win_rate_pct"],
                "total_return_pct": metrics["total_return_pct"],
                "worst_30d_return_pct": metrics["worst_30d_return_pct"],
                "best_30d_return_pct": metrics["best_30d_return_pct"],
                "sharpe": metrics["sharpe"],
                "max_drawdown_pct": metrics["max_drawdown_pct"],
                "num_trades": metrics["num_trades"],
            }
        )
        if (i + 1) % 200 == 0:
            print(f"  {i + 1}/{len(combos)} combinations done...")

    elapsed = time.time() - start
    print(f"Done in {elapsed:.1f}s.\n")

    results_df = pd.DataFrame(results)

    win_rate_ok = results_df["win_rate_pct"] >= 70.0
    success = (
        (results_df["best_30d_return_pct"] >= 5.0)
        & (results_df["sharpe"] >= 1.2)
        & (results_df["max_drawdown_pct"] >= -8.0)
    )
    failure = (
        (results_df["max_drawdown_pct"] < -8.0)
        | (results_df["worst_30d_return_pct"] < -4.0)
        | (results_df["sharpe"] < 0)
    )
    print(f"Combinations reaching >=70% win rate:        {win_rate_ok.sum()} / {len(results_df)}")
    print(f"Combinations clearing CLAUDE.md Success:      {success.sum()} / {len(results_df)}")
    print(f"Combinations still hitting CLAUDE.md Failure: {failure.sum()} / {len(results_df)}\n")

    sort_cols = SORT_KEYS[args.sort_by]
    results_df = results_df.sort_values(sort_cols, ascending=False)

    print(f"Top {args.top_n} by {args.sort_by} (tiebreak: {sort_cols[1]}):")
    with pd.option_context("display.max_columns", None, "display.width", 220):
        print(results_df.head(args.top_n).to_string(index=False))

    if args.csv_out:
        results_df.to_csv(args.csv_out, index=False)
        print(f"\nFull results ({len(results_df)} rows) written to {args.csv_out}")


if __name__ == "__main__":
    main()
