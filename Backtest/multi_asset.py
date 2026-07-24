"""Multi-asset portfolio backtest: runs the confirmed RSI+range-filter strategy
(from backtest.py) independently across several pairs and combines them into a
single portfolio equity curve.

This tests a different hypothesis than a new signal: diversification is one of
the few genuine "free lunches" in finance -- running the same edge across
several less-than-perfectly-correlated assets can raise portfolio-level Sharpe
without raising the risk of any single position, which in turn could support
somewhat higher position sizing more safely than leveraging one asset alone.

Capital is split evenly across the symbols given. Each asset's hourly equity
curve is resampled to daily and summed to build the portfolio curve (daily,
not hourly, since different pairs' fetched bars don't line up exactly bar for
bar) -- so Sharpe here is calculated on daily returns, not hourly like
backtest.py's default.

Two parameter modes:
  - Default: one shared set of RSI/stop/range-filter flags (same as
    backtest.py's) applied to every symbol. This is what an earlier session
    used to test naive diversification with BTC's tuned parameters reused
    unchanged on ETH/SOL -- it failed (combined Sharpe -0.51, see
    VALIDATED_PARAMETERS.md), because a coin's tuned parameters don't
    transfer to another coin.
  - --per-symbol-baselines: each symbol uses its own confirmed baseline from
    CONFIRMED_BASELINES below (BTC, ETH, BNB as of 2026-07-24) instead of the
    shared flags. This is the correct way to test diversification benefit,
    since it doesn't conflate "wrong parameters for this coin" with "genuine
    diversification effect."

Usage:
    python multi_asset.py --interval 1h --period 730d
    python multi_asset.py --source ccxt --exchange kraken --symbols "BTCUSDT,ETHUSDT,SOLUSDT"
    python multi_asset.py --source ccxt --exchange binance --symbols "BTCUSDT,ETHUSDT,BNBUSDT" --per-symbol-baselines
"""
import argparse

import pandas as pd

from backtest import (
    DEFAULT_SYMBOL,
    INTERVAL_BARS_PER_YEAR,
    compute_metrics,
    fetch_data_ccxt,
    fetch_data_yfinance,
    simulate,
)

DEFAULT_SYMBOLS = {
    "yfinance": "BTCUSDT,ETHUSDT,SOLUSDT",
    "ccxt": "BTCUSDT,ETHUSDT,SOLUSDT",
}

