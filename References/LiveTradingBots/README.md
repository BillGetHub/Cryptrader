# LiveTradingBots

Live execution of the RSI mean-reversion strategy defined in the project's `CLAUDE.md`:

- Entry: RSI(14) < 25
- Stop: 1.4% below entry
- Size: 0.5R (risk-based position sizing)

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
