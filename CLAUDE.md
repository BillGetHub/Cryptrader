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
Stop : volatility-adjusted -- 2.0x ATR(21), not a fixed percentage (see note below)
Size : 0.5R
RSI period : 14

Range filter: only enter (long or short) when price is within 3.0% of its 200-bar SMA --
i.e. skip strong trending conditions. RSI mean reversion tends to work best range-bound and
worst in strong trends either direction; a trade-with-the-trend filter was tested and hurt
results (see Backtest/README.md), this range filter is the opposite idea and helped a lot.

Short (backtest-only -- Kraken spot has no native short selling, would need margin/futures):
Entry : rsi > 78
Exit : rsi <= 65
Stop : same 2.0x ATR(21), applied above entry

Baseline confirmed 2026-07-24, backtested on BTC-USD 1h, 730d (yfinance) via Backtest/backtest.py:
74.0% win rate, +8.01% return, Sharpe +1.38, max drawdown -1.84%, worst rolling 30d -1.27%,
best rolling 30d +2.40%, 131 trades. The stop changed from a fixed 5.0% to a volatility-
adjusted one (2.0x the 21-period Average True Range) -- the stop distance now widens or
narrows with how volatile the market currently is, instead of using the same percentage
regardless of conditions. This alone roughly 4.6x'd total return (+1.75% -> +8.01%) and
raised Sharpe (+1.31 -> +1.38) versus the prior fixed-stop baseline, the single biggest
improvement of any change made this session. Both ATR parameters were bracketed and
confirmed as local peaks: multiplier 1.5 and 2.5 were both worse (Sharpe 1.14 and 0.99 vs
2.0's 1.38); period 10 and 30 were both worse (Sharpe 1.21 and 1.16 vs 21's 1.38). Clears
all Failure conditions and now Sharpe/drawdown clear Success by a wider margin than before,
but 30d return (+2.40% best) is still short of the +5%/30d Success bar -- closer than any
prior baseline, but still short. Two structurally different strategies (fast/slow moving-
average trend-following, and Bollinger Band mean reversion) and a naive multi-asset
diversification (same parameters reused unchanged on ETH/SOL) were also tested and all
underperformed this baseline, some badly enough to breach Failure conditions -- see
Backtest/README.md for details. The ATR-stop win suggests the remaining gap to full Success
is more likely closable through refining risk mechanics (like this) than through a wholesale
different signal.

Data-source caveat (2026-07-24): the numbers above were validated on Yahoo's BTC-USD fiat
pair only. Cross-checked against genuine Binance BTCUSDT with identical parameters (found
incidentally via the multi-asset portfolio test below), results are meaningfully weaker --
Sharpe +0.59 not +1.38, no longer clearing the >=1.2 Success bar (though still positive, so
not a Failure breach), return +3.23% not +8.01%. ETH and BNB were both tuned directly on
Binance from the start, so neither shares this exposure; BTC has not yet been re-tuned there
-- an open question, not yet attempted. Full detail: Backtest/VALIDATED_PARAMETERS.md.

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
split evenly, genuine Binance data): 74.2% combined win rate, +3.45% return, Sharpe +1.27,
max drawdown -1.00% (tightest of anything tested this project), worst 30d -0.87%, best 30d
+1.00%. Clears Sharpe/drawdown Success with the safest risk profile yet, but diversification
compresses both tails together -- best-30d return ends up further from the +5% target than
any single-coin baseline, not closer. Does not beat BNB alone; not adopted as a replacement
for the per-coin baselines. Full detail: Backtest/VALIDATED_PARAMETERS.md.

Previous baselines (kept for traceability):
1. Original spec, never cleared Failure: Entry rsi<25, Exit rsi>=50, Stop 1.4%, no short.
2. Win-rate-focused, cleared Failure only: Entry rsi<27, Exit rsi>=30, Stop 4.5%, Short entry
   rsi>78 exit rsi<=62 stop 4.5%, no range filter -- 71.5% win rate, Sharpe +0.06.
3. First Success-clearing baseline, same as above but range filter at 2.5% instead of 3.0% --
   79.8% win rate, Sharpe +1.53, only 89 trades.
4. Fixed 5.0% stop version of the current entry/exit/range-filter numbers -- 76.3% win rate,
   +1.75% return, Sharpe +1.31, max drawdown -0.42%, 114 trades.

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