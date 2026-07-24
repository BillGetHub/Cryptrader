"""Live trading bot implementing the RSI mean-reversion strategy from CLAUDE.md.

Long entry: RSI(RSI_PERIOD) < RSI_ENTRY_THRESHOLD, and (if ENABLE_RANGE_FILTER)
only when price is within RANGE_MAX_DISTANCE_PCT of its RANGE_MA_PERIOD-bar SMA.
Long exit: RSI(RSI_PERIOD) >= RSI_EXIT_THRESHOLD, or the stop is hit.
Stop: ATR_MULTIPLIER x ATR(ATR_PERIOD) below entry if ENABLE_ATR_STOP, else a
fixed STOP_LOSS_PCT below entry.
Size: POSITION_SIZE_R percent of account balance risked per trade, sized off
the stop distance (same 0.5R sizing as Backtest/backtest.py).

Per-coin defaults come from BASELINES below (BTC/ETH/BNB's confirmed
2026-07-24 baselines, see CLAUDE.md / Backtest/VALIDATED_PARAMETERS.md); any
individual value can still be overridden via its environment variable for
other coins or manual testing.

Short side (RSI-overbought mean reversion) is intentionally NOT implemented
here. Every confirmed baseline's backtested numbers include a short leg, but
Kraken spot (this bot's actual venue) has no native short selling -- the
short leg in Backtest/backtest.py is backtest-only. This means live results
will differ from the full backtested win rate/Sharpe, since roughly a
quarter to a third of the backtested trades (the short side) simply won't
happen here.

Position state (in a trade or not, entry/stop price, size, the resting stop
order's id) is persisted to STATE_FILE so a process restart doesn't forget
an open position and risk double-entering. On each poll while in a
position, the bot checks whether the resting stop order already filled
(stop hit) before checking the RSI exit, so both exit paths are handled
correctly regardless of which fires first.

Known limitation carried over from the original version: the bot polls
every POLL_INTERVAL_SECONDS regardless of TIMEFRAME, so most polls will see
the same still-forming candle. This means signals can fire slightly before
a candle technically closes, unlike Backtest/backtest.py's fully-closed-bar
simulation. Not solved here -- a separate concern from the missing exit
logic / state tracking / ATR-stop / range-filter gaps this rewrite fixes.
"""
import json
import os
import time

import ccxt
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

QUOTE_CURRENCIES = ("USDT", "USDC", "USD", "EUR", "GBP")


def normalize_symbol(symbol: str) -> str:
    """Accept a bare pair like BTCUSDT and insert ccxt's required '/' before
    the quote currency (-> BTC/USDT). Symbols that already contain '/' are
    returned unchanged.
    """
    if "/" in symbol:
        return symbol
    for quote in QUOTE_CURRENCIES:
        if symbol.endswith(quote) and len(symbol) > len(quote):
            return f"{symbol[:-len(quote)]}/{quote}"
    return symbol


EXCHANGE = os.environ.get("EXCHANGE", "kraken")
API_KEY = os.environ.get("API_KEY", "")
API_SECRET = os.environ.get("API_SECRET", "")

SYMBOL = normalize_symbol(os.environ.get("SYMBOL", "BTCUSDT"))
TIMEFRAME = os.environ.get("TIMEFRAME", "1h")

# Each coin's own confirmed baseline (CLAUDE.md / Backtest/VALIDATED_PARAMETERS.md,
# 2026-07-24). Keyed on the bare pair form; any field can still be overridden
# by its environment variable below.
BASELINES = {
    "BTCUSDT": dict(
        rsi_period=14,
        rsi_entry=28.0,
        rsi_exit=29.0,
        enable_atr_stop=True,
        atr_period=10,
        atr_multiplier=2.0,
        stop_loss_pct=5.5,
        enable_range_filter=True,
        range_ma_period=200,
        range_max_distance_pct=2.0,
    ),
    "ETHUSDT": dict(
        rsi_period=12,
        rsi_entry=28.0,
        rsi_exit=29.0,
        enable_atr_stop=False,
        atr_period=21,
        atr_multiplier=2.0,
        stop_loss_pct=4.5,
        enable_range_filter=True,
        range_ma_period=200,
        range_max_distance_pct=2.5,
    ),
    "BNBUSDT": dict(
        rsi_period=12,
        rsi_entry=27.0,
        rsi_exit=29.0,
        enable_atr_stop=False,
        atr_period=21,
        atr_multiplier=2.0,
        stop_loss_pct=5.0,
        enable_range_filter=True,
        range_ma_period=200,
        range_max_distance_pct=4.0,
    ),
}
_baseline = BASELINES.get(SYMBOL.replace("/", ""), {})


