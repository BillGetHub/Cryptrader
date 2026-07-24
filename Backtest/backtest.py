"""Backtest harness for the RSI mean-reversion strategy defined in CLAUDE.md.

Entry: RSI(period) < entry threshold
Stop:  stop_loss_pct below entry
Size:  position_size_r percent of account balance risked per trade

CLAUDE.md defines an entry and a stop but no exit target. This harness closes
a position on whichever comes first: the stop being hit, or RSI recovering to
>= --rsi-exit (a mean-reversion exit, default 50). That default is an
assumption, not a spec requirement -- tune it like any other variable.

Data can come from either source:
    --source yfinance (default): Yahoo Finance via the yfinance package.
    --source ccxt: a crypto exchange's own public REST API via ccxt (free,
        no API key needed for OHLCV data). Defaults to Kraken, the venue
        LiveTradingBots/bot.py actually trades on, so backtest and live
        signals see the same prices.

Usage:
    python backtest.py --source yfinance --symbol BTC-USD --interval 1h --period 730d
    python backtest.py --source ccxt --exchange kraken --symbol BTC/USD --interval 1h --period 730d
"""
import argparse

import ccxt
import numpy as np
import pandas as pd
import yfinance as yf

INTERVAL_BARS_PER_YEAR = {
    "1m": 365 * 24 * 60,
    "5m": 365 * 24 * 12,
    "15m": 365 * 24 * 4,
    "30m": 365 * 24 * 2,
    "1h": 365 * 24,
    "1d": 365,
}

TIMEFRAME_MS = {
    "1m": 60_000,
    "5m": 5 * 60_000,
    "15m": 15 * 60_000,
    "30m": 30 * 60_000,
    "1h": 60 * 60_000,
    "1d": 24 * 60 * 60_000,
}

DEFAULT_SYMBOL = {"yfinance": "BTC-USD", "ccxt": "BTC/USD"}


def compute_rsi(closes: pd.Series, period: int) -> pd.Series:
    delta = closes.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def fetch_data_yfinance(symbol: str, interval: str, period: str) -> pd.DataFrame:
    df = yf.download(symbol, interval=interval, period=period, auto_adjust=True, progress=False)
    if df.empty:
        raise SystemExit(f"No data returned for {symbol} interval={interval} period={period}")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


def parse_period_to_days(period: str) -> int:
    if period.endswith("d"):
        return int(period[:-1])
    return int(period)


def fetch_data_ccxt(exchange_id: str, symbol: str, timeframe: str, period: str) -> pd.DataFrame:
    if timeframe not in TIMEFRAME_MS:
        raise SystemExit(f"--source ccxt does not support interval {timeframe!r}; choose one of {sorted(TIMEFRAME_MS)}")

    exchange = getattr(ccxt, exchange_id)({"enableRateLimit": True})
    timeframe_ms = TIMEFRAME_MS[timeframe]
    since = exchange.milliseconds() - parse_period_to_days(period) * 24 * 60 * 60 * 1000

    candles = []
    max_requests = 500  # safety cap so a misbehaving exchange/pair can't loop forever
    for _ in range(max_requests):
        batch = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=720)
        if not batch:
            break
        candles.extend(batch)
        next_since = batch[-1][0] + timeframe_ms
        if next_since <= since or next_since >= exchange.milliseconds():
            break
        since = next_since
        if len(batch) < 720:
            break

    if not candles:
        raise SystemExit(
            f"No data returned for {symbol} on {exchange_id} timeframe={timeframe} period={period}"
        )

    df = pd.DataFrame(candles, columns=["timestamp", "Open", "High", "Low", "Close", "Volume"])
    df = df.drop_duplicates(subset="timestamp").sort_values("timestamp")
    df.index = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    return df.drop(columns=["timestamp"])


def fetch_data(args: argparse.Namespace) -> pd.DataFrame:
    if args.source == "yfinance":
        return fetch_data_yfinance(args.symbol, args.interval, args.period)
    return fetch_data_ccxt(args.exchange, args.symbol, args.interval, args.period)


