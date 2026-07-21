# Cryptrader

An AI-driven crypto auto trader for Kraken. It asks Claude for a directional
outlook (Bullish / Bearish / Neutral) on a market, backed by live OHLCV data,
funding rates, and web search, then acts on that outlook automatically:
opening, closing, or reversing a Kraken Futures position.

This project is built on top of
[RobotTraders/KrakenTradingKit](https://github.com/RobotTraders/KrakenTradingKit)
(commit `e1a6ca0`), a Kraken Spot/Futures API kit and AI trading assistant
framework. See [NOTICE.md](NOTICE.md) for details on what was changed.

Requires Python 3.12 or 3.13.

## Clone

```bash
git clone https://github.com/billgethub/cryptrader.git
cd cryptrader
```

## Install

```bash
uv sync
```

(or `pip install -e .` if you're not using [uv](https://docs.astral.sh/uv/))

## Setup

1. Copy the example environment file and fill in your own Kraken API
   credentials (used by the notebooks under `notebooks/`):

   ```bash
   cp .env.example .env
   ```

2. Copy the bot secrets file and fill in your Kraken, Anthropic, and
   (optionally) Discord credentials:

   ```bash
   cp bots/daily_active_trader_secrets_example.toml bots/daily_active_trader_secrets.toml
   ```

   Files matching `bots/*secrets*.toml` are gitignored, so your credentials
   never get committed.

## Run the auto trader

The included bot, `daily_active_trader`, asks Claude for a 24-hour outlook on
Bitcoin (`PF_XBTUSD` on Kraken Futures) once per invocation, then sizes and
places the resulting order:

```bash
python -m ai_assistant daily_active_trader
```

Run it on a schedule (cron, a GitHub Action, etc.) for a fully automatic
trader. Configuration lives in `bots/daily_active_trader.toml`:

- `demo = true` — trades against Kraken's demo/paper futures environment
  (fake funds, real order flow). **This is the default when the field is
  absent**, so a config never trades with real money by accident.
- `dry_run` — when `true`, the bot decides an action but never places orders,
  not even on the demo account. Defaults to `false`.
- `strategy.balance_fraction` — fraction of account capital risked per entry.
- `strategy.min_confidence` — minimum AI confidence required to act.

Start with `dry_run = true` for a first run to see the decision without any
order, then `dry_run = false` to paper trade for real on the demo account.
Only once you've reviewed several runs' logs under `logs/` (and Discord
notifications, if configured) should you consider going live.

Going live (`demo = false`) with real funds also requires setting the
`CRYPTRADER_CONFIRM_LIVE=yes` environment variable, or the run aborts before
placing any order — see [`ai_assistant/README.md`](ai_assistant/README.md#modes).

## Project layout

- `kraken_kit/` — Kraken Spot and Futures REST API clients and connectors.
- `ai_assistant/` — the Claude-driven assistant: prompt/tool loop, config
  loading, structured outlook parsing.
- `strategies/` — trading strategies that turn an AI outlook into orders.
- `common/` — shared secrets loading, logging, and Discord notifications.
- `bots/` — per-bot TOML configuration and secrets.
- `notebooks/` — Jupyter notebooks for exploring the Spot/Futures APIs.

## Support the Channel

[Sign up to Kraken](https://www.kraken.com/en-fr/partnercampaign/robottraders) and get $15 worth of BTC for free. The link won't work with a VPN enabled (only during account creation). This is an affiliate link from the upstream KrakenTradingKit project; it supports RobotTraders in producing and distributing open-source content for free.

## Disclaimer

This software is provided "as is", without warranty of any kind, express or implied, including but not limited to the warranties of merchantability, fitness for a particular purpose, and non-infringement. In no event shall the authors be liable for any claim, damages, or other liability arising from the use of this software.

Not investment advice. Cryptocurrency and derivatives trading involves substantial risk of loss. Always verify that the software behaves correctly before using it with real funds. You are solely responsible for your trading decisions and any resulting gains or losses.

Payward Europe Solutions Limited t/a Kraken is regulated by the Central Bank of Ireland. Derivatives products are provided by Payward Europe Digital Solutions (CY) Limited, regulated by the Cyprus Securities and Exchange Commission (CySEC), licence no 342/17.

FOR MORE INFORMATION AND APPLICABLE CONDITIONS OR LIMITATIONS, PLEASE CONSULT https://www.kraken.com/legal/disclosures

## Licence

[AGPL-3.0](LICENSE), inherited from the upstream KrakenTradingKit project. See [NOTICE.md](NOTICE.md).
