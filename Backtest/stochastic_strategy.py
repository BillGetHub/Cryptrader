"""Stochastic oscillator mean-reversion backtest -- same underlying idea as
the RSI strategy in backtest.py (enter oversold, exit on recovery, opt-in
short the overbought side), but a genuinely different formula: RSI measures
average gain vs. average loss over a lookback; the stochastic oscillator
measures where the current close sits within its recent high/low range.
Different math family, same "buy the dip, sell the rip" shape -- worth
comparing directly against RSI's results on the same data.

    %K = 100 * (close - lowest_low_N) / (highest_high_N - lowest_low_N)
    %D = SMA(%K, d_period)   -- smoothed; %D is what's traded, not raw %K

    Long entry:  %D < entry_threshold.  Long exit:  %D >= exit_threshold, or stop hit.
    Short entry (opt-in): %D > short_entry_threshold.  Short exit: %D <= short_exit_threshold, or stop.

Usage:
    python stochastic_strategy.py --symbol SOLUSDT --source ccxt --exchange binance
    python stochastic_strategy.py --stoch-period 14 --stoch-smooth 3 --enable-short
"""
import argparse

import numpy as np
import pandas as pd

from backtest import DEFAULT_SYMBOL, INTERVAL_BARS_PER_YEAR, compute_metrics, fetch_data


def compute_stochastic(df: pd.DataFrame, period: int, smooth: int) -> pd.Series:
    lowest_low = df["Low"].rolling(period).min()
    highest_high = df["High"].rolling(period).max()
    percent_k = 100 * (df["Close"] - lowest_low) / (highest_high - lowest_low)
    return percent_k.rolling(smooth).mean()


def simulate_stochastic(
    df: pd.DataFrame,
    stoch_period: int,
    stoch_smooth: int,
    entry_threshold: float,
    exit_threshold: float,
    stop_loss_pct: float,
    position_size_r: float,
    initial_balance: float,
    enable_short: bool = False,
    short_entry_threshold: float = 80.0,
    short_exit_threshold: float = 50.0,
) -> dict:
    percent_d = compute_stochastic(df, stoch_period, stoch_smooth).to_numpy(dtype=np.float64)
    highs = df["High"].to_numpy(dtype=np.float64)
    lows = df["Low"].to_numpy(dtype=np.float64)
    closes = df["Close"].to_numpy(dtype=np.float64)
    n = len(closes)

    balance = initial_balance
    equity = np.empty(n, dtype=np.float64)

    direction = None  # None, "long", "short"
    entry_price = stop_price = size = risk_amount = 0.0
    entry_idx = -1
    trades = []

    for i in range(n):
        high, low, close = highs[i], lows[i], closes[i]
        d_val = percent_d[i]
        stoch_ready = not np.isnan(d_val)

        if direction is not None:
            exit_price, reason = None, None
            if direction == "long":
                if low <= stop_price:
                    exit_price, reason = stop_price, "stop"
                elif stoch_ready and d_val >= exit_threshold:
                    exit_price, reason = close, "reversion_exit"
            else:
                if high >= stop_price:
                    exit_price, reason = stop_price, "stop"
                elif stoch_ready and d_val <= short_exit_threshold:
                    exit_price, reason = close, "reversion_exit"

            if exit_price is not None:
                pnl = size * (exit_price - entry_price) if direction == "long" else size * (entry_price - exit_price)
                balance += pnl
                trades.append(
                    (
                        direction,
                        entry_idx,
                        i,
                        entry_price,
                        exit_price,
                        size,
                        pnl,
                        pnl / risk_amount if risk_amount else 0.0,
                        reason,
                    )
                )
                direction = None

        if direction is None and stoch_ready:
            new_direction = None
            if d_val < entry_threshold:
                new_direction = "long"
            elif enable_short and d_val > short_entry_threshold:
                new_direction = "short"

            if new_direction is not None:
                candidate_entry_price = close
                stop_offset = candidate_entry_price * stop_loss_pct / 100
                if new_direction == "long":
                    candidate_stop_price = candidate_entry_price - stop_offset
                    stop_distance = candidate_entry_price - candidate_stop_price
                else:
                    candidate_stop_price = candidate_entry_price + stop_offset
                    stop_distance = candidate_stop_price - candidate_entry_price
                candidate_risk_amount = balance * position_size_r / 100
                candidate_size = candidate_risk_amount / stop_distance if stop_distance > 0 else 0.0
                if candidate_size > 0:
                    direction = new_direction
                    entry_price = candidate_entry_price
                    stop_price = candidate_stop_price
                    size = candidate_size
                    risk_amount = candidate_risk_amount
                    entry_idx = i

        if direction is not None:
            open_pnl = size * (close - entry_price) if direction == "long" else size * (entry_price - close)
        else:
            open_pnl = 0.0
        equity[i] = balance + open_pnl

    equity_df = pd.DataFrame({"equity": equity}, index=df.index)

    columns = ["direction", "entry_time", "exit_time", "entry_price", "exit_price", "size", "pnl", "r_multiple", "reason"]
    if trades:
        raw = pd.DataFrame(
            trades,
            columns=["direction", "entry_idx", "exit_idx", "entry_price", "exit_price", "size", "pnl", "r_multiple", "reason"],
        )
        raw["entry_time"] = df.index[raw["entry_idx"]]
        raw["exit_time"] = df.index[raw["exit_idx"]]
        trades_df = raw[columns]
    else:
        trades_df = pd.DataFrame(columns=columns)

    return {"equity": equity_df, "trades": trades_df, "final_balance": balance}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backtest a stochastic oscillator mean-reversion strategy.")
    parser.add_argument("--source", default="yfinance", choices=["yfinance", "ccxt"])
    parser.add_argument("--exchange", default="kraken")
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--interval", default="1h", choices=sorted(INTERVAL_BARS_PER_YEAR))
    parser.add_argument("--period", default="730d")
    parser.add_argument("--stoch-period", type=int, default=14, help="Lookback for %%K's high/low range.")
    parser.add_argument("--stoch-smooth", type=int, default=3, help="SMA period smoothing %%K into %%D.")
    parser.add_argument("--stoch-entry", type=float, default=20.0, help="Long entry: %%D below this.")
    parser.add_argument("--stoch-exit", type=float, default=50.0, help="Long exit: %%D at/above this.")
    parser.add_argument("--stop-loss-pct", type=float, default=5.0)
    parser.add_argument("--position-size-r", type=float, default=0.5)
    parser.add_argument(
        "--enable-short",
        action="store_true",
        help="Backtest-only: also take short entries on an overbought %%D. Kraken spot has no "
        "native short selling. Off by default.",
    )
    parser.add_argument("--short-stoch-entry", type=float, default=80.0, help="Short entry: %%D above this.")
    parser.add_argument("--short-stoch-exit", type=float, default=50.0, help="Short exit: %%D at/below this.")
    parser.add_argument("--initial-balance", type=float, default=10000.0)
    parser.add_argument("--csv-out", default=None, help="optional path to write the equity curve as CSV")
    args = parser.parse_args()
    if args.symbol is None:
        args.symbol = DEFAULT_SYMBOL[args.source]
    return args