def simulate(
    df: pd.DataFrame,
    rsi_period: int,
    rsi_entry: float,
    rsi_exit: float,
    stop_loss_pct: float,
    position_size_r: float,
    initial_balance: float,
    enable_short: bool = False,
    short_rsi_entry: float = 75.0,
    short_rsi_exit: float = 65.0,
) -> dict:
    """Long entries fire on RSI < rsi_entry, exit on RSI >= rsi_exit (or stop below entry).
    Short entries (opt-in) fire on RSI > short_rsi_entry, exit on RSI <= short_rsi_exit
    (or stop above entry). Independent bands per side, one position open at a time.
    """
    rsi = compute_rsi(df["Close"], rsi_period)

    balance = initial_balance
    position = None  # dict: direction, entry_time, entry_price, stop_price, size, risk_amount
    equity_curve = []
    trades = []

    for i in range(len(df)):
        ts = df.index[i]
        high, low, close = df["High"].iloc[i], df["Low"].iloc[i], df["Close"].iloc[i]
        r = rsi.iloc[i]

        if position is not None:
            exit_price, reason = None, None
            if position["direction"] == "long":
                if low <= position["stop_price"]:
                    exit_price, reason = position["stop_price"], "stop"
                elif not np.isnan(r) and r >= rsi_exit:
                    exit_price, reason = close, "rsi_exit"
            else:
                if high >= position["stop_price"]:
                    exit_price, reason = position["stop_price"], "stop"
                elif not np.isnan(r) and r <= short_rsi_exit:
                    exit_price, reason = close, "rsi_exit"

            if exit_price is not None:
                if position["direction"] == "long":
                    pnl = position["size"] * (exit_price - position["entry_price"])
                else:
                    pnl = position["size"] * (position["entry_price"] - exit_price)
                balance += pnl
                trades.append(
                    {
                        "direction": position["direction"],
                        "entry_time": position["entry_time"],
                        "exit_time": ts,
                        "entry_price": position["entry_price"],
                        "exit_price": exit_price,
                        "size": position["size"],
                        "pnl": pnl,
                        "r_multiple": pnl / position["risk_amount"] if position["risk_amount"] else 0.0,
                        "reason": reason,
                    }
                )
                position = None

        if position is None and not np.isnan(r):
            direction = None
            if r < rsi_entry:
                direction = "long"
            elif enable_short and r > short_rsi_entry:
                direction = "short"

            if direction is not None:
                entry_price = close
                if direction == "long":
                    stop_price = entry_price * (1 - stop_loss_pct / 100)
                    stop_distance = entry_price - stop_price
                else:
                    stop_price = entry_price * (1 + stop_loss_pct / 100)
                    stop_distance = stop_price - entry_price
                risk_amount = balance * position_size_r / 100
                size = risk_amount / stop_distance if stop_distance > 0 else 0.0
                if size > 0:
                    position = {
                        "direction": direction,
                        "entry_time": ts,
                        "entry_price": entry_price,
                        "stop_price": stop_price,
                        "size": size,
                        "risk_amount": risk_amount,
                    }

        if position is not None:
            if position["direction"] == "long":
                open_pnl = position["size"] * (close - position["entry_price"])
            else:
                open_pnl = position["size"] * (position["entry_price"] - close)
        else:
            open_pnl = 0.0
        equity_curve.append({"time": ts, "equity": balance + open_pnl})

    equity_df = pd.DataFrame(equity_curve).set_index("time")
    trades_df = pd.DataFrame(trades)
    return {"equity": equity_df, "trades": trades_df, "final_balance": balance}


