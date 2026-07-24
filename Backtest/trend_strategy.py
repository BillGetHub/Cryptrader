"""Trend-following backtest: classic fast/slow moving-average crossover.

This is a genuinely different strategy from the RSI mean-reversion one in
backtest.py, not a variant of it. RSI mean reversion (with the range filter)
specifically trades only when price is ranging near its average, avoiding
strong trends. This strategy does the opposite: it's long while price is
trending up (fast SMA > slow SMA) and short (opt-in) while trending down --
i.e. it trades exactly the conditions the RSI strategy's range filter
excludes. The two could plausibly complement each other rather than compete.

Rule:
    Long while fast_ma > slow_ma. Short (opt-in) while fast_ma < slow_ma.
    Exit on trend flip (fast/slow cross back) or the stop being hit,
    whichever comes first. Always in the market one way or another once the
    MAs are warmed up (or flat, if shorts are disabled and the trend is down).

Usage:
    python trend_strategy.py --symbol BTCUSDT --interval 1h --period 730d
    python trend_strategy.py --fast-ma-period 20 --slow-ma-period 50 --enable-short
"""
import argparse

import numpy as np
import pandas as pd

from backtest import DEFAULT_SYMBOL, INTERVAL_BARS_PER_YEAR, compute_metrics, fetch_data


def simulate_trend(
    df: pd.DataFrame,
    fast_ma_period: int,
    slow_ma_period: int,
    stop_loss_pct: float,
    position_size_r: float,
    initial_balance: float,
    enable_short: bool = False,
) -> dict:
    fast_ma = df["Close"].rolling(fast_ma_period).mean().to_numpy(dtype=np.float64)
    slow_ma = df["Close"].rolling(slow_ma_period).mean().to_numpy(dtype=np.float64)
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
        fma, sma = fast_ma[i], slow_ma[i]
        ma_ready = not np.isnan(fma) and not np.isnan(sma)

        if direction is not None:
            exit_price, reason = None, None
            if direction == "long":
                if low <= stop_price:
                    exit_price, reason = stop_price, "stop"
                elif ma_ready and fma <= sma:
                    exit_price, reason = close, "trend_flip"
            else:
                if high >= stop_price:
                    exit_price, reason = stop_price, "stop"
                elif ma_ready and fma >= sma:
                    exit_price, reason = close, "trend_flip"

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

        if direction is None and ma_ready:
            new_direction = None
            if fma > sma:
                new_direction = "long"
            elif enable_short and fma < sma:
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
    parser = argparse.ArgumentParser(description="Backtest a fast/slow moving-average crossover trend-following strategy.")
    parser.add_argument("--source", default="yfinance", choices=["yfinance", "ccxt"])
    parser.add_argument("--exchange", default="kraken")
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--interval", default="1h", choices=sorted(INTERVAL_BARS_PER_YEAR))
    parser.add_argument("--period", default="730d")
    parser.add_argument("--fast-ma-period", type=int, default=20, help="Fast SMA period in bars.")
    parser.add_argument("--slow-ma-period", type=int, default=50, help="Slow SMA period in bars.")
    parser.add_argument("--stop-loss-pct", type=float, default=5.0)
    parser.add_argument("--position-size-r", type=float, default=0.5)
    parser.add_argument(
        "--enable-short",
        action="store_true",
        help="Backtest-only: also take short entries when trending down. Kraken spot has no "
        "native short selling. Off by default.",
    )
    parser.add_argument("--initial-balance", type=float, default=10000.0)
    parser.add_argument("--csv-out", default=None, help="optional path to write the equity curve as CSV")
    args = parser.parse_args()
    if args.symbol is None:
        args.symbol = DEFAULT_SYMBOL[args.source]
    return args


def main() -> None:
    args = parse_args()

    df = fetch_data(args)
    result = simulate_trend(
        df,
        args.fast_ma_period,
        args.slow_ma_period,
        args.stop_loss_pct,
        args.position_size_r,
        args.initial_balance,
        enable_short=args.enable_short,
    )
    metrics = compute_metrics(
        result["equity"], result["trades"], args.initial_balance, INTERVAL_BARS_PER_YEAR[args.interval]
    )

    source_label = args.source if args.source == "yfinance" else f"ccxt/{args.exchange}"
    print(f"Source:              {source_label}")
    print(f"Symbol:              {args.symbol}")
    print(f"Interval / Period:   {args.interval} / {args.period}")
    print(f"Bars:                {len(df)}")
    print(f"Fast/Slow SMA:       {args.fast_ma_period} / {args.slow_ma_period}")
    print(f"Short entries:       {'on' if args.enable_short else 'off'}")
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
