"""Shared backtest engine: simulates a strategy's entry/stop/size rules over
historical OHLCV data and reports metrics against CLAUDE.md's Success/Failure bar.

Assumptions (not specified by CLAUDE.md, adjust as needed):
- One open position at a time (a new entry signal is ignored while in a trade).
- Entry fills at the signal bar's close; stop-loss fills at the stop price if
  the bar's low touches it; the strategy's own exit signal fills at that bar's close.
- Risk-free rate is assumed 0% for the Sharpe calculation.
"""
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

PERIODS_PER_YEAR = {
    "1m": 60 * 24 * 365,
    "5m": 12 * 24 * 365,
    "15m": 4 * 24 * 365,
    "1h": 24 * 365,
    "4h": 6 * 365,
    "1d": 365,
}


def load_strategy(strategy_dir: Path):
    config = yaml.safe_load((strategy_dir / "config.yaml").read_text())
    spec = importlib.util.spec_from_file_location(f"strategy_{strategy_dir.name}", strategy_dir / "strategy.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, config


def load_ohlcv(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    df.columns = [c.strip().lower() for c in df.columns]
    required = {"timestamp", "open", "high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"CSV missing required columns: {sorted(missing)}")
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df.sort_values("timestamp").reset_index(drop=True)


def simulate(df: pd.DataFrame, entries: pd.Series, exits: pd.Series, risk: dict, initial_balance: float) -> dict:
    stop_loss_pct = risk["stop_loss_pct"]
    size_r_pct = risk["size_r_pct"]

    balance = initial_balance
    equity_curve = np.empty(len(df))
    trades = []

    in_position = False
    entry_price = stop_price = size = 0.0

    for i in range(len(df)):
        if in_position:
            if df["low"].iloc[i] <= stop_price:
                pnl = (stop_price - entry_price) * size
                balance += pnl
                trades.append(pnl)
                in_position = False
            elif exits.iloc[i]:
                exit_price = df["close"].iloc[i]
                pnl = (exit_price - entry_price) * size
                balance += pnl
                trades.append(pnl)
                in_position = False
        elif entries.iloc[i]:
            entry_price = df["close"].iloc[i]
            stop_price = entry_price * (1 - stop_loss_pct / 100)
            stop_distance = entry_price - stop_price
            risk_amount = balance * size_r_pct / 100
            size = risk_amount / stop_distance if stop_distance > 0 else 0.0
            in_position = True

        equity_curve[i] = balance

    return {"final_balance": balance, "equity_curve": equity_curve, "trades": trades}


def compute_metrics(df: pd.DataFrame, result: dict, initial_balance: float, timeframe: str) -> dict:
    equity = pd.Series(result["equity_curve"], index=df["timestamp"])
    bar_returns = equity.pct_change().fillna(0)

    periods_per_year = PERIODS_PER_YEAR.get(timeframe, 24 * 365)
    sharpe = 0.0
    if bar_returns.std() > 0:
        sharpe = (bar_returns.mean() / bar_returns.std()) * np.sqrt(periods_per_year)

    running_max = equity.cummax()
    drawdown = (equity - running_max) / running_max
    max_drawdown = abs(drawdown.min()) * 100

    total_return = (result["final_balance"] - initial_balance) / initial_balance * 100

    trades = result["trades"]
    win_rate = (sum(1 for t in trades if t > 0) / len(trades) * 100) if trades else 0.0

    daily_equity = equity.resample("1D").last().ffill()
    rolling_30d_return = daily_equity.pct_change(30).dropna() * 100

    return {
        "total_return_pct": round(total_return, 2),
        "sharpe": round(sharpe, 2),
        "max_drawdown_pct": round(max_drawdown, 2),
        "trade_count": len(trades),
        "win_rate_pct": round(win_rate, 2),
        "rolling_30d_return_min_pct": round(rolling_30d_return.min(), 2) if not rolling_30d_return.empty else None,
        "rolling_30d_return_mean_pct": round(rolling_30d_return.mean(), 2) if not rolling_30d_return.empty else None,
        "rolling_30d_return_max_pct": round(rolling_30d_return.max(), 2) if not rolling_30d_return.empty else None,
    }


def evaluate_against_bar(metrics: dict) -> str:
    if (
        metrics["max_drawdown_pct"] > 8
        or (metrics["rolling_30d_return_min_pct"] is not None and metrics["rolling_30d_return_min_pct"] < -4)
        or metrics["sharpe"] < 0
    ):
        return "FAILURE"
    if (
        metrics["rolling_30d_return_mean_pct"] is not None
        and metrics["rolling_30d_return_mean_pct"] >= 5
        and metrics["sharpe"] >= 1.2
        and metrics["max_drawdown_pct"] <= 8
    ):
        return "SUCCESS"
    return "INCONCLUSIVE"


def run(strategy_dir: Path, csv_path: Path, initial_balance: float, log_path: Path) -> dict:
    module, config = load_strategy(strategy_dir)
    df = load_ohlcv(csv_path)

    entries = module.generate_signals(df, config["params"])
    exits = module.generate_exits(df, config["params"])

    result = simulate(df, entries, exits, config["risk"], initial_balance)
    metrics = compute_metrics(df, result, initial_balance, config["timeframe"])
    verdict = evaluate_against_bar(metrics)

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "strategy": config["name"],
        "data_file": str(csv_path),
        "config": config,
        "metrics": metrics,
        "verdict": verdict,
    }

    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a") as f:
        f.write(json.dumps(record) + "\n")

    return record
