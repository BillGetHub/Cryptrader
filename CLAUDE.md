# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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

Entry : rsi < 25
Stop : 1.4%
Size : 0.5R

Improve the strategy after backtest the strategy with scientific approach, i.e., change one variable at a time and verify if the result is better with the particular variable change.

Example :

01 Change 1 variable
02 Test run 
03 Measure versus the Goal
04 New Baseline, keep if better.

Please ask me to confirm whether New Baseline can be used before make amendments in the codes etc.

# Flow 

1. Launch Subagents when the project get more complex.
