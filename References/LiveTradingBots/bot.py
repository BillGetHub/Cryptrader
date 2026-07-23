"""Live trading bot implementing the RSI mean-reversion strategy from CLAUDE.md.

Entry: RSI(period) < RSI_ENTRY_THRESHOLD
Stop: STOP_LOSS_PCT below entry
Size: POSITION_SIZE_R * account risk-per-trade, sized off the stop distance
"""
import os
import time

import ccxt
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

EXCHANGE = os.environ.get("EXCHANGE", "kraken")
API_KEY = os.environ.get("API_KEY", "")
API_SECRET = os.environ.get("API_SECRET", "")

SYMBOL = os.environ.get("SYMBOL", "BTC/USD")
TIMEFRAME = os.environ.get("TIMEFRAME", "1h")

RSI_PERIOD = int(os.environ.get("RSI_PERIOD", "14"))
RSI_ENTRY_THRESHOLD = float(os.environ.get("RSI_ENTRY_THRESHOLD", "25"))
STOP_LOSS_PCT = float(os.environ.get("STOP_LOSS_PCT", "1.4"))
POSITION_SIZE_R = float(os.environ.get("POSITION_SIZE_R", "0.5"))

DRY_RUN = os.environ.get("DRY_RUN", "true").lower() == "true"


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


def fetch_closes(exchange: ccxt.Exchange, symbol: str, timeframe: str, limit: int) -> pd.Series:
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
    return df["close"]


def position_size(account_balance: float, entry_price: float, stop_price: float) -> float:
    risk_per_trade = account_balance * POSITION_SIZE_R / 100
    stop_distance = entry_price - stop_price
    if stop_distance <= 0:
        return 0.0
    return risk_per_trade / stop_distance


def run_once(exchange: ccxt.Exchange) -> None:
    closes = fetch_closes(exchange, SYMBOL, TIMEFRAME, limit=RSI_PERIOD * 3)
    rsi = compute_rsi(closes, RSI_PERIOD).iloc[-1]
    price = closes.iloc[-1]

    print(f"[{SYMBOL}] price={price:.2f} rsi={rsi:.2f}")

    if rsi < RSI_ENTRY_THRESHOLD:
        stop_price = price * (1 - STOP_LOSS_PCT / 100)
        balance = exchange.fetch_balance()["total"].get(SYMBOL.split("/")[1], 0.0)
        size = position_size(balance, price, stop_price)

        print(f"Entry signal: rsi={rsi:.2f} < {RSI_ENTRY_THRESHOLD}, stop={stop_price:.2f}, size={size:.6f}")

        if DRY_RUN:
            print("DRY_RUN enabled - no order placed.")
        else:
            exchange.create_market_buy_order(SYMBOL, size)
            exchange.create_order(SYMBOL, "stop_loss", "sell", size, stop_price)


def main() -> None:
    exchange = build_exchange()
    while True:
        try:
            run_once(exchange)
        except Exception as exc:  # noqa: BLE001 - keep the bot alive on transient API errors
            print(f"Error during trading loop: {exc}")
        time.sleep(60)


if __name__ == "__main__":
    main()
