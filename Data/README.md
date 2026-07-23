# Data

Historical OHLCV CSVs for backtesting go here. Not committed to the repo (see
`.gitignore`) since they're large and easy to re-download.

## Getting BTC/USD 1h data (default for RsiMeanReversion)

1. Go to https://www.cryptodatadownload.com/data/kraken/ and download the
   `BTCUSD` 1h CSV.
2. Save it here, e.g. `Data/BTCUSD_1h.csv`.
3. The engine expects at least these columns (case-insensitive):
   `timestamp, open, high, low, close`. Rename columns if the downloaded file
   uses different headers (e.g. `date` → `timestamp`, `unix` timestamps → ISO).

## Running a backtest against it

```bash
pip install -r requirements.txt
python run_backtest.py --strategy RsiMeanReversion --data Data/BTCUSD_1h.csv
```
