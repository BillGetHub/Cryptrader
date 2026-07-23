"""CLI: run a strategy backtest and log the result as a baseline.

Example:
    python run_backtest.py --strategy RsiMeanReversion --data Data/BTCUSD_1h.csv
"""
import argparse
import json
from pathlib import Path

from backtest_engine import run


def main():
    parser = argparse.ArgumentParser(description="Run a strategy backtest against historical OHLCV data.")
    parser.add_argument("--strategy", required=True, help="Strategy folder name under Strategies/, e.g. RsiMeanReversion")
    parser.add_argument("--data", required=True, help="Path to historical OHLCV CSV file")
    parser.add_argument("--balance", type=float, default=10000.0, help="Initial account balance for the backtest")
    parser.add_argument("--log", default="backtest_results.log", help="Path to append JSON results to")
    args = parser.parse_args()

    strategy_dir = Path("Strategies") / args.strategy
    record = run(strategy_dir, Path(args.data), args.balance, Path(args.log))

    print(json.dumps(record["metrics"], indent=2))
    print(f"Verdict: {record['verdict']}")


if __name__ == "__main__":
    main()
