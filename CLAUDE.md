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

5. "Based on this conversation, Build me a Skill."
Based on this conversation enhance any skill, I use to include a gotcha section, so we don't make this mistake again.

6. "Automate this"

Be cautious when using it so I don't always improve in right direction.