def main() -> None:
    args = parse_args()

    df = fetch_data(args)
    result = simulate_stochastic(
        df,
        args.stoch_period,
        args.stoch_smooth,
        args.stoch_entry,
        args.stoch_exit,
        args.stop_loss_pct,
        args.position_size_r,
        args.initial_balance,
        enable_short=args.enable_short,
        short_entry_threshold=args.short_stoch_entry,
        short_exit_threshold=args.short_stoch_exit,
    )
    metrics = compute_metrics(
        result["equity"], result["trades"], args.initial_balance, INTERVAL_BARS_PER_YEAR[args.interval]
    )

    source_label = args.source if args.source == "yfinance" else f"ccxt/{args.exchange}"
    print(f"Source:              {source_label}")
    print(f"Symbol:              {args.symbol}")
    print(f"Interval / Period:   {args.interval} / {args.period}")
    print(f"Bars:                {len(df)}")
    print(f"Stoch period/smooth: {args.stoch_period} / {args.stoch_smooth}")
    print(f"Long entry/exit:     <{args.stoch_entry} / >={args.stoch_exit}")
    print(f"Short entries:       {'on' if args.enable_short else 'off'}")
    if args.enable_short:
        print(f"Short entry/exit:    >{args.short_stoch_entry} / <={args.short_stoch_exit}")
    print(f"Stop / Size:         {args.stop_loss_pct}% / {args.position_size_r}R")
    print()
    if args.enable_short:
        print(f"Trades:              {metrics['num_trades']} (long {metrics['num_long_trades']}, short {metrics['num_short_trades']})")
        print(
            f"Win rate:            {metrics['win_rate_pct']:.1f}% "
            f"(long {metrics['long_win_rate_pct']:.1f}%, short {metrics['short_win_rate_pct']:.1f}%)"
        )
    else:
        print(f"Trades:              {metrics['num_trades']}")
        print(f"Win rate:            {metrics['win_rate_pct']:.1f}%")
    print(f"Total return:        {metrics['total_return_pct']:.2f}%")
    print(f"Sharpe (annualized): {metrics['sharpe']:.2f}")
    print(f"Max drawdown:        {metrics['max_drawdown_pct']:.2f}%")
    print(f"Worst rolling 30d:   {metrics['worst_30d_return_pct']:.2f}%")
    print(f"Best rolling 30d:    {metrics['best_30d_return_pct']:.2f}%")
    print()
    print("CLAUDE.md thresholds:")
    print("  Success: return >= +5%/30d, sharpe >= 1.2, drawdown <= 8%")
    print("  Failure: drawdown > 8%, return < -4%/30d, sharpe < 0")

    if args.csv_out:
        result["equity"].to_csv(args.csv_out)
        print(f"\nEquity curve written to {args.csv_out}")


if __name__ == "__main__":
    main()