# Each coin's own confirmed baseline (CLAUDE.md / VALIDATED_PARAMETERS.md,
# 2026-07-24), for --per-symbol-baselines. Keyed on the bare pair form used
# throughout this project (normalize_symbol handles per-source formatting).
CONFIRMED_BASELINES = {
    "BTCUSDT": dict(
        rsi_period=14,
        rsi_entry=28.0,
        rsi_exit=29.0,
        stop_loss_pct=5.5,
        enable_short=True,
        short_rsi_entry=76.0,
        short_rsi_exit=50.0,
        enable_range_filter=True,
        range_ma_period=200,
        range_max_distance_pct=2.0,
        enable_atr_stop=True,
        atr_period=10,
        atr_multiplier=2.0,
    ),
    "ETHUSDT": dict(
        rsi_period=12,
        rsi_entry=28.0,
        rsi_exit=29.0,
        stop_loss_pct=4.5,
        enable_short=True,
        short_rsi_entry=76.0,
        short_rsi_exit=45.0,
        enable_range_filter=True,
        range_ma_period=200,
        range_max_distance_pct=2.5,
        enable_atr_stop=False,
    ),
    "BNBUSDT": dict(
        rsi_period=12,
        rsi_entry=27.0,
        rsi_exit=29.0,
        stop_loss_pct=5.0,
        enable_short=True,
        short_rsi_entry=78.0,
        short_rsi_exit=45.0,
        enable_range_filter=True,
        range_ma_period=200,
        range_max_distance_pct=4.0,
        enable_atr_stop=False,
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Multi-asset portfolio backtest of the RSI+range-filter strategy.")
    parser.add_argument("--source", default="yfinance", choices=["yfinance", "ccxt"])
    parser.add_argument("--exchange", default="kraken")
    parser.add_argument(
        "--symbols",
        default=None,
        help="Comma-separated symbols (bare pairs like BTCUSDT are auto-normalized per source). "
        "Defaults to BTC/ETH/SOL.",
    )
    parser.add_argument("--interval", default="1h", choices=sorted(INTERVAL_BARS_PER_YEAR))
    parser.add_argument("--period", default="730d")
    parser.add_argument("--rsi-period", type=int, default=14)
    parser.add_argument("--rsi-entry", type=float, default=28.0)
    parser.add_argument("--rsi-exit", type=float, default=29.0)
    parser.add_argument("--stop-loss-pct", type=float, default=5.0)
    parser.add_argument("--position-size-r", type=float, default=0.5)
    parser.add_argument("--enable-short", action="store_true")
    parser.add_argument("--short-rsi-entry", type=float, default=78.0)
    parser.add_argument("--short-rsi-exit", type=float, default=65.0)
    parser.add_argument("--enable-range-filter", action="store_true")
    parser.add_argument("--range-ma-period", type=int, default=200)
    parser.add_argument("--range-max-distance-pct", type=float, default=3.0)
    parser.add_argument("--enable-atr-stop", action="store_true", help="Ignored per-symbol if --per-symbol-baselines is set.")
    parser.add_argument("--atr-period", type=int, default=21)
    parser.add_argument("--atr-multiplier", type=float, default=2.0)
    parser.add_argument(
        "--per-symbol-baselines",
        action="store_true",
        help="Use each symbol's own confirmed baseline (CONFIRMED_BASELINES) instead of "
        "the shared flags above. Only defined for BTCUSDT/ETHUSDT/BNBUSDT; any other "
        "symbol falls back to the shared flags with a warning.",
    )
    parser.add_argument("--initial-balance", type=float, default=10000.0, help="Total capital, split evenly across symbols.")
    parser.add_argument("--csv-out", default=None, help="optional path to write the portfolio equity curve as CSV")
    args = parser.parse_args()
    if args.symbols is None:
        args.symbols = DEFAULT_SYMBOLS[args.source]
    args.symbol_list = [s.strip() for s in args.symbols.split(",") if s.strip()]
    return args


def fetch_one(args: argparse.Namespace, symbol: str) -> pd.DataFrame:
    if args.source == "yfinance":
        return fetch_data_yfinance(symbol, args.interval, args.period)
    return fetch_data_ccxt(args.exchange, symbol, args.interval, args.period)


def main() -> None:
    args = parse_args()
    n_symbols = len(args.symbol_list)
    per_asset_balance = args.initial_balance / n_symbols

    daily_equities = {}
    all_trades = []
    per_asset_summary = []

    for symbol in args.symbol_list:
        print(f"Fetching {symbol} {args.interval} data ({args.source})...")
        df = fetch_one(args, symbol)

        if args.per_symbol_baselines:
            baseline = CONFIRMED_BASELINES.get(symbol.upper())
            if baseline is None:
                print(f"  No confirmed baseline for {symbol}, falling back to shared CLI flags.")
                params = dict(
                    rsi_period=args.rsi_period,
                    rsi_entry=args.rsi_entry,
                    rsi_exit=args.rsi_exit,
                    stop_loss_pct=args.stop_loss_pct,
                    enable_short=args.enable_short,
                    short_rsi_entry=args.short_rsi_entry,
                    short_rsi_exit=args.short_rsi_exit,
                    enable_range_filter=args.enable_range_filter,
                    range_ma_period=args.range_ma_period,
                    range_max_distance_pct=args.range_max_distance_pct,
                    enable_atr_stop=args.enable_atr_stop,
                    atr_period=args.atr_period,
                    atr_multiplier=args.atr_multiplier,
                )
            else:
                print(f"  Using {symbol}'s own confirmed baseline.")
                params = dict(baseline)
        else:
            params = dict(
                rsi_period=args.rsi_period,
                rsi_entry=args.rsi_entry,
                rsi_exit=args.rsi_exit,
                stop_loss_pct=args.stop_loss_pct,
                enable_short=args.enable_short,
                short_rsi_entry=args.short_rsi_entry,
                short_rsi_exit=args.short_rsi_exit,
                enable_range_filter=args.enable_range_filter,
                range_ma_period=args.range_ma_period,
                range_max_distance_pct=args.range_max_distance_pct,
                enable_atr_stop=args.enable_atr_stop,
                atr_period=args.atr_period,
                atr_multiplier=args.atr_multiplier,
            )

        rsi_period = params.pop("rsi_period")
        rsi_entry = params.pop("rsi_entry")
        rsi_exit = params.pop("rsi_exit")
        stop_loss_pct = params.pop("stop_loss_pct")
        result = simulate(
            df,
            rsi_period,
            rsi_entry,
            rsi_exit,
            stop_loss_pct,
            args.position_size_r,
            per_asset_balance,
            **params,
        )
        metrics = compute_metrics(result["equity"], result["trades"], per_asset_balance, INTERVAL_BARS_PER_YEAR[args.interval])
        per_asset_summary.append(
            {
                "symbol": symbol,
                "bars": len(df),
                "trades": metrics["num_trades"],
                "win_rate_pct": metrics["win_rate_pct"],
                "total_return_pct": metrics["total_return_pct"],
                "sharpe": metrics["sharpe"],
                "max_drawdown_pct": metrics["max_drawdown_pct"],
            }
        )

        daily = result["equity"]["equity"].resample("1D").last().ffill()
        daily_equities[symbol] = daily

        trades = result["trades"].copy()
        trades["symbol"] = symbol
        all_trades.append(trades)

    print("\nPer-asset results:")
    per_asset_df = pd.DataFrame(per_asset_summary)
    with pd.option_context("display.max_columns", None, "display.width", 160):
        print(per_asset_df.to_string(index=False))

    portfolio_equity = pd.concat(daily_equities.values(), axis=1).sum(axis=1).to_frame("equity").dropna()
    combined_trades = pd.concat(all_trades, ignore_index=True) if all_trades else pd.DataFrame()

    portfolio_metrics = compute_metrics(portfolio_equity, combined_trades, args.initial_balance, INTERVAL_BARS_PER_YEAR["1d"])

    print(f"\nPortfolio ({n_symbols} symbols, capital split evenly, daily-resampled):")
    print(f"Total trades:        {portfolio_metrics['num_trades']}")
    print(f"Combined win rate:   {portfolio_metrics['win_rate_pct']:.1f}%")
    print(f"Total return:        {portfolio_metrics['total_return_pct']:.2f}%")
    print(f"Sharpe (annualized, daily): {portfolio_metrics['sharpe']:.2f}")
    print(f"Max drawdown:        {portfolio_metrics['max_drawdown_pct']:.2f}%")
    print(f"Worst rolling 30d:   {portfolio_metrics['worst_30d_return_pct']:.2f}%")
    print(f"Best rolling 30d:    {portfolio_metrics['best_30d_return_pct']:.2f}%")
    print()
    print("CLAUDE.md thresholds:")
    print("  Success: return >= +5%/30d, sharpe >= 1.2, drawdown <= 8%")
    print("  Failure: drawdown > 8%, return < -4%/30d, sharpe < 0")

    if args.csv_out:
        portfolio_equity.to_csv(args.csv_out)
        print(f"\nPortfolio equity curve written to {args.csv_out}")


if __name__ == "__main__":
    main()
