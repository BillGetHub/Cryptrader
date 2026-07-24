"""Backtest harness for the RSI mean-reversion strategy defined in CLAUDE.md.

Entry: RSI(period) < entry threshold
Stop:  stop_loss_pct below entry
Size:  position_size_r percent of account balance risked per trade

CLAUDE.md defines an entry and a stop but no exit target; --rsi-exit closes a
position on RSI recovering back up, or the stop being hit. Defaults below are
the confirmed baseline (CLAUDE.md, 2026-07-24): 74.0% win rate, +8.01% return,
Sharpe +1.38, max drawdown -1.84%, worst rolling 30d -1.27%, best rolling 30d
+2.40%, 131 trades on BTC-USD 1h/730d. --enable-short, --enable-range-filter,
and --enable-atr-stop reproduce the short leg, range filter, and volatility-
adjusted stop that baseline includes; without them you get a smaller subset
(note: with --enable-atr-stop, --stop-loss-pct is ignored -- the stop is
sized from ATR instead). Sharpe and drawdown clear CLAUDE.md's Success
thresholds by a wide margin, but 30d return (+2.40% best) is still short of
+5%/30d -- closer than any prior baseline (replacing the fixed stop with an
ATR-based one roughly 4.6x'd return on its own), but not there yet. See
CLAUDE.md for the full note, including why two alternative strategies (trend-
following, Bollinger Bands) and naive multi-asset diversification all
underperformed this baseline.

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


def compute_atr(df: pd.DataFrame, period: int) -> pd.Series:
    prev_close = df["Close"].shift(1)
    true_range = pd.concat(
        [df["High"] - df["Low"], (df["High"] - prev_close).abs(), (df["Low"] - prev_close).abs()], axis=1
    ).max(axis=1)
    return true_range.ewm(alpha=1 / period, min_periods=period).mean()


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
    enable_trend_filter: bool = False,
    trend_ma_period: int = 200,
    enable_range_filter: bool = False,
    range_ma_period: int = 200,
    range_max_distance_pct: float = 5.0,
    enable_atr_stop: bool = False,
    atr_period: int = 14,
    atr_multiplier: float = 2.0,
) -> dict:
    """Long entries fire on RSI < rsi_entry, exit on RSI >= rsi_exit (or stop below entry).
    Short entries (opt-in) fire on RSI > short_rsi_entry, exit on RSI <= short_rsi_exit
    (or stop above entry). Independent bands per side, one position open at a time.

    enable_trend_filter (opt-in) requires the trend to agree with the trade direction:
    longs only fire when close > trend_ma_period-bar SMA (uptrend), shorts only when
    close < that SMA (downtrend). Backtested and discarded (CLAUDE.md, 2026-07-24) --
    hurt Sharpe/return at both tested periods, likely because it's really a different
    strategy (buy-the-dip-in-an-uptrend) rather than a refinement of this one.

    enable_range_filter (opt-in) is a different hypothesis: RSI mean reversion tends to
    work best when price is ranging near its average and worst in strong trends either
    direction, so this only allows entries (long or short) when price is within
    range_max_distance_pct of the range_ma_period-bar SMA -- filtering out strong trends
    instead of trading with them.

    enable_atr_stop (opt-in) replaces the fixed stop_loss_pct stop with a volatility-
    adjusted one: stop_distance = atr_multiplier * ATR(atr_period) at entry, so the stop
    (and therefore position size) adapts to how volatile the market currently is instead
    of using the same fixed percentage regardless of conditions.

    Uses raw numpy arrays instead of DataFrame.iloc in the per-bar loop -- .iloc lookups
    dominate runtime when this is called hundreds of times in grid_search.py.
    """
    rsi_series = compute_rsi(df["Close"], rsi_period)
    highs = df["High"].to_numpy(dtype=np.float64)
    lows = df["Low"].to_numpy(dtype=np.float64)
    closes = df["Close"].to_numpy(dtype=np.float64)
    rsis = rsi_series.to_numpy(dtype=np.float64)
    n = len(closes)

    if enable_trend_filter:
        trend_ma = df["Close"].rolling(trend_ma_period).mean().to_numpy(dtype=np.float64)
    else:
        trend_ma = None

    if enable_range_filter:
        range_ma = df["Close"].rolling(range_ma_period).mean().to_numpy(dtype=np.float64)
    else:
        range_ma = None

    if enable_atr_stop:
        atr = compute_atr(df, atr_period).to_numpy(dtype=np.float64)
    else:
        atr = None

    balance = initial_balance
    equity = np.empty(n, dtype=np.float64)

    direction = None  # None, "long", "short"
    entry_price = stop_price = size = risk_amount = 0.0
    entry_idx = -1
    trades = []  # rows: direction, entry_idx, exit_idx, entry_price, exit_price, size, pnl, r_multiple, reason

    for i in range(n):
        high, low, close, r = highs[i], lows[i], closes[i], rsis[i]

        if direction is not None:
            exit_price, reason = None, None
            if direction == "long":
                if low <= stop_price:
                    exit_price, reason = stop_price, "stop"
                elif not np.isnan(r) and r >= rsi_exit:
                    exit_price, reason = close, "rsi_exit"
            else:
                if high >= stop_price:
                    exit_price, reason = stop_price, "stop"
                elif not np.isnan(r) and r <= short_rsi_exit:
                    exit_price, reason = close, "rsi_exit"

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

        if direction is None and not np.isnan(r):
            trend_ok_long, trend_ok_short = True, True
            if enable_trend_filter:
                ma = trend_ma[i]
                trend_ok_long = not np.isnan(ma) and close > ma
                trend_ok_short = not np.isnan(ma) and close < ma

            range_ok = True
            if enable_range_filter:
                ma = range_ma[i]
                range_ok = not np.isnan(ma) and abs(close - ma) / ma * 100 <= range_max_distance_pct

            atr_ok = True
            if enable_atr_stop:
                atr_ok = not np.isnan(atr[i])

            new_direction = None
            if r < rsi_entry and trend_ok_long and range_ok and atr_ok:
                new_direction = "long"
            elif enable_short and r > short_rsi_entry and trend_ok_short and range_ok and atr_ok:
                new_direction = "short"

            if new_direction is not None:
                candidate_entry_price = close
                if enable_atr_stop:
                    stop_offset = atr_multiplier * atr[i]
                else:
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
            trades, columns=["direction", "entry_idx", "exit_idx", "entry_price", "exit_price", "size", "pnl", "r_multiple", "reason"]
        )
        raw["entry_time"] = df.index[raw["entry_idx"]]
        raw["exit_time"] = df.index[raw["exit_idx"]]
        trades_df = raw[columns]
    else:
        trades_df = pd.DataFrame(columns=columns)

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
    parser.add_argument("--rsi-entry", type=float, default=28.0)
    parser.add_argument(
        "--rsi-exit",
        type=float,
        default=29.0,
        help="RSI level that closes an open position. Not in CLAUDE.md spec -- an assumption to tune.",
    )
    parser.add_argument("--stop-loss-pct", type=float, default=5.0)
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
        default=78.0,
        help="Short entry when RSI rises above this (only used with --enable-short).",
    )
    parser.add_argument(
        "--short-rsi-exit",
        type=float,
        default=65.0,
        help="Cover the short when RSI falls back to this (only used with --enable-short).",
    )
    parser.add_argument(
        "--enable-trend-filter",
        action="store_true",
        help="Only take longs when price is above the --trend-ma-period SMA (uptrend), and "
        "shorts only below it (downtrend). Off by default -- every RSI band in this project's "
        "history so far has traded RSI extremes with no sense of the broader trend.",
    )
    parser.add_argument(
        "--trend-ma-period",
        type=int,
        default=200,
        help="SMA period (in bars) for --enable-trend-filter.",
    )
    parser.add_argument(
        "--enable-range-filter",
        action="store_true",
        help="Only take entries (long or short) when price is within --range-max-distance-pct "
        "of the --range-ma-period SMA -- filters out strong trends instead of trading with "
        "them, unlike --enable-trend-filter. Off by default.",
    )
    parser.add_argument(
        "--range-ma-period",
        type=int,
        default=200,
        help="SMA period (in bars) for --enable-range-filter.",
    )
    parser.add_argument(
        "--range-max-distance-pct",
        type=float,
        default=3.0,
        help="Max %% distance from the range SMA allowed for an entry (only with --enable-range-filter).",
    )
    parser.add_argument(
        "--enable-atr-stop",
        action="store_true",
        help="Replace the fixed --stop-loss-pct stop with a volatility-adjusted one: "
        "stop distance = --atr-multiplier * ATR(--atr-period) at entry. Off by default.",
    )
    parser.add_argument("--atr-period", type=int, default=21, help="ATR period in bars (only with --enable-atr-stop).")
    parser.add_argument(
        "--atr-multiplier",
        type=float,
        default=2.0,
        help="Stop distance as a multiple of ATR (only with --enable-atr-stop).",
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
        enable_trend_filter=args.enable_trend_filter,
        trend_ma_period=args.trend_ma_period,
        enable_range_filter=args.enable_range_filter,
        range_ma_period=args.range_ma_period,
        range_max_distance_pct=args.range_max_distance_pct,
        enable_atr_stop=args.enable_atr_stop,
        atr_period=args.atr_period,
        atr_multiplier=args.atr_multiplier,
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
    if args.enable_atr_stop:
        print(f"Stop / Size:         ATR({args.atr_period})x{args.atr_multiplier} / {args.position_size_r}R")
    else:
        print(f"Stop / Size:         {args.stop_loss_pct}% / {args.position_size_r}R")
    if args.enable_trend_filter:
        print(f"Trend filter:        on, {args.trend_ma_period}-bar SMA")
    if args.enable_range_filter:
        print(f"Range filter:        on, within {args.range_max_distance_pct}% of {args.range_ma_period}-bar SMA")
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
