# LiveTradingBots

Live execution of the RSI mean-reversion strategy defined in the project's `CLAUDE.md`.
`bot.py` trades the **long side only** -- Kraken spot has no native short selling, so the
short leg from `Backtest/backtest.py`'s confirmed baselines isn't implemented here. Expect
live results to differ from the full backtested numbers for that reason.

Defaults come from each coin's confirmed baseline (`bot.py`'s `BASELINES` dict, kept in sync
with `CLAUDE.md` / `Backtest/VALIDATED_PARAMETERS.md`) based on `SYMBOL`:

- Long entry: RSI(period) below threshold, only when the range filter passes (if enabled)
- Long exit: RSI(period) at/above threshold, or the stop is hit
- Stop: ATR-based (if enabled for that coin) or a fixed percentage below entry
- Size: 0.5R (risk-based position sizing)

Position state (in a trade or not, entry/stop price, the resting stop order's id) persists
to a local `bot_state_<SYMBOL>.json` file so a restart doesn't forget an open position.

## Install

`install.sh` is a bash script. Run it from a bash shell:

```bash
cd LiveTradingBots
./install.sh
```

### Windows

Windows PowerShell/cmd.exe has no `bash` command, so running `bash LiveTradingBots/install.sh` directly in
PowerShell fails with `CommandNotFoundException`. Use one of:

- **WSL**: `wsl bash LiveTradingBots/install.sh`
- **Git Bash** (installed with Git for Windows): open Git Bash, then run `bash LiveTradingBots/install.sh`

## Configure

Edit `.env` (created from `.env.example` by `install.sh`) with your exchange API key/secret and desired
symbol/timeframe. `DRY_RUN=true` (the default) logs signals without placing orders.

## Run

```bash
source venv/bin/activate
python bot.py
```
