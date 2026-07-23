"""RSI mean-reversion strategy.

Entry: rsi(period) < entry_threshold (oversold).
Exit (absent a hit stop-loss, handled by the backtest engine): rsi crosses back
above 50 (neutral), signalling the reversion has played out. CLAUDE.md defines
entry/stop/size but not a take-profit exit, so this is an explicit default —
adjust rsi_exit_threshold in config.yaml if a different exit is wanted.
"""
import pandas as pd


def compute_rsi(closes: pd.Series, period: int) -> pd.Series:
    delta = closes.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def generate_signals(df: pd.DataFrame, params: dict) -> pd.Series:
    rsi = compute_rsi(df["close"], params["rsi_period"])
    return rsi < params["rsi_entry_threshold"]


def generate_exits(df: pd.DataFrame, params: dict) -> pd.Series:
    rsi = compute_rsi(df["close"], params["rsi_period"])
    return rsi > params.get("rsi_exit_threshold", 50)
