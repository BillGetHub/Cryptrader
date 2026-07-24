"""Joint grid search over the RSI strategy's parameters, built on backtest.py.

Single-variable tuning (see README.md) hit a local maximum at 68.5% win rate
and couldn't clear it moving one lever at a time. This sweeps combinations of
levers together, fetching the data once and re-running the (fast, local,
no-network) simulation for every combination in the grid. A win-rate-focused
run of this search found the confirmed baseline in CLAUDE.md (2026-07-24):
71.5% win rate, +0.18% return, Sharpe +0.06 on BTC-USD 1h/730d --
    --rsi-entry 27 --rsi-exit 30 --stop-loss-pct 4.5
    --enable-short --short-rsi-entry 78 --short-rsi-exit 62 --rsi-period 14
That clears CLAUDE.md's Failure conditions but not yet Success (return >=
+5%/30d, Sharpe >= 1.2). The grid below widens out from that baseline to
also cover combinations that flipped Sharpe/return positive during
single-variable testing but scored lower on win rate (e.g. short-rsi-entry
70, rsi-period 10) -- edit the *_GRID constants to widen or shift further.

Note: total_return_pct is the return over the whole fetched period, not a
30-day figure -- use worst_30d_return_pct / best_30d_return_pct to check
against CLAUDE.md's actual +5%/30d and -4%/30d thresholds.

Usage:
    python grid_search.py --symbol BTC-USD --interval 1h --period 730d
    python grid_search.py --source ccxt --exchange kraken --symbol BTC/USD --interval 1h --period 730d
    python grid_search.py --sort-by sharpe --top-n 20
"""
import argparse
import itertools
import time

import pandas as pd

from backtest import DEFAULT_SYMBOL, INTERVAL_BARS_PER_YEAR, compute_metrics, fetch_data, simulate

STOP_LOSS_PCT_GRID = [3.5, 4.0, 4.5, 5.0]
RSI_ENTRY_GRID = [25, 26, 27, 28]
RSI_EXIT_GRID = [29, 30, 31, 32]
SHORT_RSI_ENTRY_GRID = [70, 75, 78, 80]
SHORT_RSI_EXIT_GRID = [58, 60, 62, 65]
RSI_PERIOD_GRID = [10, 12, 14]

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
            STOP_LOSS_PCT_GRID, RSI_ENTRY_GRID, RSI_EXIT_GRID, SHORT_RSI_ENTRY_GRID, SHORT_RSI_EXIT_GRID, RSI_PERIOD_GRID
        )
        if combo[1] < combo[2] and combo[3] > combo[4]  # rsi_entry < rsi_exit, short_entry > short_exit
    ]
    print(f"{len(combos)} valid combinations (entry/exit bands non-overlapping).")

    start = time.time()
    results = []
    for i, (stop_loss_pct, rsi_entry, rsi_exit, short_rsi_entry, short_rsi_exit, rsi_period) in enumerate(combos):
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