def compute_metrics(
    equity_df: pd.DataFrame, trades_df: pd.DataFrame, initial_balance: float, bars_per_year: float
) -> dict:
    equity = equity_df["equity"]
    total_return_pct = (equity.iloc[-1] / initial_balance - 1) * 100

    period_returns = equity.pct_change().dropna()
    sharpe = (
        (period_returns.mean() / period_returns.std()) * np.sqrt(bars_per_year)
        if period_returns.std() > 0
        else 0.0
    )

    running_max = equity.cummax()
    drawdown = (equity - running_max) / running_max
    max_drawdown_pct = drawdown.min() * 100

    daily_equity = equity.resample("1D").last().dropna()
    rolling_30d_return = daily_equity.pct_change(30).dropna() * 100

    num_trades = len(trades_df)
    win_rate_pct = (trades_df["pnl"] > 0).mean() * 100 if num_trades else 0.0

    long_trades_df = trades_df[trades_df["direction"] == "long"] if num_trades else trades_df
    short_trades_df = trades_df[trades_df["direction"] == "short"] if num_trades else trades_df
    num_long_trades = len(long_trades_df)
    num_short_trades = len(short_trades_df)
    long_win_rate_pct = (long_trades_df["pnl"] > 0).mean() * 100 if num_long_trades else float("nan")
    short_win_rate_pct = (short_trades_df["pnl"] > 0).mean() * 100 if num_short_trades else float("nan")

    return {
        "total_return_pct": total_return_pct,
        "sharpe": sharpe,
        "max_drawdown_pct": max_drawdown_pct,
        "num_trades": num_trades,
        "win_rate_pct": win_rate_pct,
        "num_long_trades": num_long_trades,
        "num_short_trades": num_short_trades,
        "long_win_rate_pct": long_win_rate_pct,
        "short_win_rate_pct": short_win_rate_pct,
        "worst_30d_return_pct": rolling_30d_return.min() if not rolling_30d_return.empty else float("nan"),
        "best_30d_return_pct": rolling_30d_return.max() if not rolling_30d_return.empty else float("nan"),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backtest the CLAUDE.md RSI mean-reversion strategy.")
    parser.add_argument(
        "--source",
        default="yfinance",
        choices=["yfinance", "ccxt"],
        help="Data source. 'yfinance' (default) hits Yahoo Finance. 'ccxt' hits a crypto "
        "exchange's own free public API (see --exchange) -- no key needed for OHLCV data, "
        "and it matches the venue bot.py actually trades on.",
    )
    parser.add_argument(
        "--exchange",
        default="kraken",
        help="ccxt exchange id, only used when --source ccxt (default: kraken, same as bot.py).",
    )
    parser.add_argument("--symbol", default=None, help="Defaults to BTC-USD for yfinance, BTC/USD for ccxt.")
    parser.add_argument("--interval", default="1h", choices=sorted(INTERVAL_BARS_PER_YEAR))
    parser.add_argument(
        "--period",
        default="730d",
        help="Lookback window as e.g. 730d, 60d (or 'max' for --source yfinance only). "
        "Yahoo caps intraday history: 1h ~730d, 1m ~7d. ccxt exchanges are not capped this way "
        "but a longer period means more paginated API requests.",
    )
    parser.add_argument("--rsi-period", type=int, default=14)
    parser.add_argument("--rsi-entry", type=float, default=25.0)
    parser.add_argument(
        "--rsi-exit",
        type=float,
        default=50.0,
        help="RSI level that closes an open position. Not in CLAUDE.md spec -- an assumption to tune.",
    )
    parser.add_argument("--stop-loss-pct", type=float, default=1.4)
    parser.add_argument("--position-size-r", type=float, default=0.5)
    parser.add_argument(
        "--enable-short",
        action="store_true",
        help="Backtest-only: also take short entries. NOTE: Kraken spot (what bot.py trades) "
        "has no native short selling -- this would need a margin/futures account with "
        "liquidation risk and funding costs not modeled here. Off by default.",
    )
    parser.add_argument(
        "--short-rsi-entry",
        type=float,
        default=75.0,
        help="Short entry when RSI rises above this (only used with --enable-short).",
    )
    parser.add_argument(
        "--short-rsi-exit",
        type=float,
        default=65.0,
        help="Cover the short when RSI falls back to this (only used with --enable-short).",
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
    result = simulate(
        df,
        args.rsi_period,
        args.rsi_entry,
        args.rsi_exit,
        args.stop_loss_pct,
        args.position_size_r,
        args.initial_balance,
        enable_short=args.enable_short,
        short_rsi_entry=args.short_rsi_entry,
        short_rsi_exit=args.short_rsi_exit,
    )
    metrics = compute_metrics(
        result["equity"], result["trades"], args.initial_balance, INTERVAL_BARS_PER_YEAR[args.interval]
    )

    source_label = args.source if args.source == "yfinance" else f"ccxt/{args.exchange}"
    print(f"Source:              {source_label}")
    print(f"Symbol:              {args.symbol}")
    print(f"Interval / Period:   {args.interval} / {args.period}")
    print(f"Bars:                {len(df)}")
    print(f"RSI long entry/exit: <{args.rsi_entry} / >={args.rsi_exit}")
    if args.enable_short:
        print(f"RSI short entry/exit: >{args.short_rsi_entry} / <={args.short_rsi_exit}")
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