def _env_bool(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).lower() == "true"


RSI_PERIOD = int(os.environ.get("RSI_PERIOD", _baseline.get("rsi_period", 14)))
RSI_ENTRY_THRESHOLD = float(os.environ.get("RSI_ENTRY_THRESHOLD", _baseline.get("rsi_entry", 28.0)))
RSI_EXIT_THRESHOLD = float(os.environ.get("RSI_EXIT_THRESHOLD", _baseline.get("rsi_exit", 29.0)))

ENABLE_ATR_STOP = _env_bool("ENABLE_ATR_STOP", _baseline.get("enable_atr_stop", False))
ATR_PERIOD = int(os.environ.get("ATR_PERIOD", _baseline.get("atr_period", 21)))
ATR_MULTIPLIER = float(os.environ.get("ATR_MULTIPLIER", _baseline.get("atr_multiplier", 2.0)))
STOP_LOSS_PCT = float(os.environ.get("STOP_LOSS_PCT", _baseline.get("stop_loss_pct", 5.0)))

ENABLE_RANGE_FILTER = _env_bool("ENABLE_RANGE_FILTER", _baseline.get("enable_range_filter", False))
RANGE_MA_PERIOD = int(os.environ.get("RANGE_MA_PERIOD", _baseline.get("range_ma_period", 200)))
RANGE_MAX_DISTANCE_PCT = float(os.environ.get("RANGE_MAX_DISTANCE_PCT", _baseline.get("range_max_distance_pct", 3.0)))

POSITION_SIZE_R = float(os.environ.get("POSITION_SIZE_R", "0.5"))
POLL_INTERVAL_SECONDS = int(os.environ.get("POLL_INTERVAL_SECONDS", "60"))

STATE_FILE = os.environ.get("STATE_FILE", f"bot_state_{SYMBOL.replace('/', '')}.json")

DRY_RUN = os.environ.get("DRY_RUN", "true").lower() == "true"

FLAT_STATE = {"in_position": False, "entry_price": None, "stop_price": None, "size": None, "stop_order_id": None}


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return dict(FLAT_STATE)


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def build_exchange() -> ccxt.Exchange:
    exchange_class = getattr(ccxt, EXCHANGE)
    return exchange_class({"apiKey": API_KEY, "secret": API_SECRET, "enableRateLimit": True})


def compute_rsi(closes: pd.Series, period: int) -> pd.Series:
    delta = closes.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def compute_atr(df: pd.DataFrame, period: int) -> pd.Series:
    prev_close = df["close"].shift(1)
    true_range = pd.concat(
        [df["high"] - df["low"], (df["high"] - prev_close).abs(), (df["low"] - prev_close).abs()], axis=1
    ).max(axis=1)
    return true_range.ewm(alpha=1 / period, min_periods=period).mean()


def fetch_ohlcv(exchange: ccxt.Exchange, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    return pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])


def position_size(account_balance: float, entry_price: float, stop_price: float) -> float:
    risk_per_trade = account_balance * POSITION_SIZE_R / 100
    stop_distance = entry_price - stop_price
    if stop_distance <= 0:
        return 0.0
    return risk_per_trade / stop_distance


