# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Purpose

To create a crypto autotrading bot by choosing the best proven method with references provided in subdirectories includes :

KrakenTradingKit

# Defining Success And Failure of this Cryptrader project 

Failure if :
* drawdown > 8%
* return < -4% / 30d
* sharpe < 0

Success if :
* return >= +5% / 30d
* sharpe >= 1.2 
* drawdoen <= 8%

Definition :
Sharpe score 
Profitability per unit of risk

Sharpe = (return - risk-free) /volatility

Sharpe < 1 Not Great
Sharpe between 1 to 2 is Good
Sharpe > 2 is Excellence

Entry : rsi < 28
Exit : rsi >= 29 (mean-reversion exit; not in original spec, added so a trade has a close condition)
Stop : volatility-adjusted -- 2.0x ATR(10), not a fixed percentage (see note below)
Size : 0.5R
RSI period : 14

Range filter: only enter (long or short) when price is within 2.0% of its 200-bar SMA --
i.e. skip strong trending conditions. RSI mean reversion tends to work best range-bound and
worst in strong trends either direction; a trade-with-the-trend filter was tested and hurt
results (see Backtest/README.md), this range filter is the opposite idea and helped a lot.

Short (backtest-only -- Kraken spot has no native short selling, would need margin/futures):
Entry : rsi > 76
Exit : rsi <= 50
Stop : same 2.0x ATR(10), applied above entry

Baseline confirmed 2026-07-24, backtested on genuine Binance BTCUSDT 1h, 730d (ccxt) via
Backtest/backtest.py: 78.9% win rate, +6.54% return, Sharpe +1.52, max drawdown -2.32%,
worst rolling 30d -1.90%, best rolling 30d +2.32%, 76 trades --
    --rsi-entry 28 --rsi-exit 29 --rsi-period 14 --enable-atr-stop --atr-period 10 --atr-multiplier 2.0
    --enable-short --short-rsi-entry 76 --short-rsi-exit 50
    --enable-range-filter --range-ma-period 200 --range-max-distance-pct 2.0

This supersedes the prior baseline (kept below for traceability), which was tuned and
validated only on Yahoo's BTC-USD fiat pair -- cross-checking those exact parameters against
genuine Binance BTCUSDT data found Sharpe dropping from +1.38 to +0.59, no longer clearing
the >=1.2 Success bar (though still positive, so not a Failure breach either). Unlike ETH and
BNB, BTC had never been tuned directly on real exchange data; this baseline fixes that via
the same grid_search.py -> hand-bracket process used for the other two coins. Four widening
passes were needed: rsi_entry, short_rsi_entry, short_rsi_exit, and range_max_distance_pct
all shifted meaningfully from their Yahoo-tuned values (76/50/2.0 vs the old 78/65/3.0),
while rsi_period=14 and stop_loss_pct's near-irrelevance both held from the Yahoo tuning.
A follow-up ATR-stop bracket (mirroring exactly how the original ATR-stop win was found)
then confirmed ATR(10)x2.0 as the local peak here -- notably not ATR(21)x2.0, the Yahoo-
tuned value; both period and multiplier were bracketed with losing neighbors on both sides.
Two close alternatives were also fully bracketed and considered: a fixed 5.5% stop (no ATR)
reaches higher Sharpe (+1.63) but far less return (+1.64%); ATR(21)x1.5 reaches higher return
(+8.03%) but lower Sharpe (+1.46). ATR(10)x2.0 was adopted as the best balance, not dominated
by either alternative on both axes. Still short of the +5%/30d Success bar, same gap seen on
every coin's baseline so far. Full comparison: Backtest/VALIDATED_PARAMETERS.md.

ETHUSDT confirmed baseline (2026-07-24, backtested via ccxt/Binance -- yfinance has no
ETH-USDT ticker, Kraken's ccxt pagination caps around 30 days): 78.1% win rate, +3.55%
return, Sharpe +1.25, max drawdown -2.64%, 105 trades. Tuned independently, not copied from
BTC -- BTC's exact parameters breach the Sharpe<0 Failure condition when reused unchanged on
ETH. ETH's optimal shape differs genuinely from BTC's: no ATR-stop (every ATR variant tested
made ETH worse, the opposite of BTC), RSI period 12 not 14, short-exit 45 not 65. Full detail
and every parameter set tested for both coins: Backtest/VALIDATED_PARAMETERS.md.

BNBUSDT confirmed baseline (2026-07-24, backtested via ccxt/Binance, 1h/730d): 75.7% win
rate, +3.56% return, Sharpe +1.51 (best of all three coins), max drawdown -1.32%, worst
rolling 30d -0.71%, best rolling 30d +0.80%, 152 trades. Found via three widening passes of
grid_search.py with every parameter dimension confirmed bracketed (none sitting on a search-
range edge). Shares ETH's RSI period (12, not BTC's 14) and no ATR-stop, but its own values
elsewhere -- rsi-entry 27, short-rsi-entry 78/short-rsi-exit 45, range filter widened to
4.0%. Trend-following and Bollinger Bands were both tested as alternatives and discarded:
Bollinger breaches Failure outright (worst 30d -4.11%, Sharpe -0.36); trend-following clears
Failure (unlike on BTC/ETH, where it breached 2-3 conditions) and its best-30d return
(+5.02%) alone clears the Success bar, but Sharpe +0.45 and 40.6% win rate are both far
short of the RSI+range-filter baseline. Full detail: Backtest/VALIDATED_PARAMETERS.md.

