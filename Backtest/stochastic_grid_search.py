"""Joint grid search over the stochastic oscillator strategy's parameters,
built on stochastic_strategy.py. Same process as grid_search.py (RSI), but
long-only throughout -- this exists specifically to see whether tuning
closes SOL's gap to Success the way it did for RSI on BTC/ETH/BNB, since
SOL's long-only RSI/trend/Bollinger/MACD/Donchian results (all at default
or lightly-tuned parameters) all fell well short. Not wired for --enable-short:
if a future coin's short side is worth tuning here, add it then rather than
now, since SOL's whole point in reaching this file is finding a genuine
long-only edge.

Usage:
    python stochastic_grid_search.py --symbol SOLUSDT --source ccxt --exchange binance
    python stochastic_grid_search.py --sort-by sharpe --top-n 20
"""
import argparse
import itertools
import time

import pandas as pd

from backtest import DEFAULT_SYMBOL, INTERVAL_BARS_PER_YEAR, compute_metrics, fetch_data
from stochastic_strategy import simulate_stochastic

STOCH_PERIOD_GRID = [10, 14, 21]
STOCH_SMOOTH_GRID = [3, 5]
STOCH_ENTRY_GRID = [10, 15, 20, 25]
STOCH_EXIT_GRID = [40, 50, 60, 80]
STOP_LOSS_PCT_GRID = [3.0, 5.0, 7.0]

SORT_KEYS = {
    "win_rate": ["win_rate_pct", "sharpe"],
    "sharpe": ["sharpe", "win_rate_pct"],
    "return": ["best_30d_return_pct", "sharpe"],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Joint grid search for the stochastic oscillator strategy's parameters.")
    parser.add_argument("--source", default="yfinance", choices=["yfinance", "ccxt"])
    parser.add_argument("--exchange", default="kraken")
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--interval", default="1h", choices=sorted(INTERVAL_BARS_PER_YEAR))
    parser.add_argument("--period", default="730d")
    parser.add_argument("--position-size-r", type=float, default=0.5)
    parser.add_argument("--initial-balance", type=float, default=10000.0)
    parser.add_argument("--sort-by", default="sharpe", choices=sorted(SORT_KEYS))
    parser.add_argument("--top-n", type=int, default=15)
    parser.add_argument("--csv-out", default=None)
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
            STOCH_PERIOD_GRID, STOCH_SMOOTH_GRID, STOCH_ENTRY_GRID, STOCH_EXIT_GRID, STOP_LOSS_PCT_GRID
        )
        if combo[2] < combo[3]  # entry < exit
    ]
    print(f"{len(combos)} valid combinations.")

    start = time.time()
    results = []
    for i, (stoch_period, stoch_smooth, entry_threshold, exit_threshold, stop_loss_pct) in enumerate(combos):
        result = simulate_stochastic(
            df,
            stoch_period,
            stoch_smooth,
            entry_threshold,
            exit_threshold,
            stop_loss_pct,
            args.position_size_r,
            args.initial_balance,
            enable_short=False,
        )
        metrics = compute_metrics(
            result["equity"], result["trades"], args.initial_balance, INTERVAL_BARS_PER_YEAR[args.interval]
        )
        results.append(
            {
                "stoch_period": stoch_period,
                "stoch_smooth": stoch_smooth,
                "entry_threshold": entry_threshold,
                "exit_threshold": exit_threshold,
                "stop_loss_pct": stop_loss_pct,
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