def enter_long(exchange: ccxt.Exchange, price: float, stop_price: float) -> dict:
    balance = exchange.fetch_balance()["total"].get(SYMBOL.split("/")[1], 0.0)
    size = position_size(balance, price, stop_price)
    if size <= 0:
        print("Computed size <= 0 (balance too low or stop too close); skipping entry.")
        return dict(FLAT_STATE)

    print(f"Entry signal: stop={stop_price:.2f}, size={size:.6f}")

    stop_order_id = None
    if DRY_RUN:
        print("DRY_RUN enabled - no order placed.")
    else:
        exchange.create_market_buy_order(SYMBOL, size)
        stop_order = exchange.create_order(SYMBOL, "stop_loss", "sell", size, stop_price)
        stop_order_id = stop_order["id"]

    return {"in_position": True, "entry_price": price, "stop_price": stop_price, "size": size, "stop_order_id": stop_order_id}


def exit_long(exchange: ccxt.Exchange, state: dict, reason: str) -> dict:
    print(f"Exit signal ({reason}): closing position, size={state['size']}")
    if not DRY_RUN:
        if state["stop_order_id"]:
            try:
                exchange.cancel_order(state["stop_order_id"], SYMBOL)
            except ccxt.OrderNotFound:
                pass  # already filled or cancelled -- nothing to clean up
        exchange.create_market_sell_order(SYMBOL, state["size"])
    return dict(FLAT_STATE)


def stop_already_filled(exchange: ccxt.Exchange, state: dict) -> bool:
    if DRY_RUN or not state["stop_order_id"]:
        return False
    order = exchange.fetch_order(state["stop_order_id"], SYMBOL)
    return order["status"] not in ("open",)


def run_once(exchange: ccxt.Exchange, state: dict) -> dict:
    fetch_limit = max(RSI_PERIOD, ATR_PERIOD if ENABLE_ATR_STOP else 0, RANGE_MA_PERIOD if ENABLE_RANGE_FILTER else 0) + 50
    df = fetch_ohlcv(exchange, SYMBOL, TIMEFRAME, limit=fetch_limit)

    rsi = compute_rsi(df["close"], RSI_PERIOD).iloc[-1]
    price = df["close"].iloc[-1]
    low = df["low"].iloc[-1]

    print(f"[{SYMBOL}] price={price:.2f} rsi={rsi:.2f} in_position={state['in_position']}")

    if pd.isna(rsi):
        print("RSI not ready yet (insufficient warmup bars); skipping this poll.")
        return state

    if state["in_position"]:
        if state["stop_price"] is not None and low <= state["stop_price"]:
            print(f"Stop breached locally (low={low:.2f} <= stop={state['stop_price']:.2f}).")
            return exit_long(exchange, state, "stop")
        if stop_already_filled(exchange, state):
            print("Resting stop order already filled on the exchange.")
            return dict(FLAT_STATE)
        if rsi >= RSI_EXIT_THRESHOLD:
            return exit_long(exchange, state, f"rsi={rsi:.2f} >= {RSI_EXIT_THRESHOLD}")
        return state

    if ENABLE_RANGE_FILTER:
        sma = df["close"].rolling(RANGE_MA_PERIOD).mean().iloc[-1]
        if pd.isna(sma):
            print("Range filter SMA not ready yet (insufficient warmup bars); skipping this poll.")
            return state
        distance_pct = abs(price - sma) / sma * 100
        if distance_pct > RANGE_MAX_DISTANCE_PCT:
            print(f"Range filter blocked entry: {distance_pct:.2f}% from SMA > {RANGE_MAX_DISTANCE_PCT}%.")
            return state

    if rsi >= RSI_ENTRY_THRESHOLD:
        return state

    if ENABLE_ATR_STOP:
        atr = compute_atr(df, ATR_PERIOD).iloc[-1]
        if pd.isna(atr):
            print("ATR not ready yet (insufficient warmup bars); skipping this poll.")
            return state
        stop_price = price - ATR_MULTIPLIER * atr
    else:
        stop_price = price * (1 - STOP_LOSS_PCT / 100)

    return enter_long(exchange, price, stop_price)


def main() -> None:
    exchange = build_exchange()
    state = load_state()
    while True:
        try:
            state = run_once(exchange, state)
            save_state(state)
        except Exception as exc:  # noqa: BLE001 - keep the bot alive on transient API errors
            print(f"Error during trading loop: {exc}")
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