Multi-asset portfolio (2026-07-24, BTC+ETH+BNB each on its own confirmed baseline, capital
split evenly, genuine Binance data, re-run after BTC's Binance-native re-tune): 77.2% combined
win rate, +4.61% return, Sharpe +1.98 (best of anything tested this project), max drawdown
-0.82% (also tightest of anything tested), worst 30d -0.65%, best 30d +1.12%. Now beats every
single-coin baseline, including BNB alone (+1.51 Sharpe) -- with BTC's re-tuned baseline
pulling its own weight (Sharpe +1.56, up from the superseded baseline's +0.59 on Binance data),
diversification amplifies three genuinely strong per-coin edges instead of being dragged down
by one weak leg. Still short of the +5%/30d Success bar, same gap seen everywhere else.
**Recommended as the live-deployment approach**: run one bot.py instance per coin (each
already loads its own confirmed baseline via SYMBOL), capital split evenly across the three,
rather than a single coin alone. An earlier run of this same test (before BTC's re-tune) did
not beat BNB alone -- kept in VALIDATED_PARAMETERS.md for traceability. Full detail:
Backtest/VALIDATED_PARAMETERS.md.

Previous baselines (kept for traceability):
1. Original spec, never cleared Failure: Entry rsi<25, Exit rsi>=50, Stop 1.4%, no short.
2. Win-rate-focused, cleared Failure only: Entry rsi<27, Exit rsi>=30, Stop 4.5%, Short entry
   rsi>78 exit rsi<=62 stop 4.5%, no range filter -- 71.5% win rate, Sharpe +0.06.
3. First Success-clearing baseline, same as above but range filter at 2.5% instead of 3.0% --
   79.8% win rate, Sharpe +1.53, only 89 trades.
4. Fixed 5.0% stop version of the current entry/exit/range-filter numbers -- 76.3% win rate,
   +1.75% return, Sharpe +1.31, max drawdown -0.42%, 114 trades.
5. ATR(21)x2.0 stop, tuned and validated on Yahoo's BTC-USD only -- 74.0% win rate, +8.01%
   return, Sharpe +1.38, max drawdown -1.84%, 131 trades. Superseded 2026-07-24 after cross-
   checking on genuine Binance BTCUSDT data dropped its Sharpe to +0.59 (below the Success
   bar); re-tuned directly on Binance to produce the current baseline above.

Improve the strategy after backtest the strategy with scientific approach, i.e., change one variable at a time and verify if the result is better with the particular variable change.

Example :

01 Change 1 variable
02 Test run 
03 Measure versus the Goal
04 New Baseline, keep if better.

Please ask me to confirm whether New Baseline can be used before make amendments in the codes etc.

# Flow 

1. Launch Subagents when the project get more complex.

2. Write me on implementation specification.

Prompt :  
Before you need to create anything, you need to create a Plan or a specification for this project.
What does it do ?
Who is it for ?
Who is NOT for ?
What does success look like ?
What out of scope ?
Then walk me through each step of how you'd build it, and for each step show me the key decision you'd make and what you'd default to. Don't build anything yet.

3. Interview

Promp :
Before we start building, interview me about what we're trying to build.
Work with me to identify the core problem we're solving.
Who it is and isn't for.
As part of the interview, lets work through any key decisions together to help inform the implementation strategy. Then summarize it back to me as an implementation specification before we write any code.

4. Verify before you build.

The rule tells Claude what to verify.
The tool tells Claude how to verify.


5. "Based on this conversation, Build me a Skill."
Based on this conversation enhance any skill, I use to include a gotcha section, so we don't make this mistake again.

6. "Automate this"

Be cautious when using it so I don't always improve in right direction.

# 3 Layer Approach

1. Update my CLAUDE.md
2. Enable the necessary Tools

Based on what I'm building, what are some tools that could help with verification ?
examples :
External Technical tools
Internal Non-Technical tools

3. Understand human-validation zones

Prompt :
Enhance my CLAUDE.md to include :
Before you start any work, state how you work to verify it.
After you finish, run the verification and report results.
Before changing any code in [Hot zone, i.e., payment/], ask me first and explain the blast radius.

# Reference

# Review