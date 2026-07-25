"""Joint grid search over the RSI strategy's parameters, built on backtest.py.

Single-variable tuning (see README.md) hit a local maximum at 68.5% win rate
and couldn't clear it moving one lever at a time. This sweeps combinations of
levers together, fetching the data once and re-running the (fast, local,
no-network) simulation for every combination in the grid.

A joint search combining --enable-short with --enable-range-filter (only
trade when price is within X% of a 200-bar SMA -- i.e. filter OUT strong
trends, since RSI mean reversion works best range-bound) found a baseline
with 89 trades and Sharpe +1.53 at 2.5% range distance. Manually widening
the distance to trade a little Sharpe for more frequency found the current
confirmed baseline in CLAUDE.md (2026-07-24): 76.3% win rate, +1.75% return,
Sharpe +1.31, max drawdown -0.42%, 114 trades on BTC-USD 1h/730d --
    --rsi-entry 28 --rsi-exit 29 --stop-loss-pct 5.0
    --enable-short --short-rsi-entry 78 --short-rsi-exit 65
    --enable-range-filter --range-ma-period 200 --range-max-distance-pct 3.0
Note this isn't a monotonic tradeoff: 4% and 5% distance both dropped Sharpe
well below 1.2 (0.25 and 0.57) before 3% was found to be a local sweet spot,
so don't assume "more distance = more trades = smoothly less Sharpe" holds
outside the range already tested. Sharpe and drawdown clear CLAUDE.md's
Success thresholds, but 30d return (+0.38% best) is far short of +5%/30d --
even at 114 trades over 730 days with 0.5R risk per trade, this is a very
safe configuration but structurally capped on absolute return (see CLAUDE.md
for the full note; getting all three Success conditions at once likely needs
more frequent trading still or larger sizing, not just more threshold
tuning).

The *_GRID constants below are edited freely as tuning moves to new assets or
regions -- they are a scratch workspace, not a record. BTC's, ETH's, and
BNB's confirmed baselines are recorded permanently in CLAUDE.md and
Backtest/VALIDATED_PARAMETERS.md regardless of what the grid currently
contains -- full per-coin tuning history, including every pass's edge-hits
and corrections, is preserved there and in git history, not repeated here.
Each coin found genuinely different optimal parameters: BTC settled on
rsi_period=14 with ATR(10)x2.0; ETH and BNB both use rsi_period=12 with no
ATR-stop; short_rsi_exit landed at 45-50 for all three (far from the
original spec's untested assumptions); range_max_distance_pct varies from
2.0% (BTC) to 4.0% (BNB). Strong evidence each new coin needs its own full
pass through this process, not a copy of another coin's numbers.

As of 2026-07-24 the grid is re-centered for SOLUSDT's first pass -- a coin
none of BTC/ETH/BNB's tuning has touched. Centered on the union of what's
been found across the other three coins (rsi_entry 27-28, rsi_exit 29,
short_rsi_entry 76-78, short_rsi_exit 45-50, rsi_period 12 or 14,
range_max_distance_pct 2.0-4.0), but wide enough on each dimension to let
SOL's own price data find genuinely different values -- the same way each
prior coin's first pass started from a known region and widened toward
wherever the edge-hits pointed. Does not sweep --enable-atr-stop (matching
the established process) -- planned as a follow-up test once the fixed-stop
optimum is found and fully bracketed.

Pass 1 (4608 combos) was dramatically weaker than any of BTC/ETH/BNB's first
passes: 0/4608 combos even reached 70% win rate, and the best Sharpe found
was only +0.15 (vs 1.2+ eventually found for the other three coins).
short_rsi_entry (74, lower edge), short_rsi_exit (mostly 40, lower edge),
and rsi_entry (mostly 26, lower edge) all hit an edge; range_max_distance_pct
never used its lower edge (2.0) at all and leaned on its upper edge (4.0).
Pass 2 (this grid) widens all four -- rsi_entry substantially, since pass 1
gave no sign of leveling off. Whether SOL just doesn't suit this mean-
reversion shape as well as BTC/ETH/BNB, or the optimum is genuinely further
out than pass 1 reached, isn't yet answerable -- this pass should clarify
which.

Pass 2 (9216 combos) answered it: Sharpe rose from +0.15 to +1.07, and 6
combos cleared 70% win rate (vs 0 in pass 1) -- SOL responds to this
strategy, pass 1 just hadn't found where. Two regimes emerged: one pairing
stop=6.5/rsi_period=12/short_rsi_entry=68/short_rsi_exit=45, the other
stop=5.0/rsi_period=14/short_rsi_entry=70/short_rsi_exit=40 -- both stop
extremes (5.0, 6.5) beat the interior (5.5, 6.0), an unusual bimodal
pattern left as-is pending more data. range_max_distance_pct's ENTIRE top
15 sat at 3.0 -- the *lower* edge of pass 2's [3.0..6.0] grid, meaning
pass 2's widen-up guess was backwards (mirrors the exact mistake made on
BTC's pass 3). rsi_entry (22) and short_rsi_entry (68) both still hit their
lower edge even after widening. Pass 3 (this grid) corrects the
range_max_distance_pct direction and widens the other two further down.

Pass 3 (7680 combos) was a big jump: Sharpe +1.07 -> **+2.12** -- the best
result found anywhere in this project, beating even the multi-asset
portfolio (+1.98). 0/7680 combos hit Failure (down from 6108 in pass 2).
The bimodal stop_loss_pct pattern resolved cleanly to 5.0 (now the lower
edge, needs widening down); short_rsi_exit hit 55 (upper edge); rsi_entry
(18) and range_max_distance_pct (1.5) both still hit their lower edge even
after two rounds of widening down -- SOL clearly wants a much more
aggressive, selective configuration than any other coin (deeper oversold
entry, much tighter range filter). short_rsi_entry=64 is now interior and
dominated completely -- likely bracketed, checked with a fine-grained pass
here. rsi_period=12 now wins outright (the earlier bimodal pairing with 14
resolved) -- added 10 to bracket it on both sides. rsi_exit gave identical
Sharpe across 28/29/30 at every other-parameter combo tested (the RSI exit
rarely fires before the stop does in this regime) -- fixed to save runtime.

Pass 4 (3840 combos) raised Sharpe again to **+2.38**. stop_loss_pct=4.5,
short_rsi_exit (55/60, neither edge), rsi_period (10 ruled out, 12/14 both
remain), and range_max_distance_pct=1.5 are all now confirmed bracketed --
1.5 in particular is genuinely confirmed on both sides across passes 3-4
(beat 2.0-3.0 going one direction, beat 0.75-1.25 going the other).
short_rsi_entry narrowed to a confirmed-good 63-65 interior range. Only
rsi_entry is still unresolved: top result at 14, the lower edge, for a
fourth consecutive pass pushing lower (26 -> 22 -> 18 -> 14) -- worth one
more check before trusting it, since a lever that keeps sliding toward an
extreme every single pass is exactly the pattern an overfit result would
show. Pass 5 (this grid) fixes everything else at its confirmed value and
makes that check cheaply.

Pass 5 (60 combos) resolved it cleanly: rsi_entry gave an IDENTICAL Sharpe
across the entire 10-14 range tested. Not an overfit slide -- a plateau.
The joint (long+short) search's best config was then confirmed fully
bracketed: --rsi-entry 14 --rsi-exit 29 --rsi-period 12 --stop-loss-pct 4.5
--short-rsi-entry 64 --short-rsi-exit 55 --range-max-distance-pct 1.5,
78.2% win rate, Sharpe +2.38, the best result in the project. BUT checking
the long/short trade split (which this file didn't surface until the
--long-only addition below) revealed **0 long trades, 119 short** -- the
entire result is short-only, and Kraken spot can't short. The plateau
across rsi_entry 10-14 makes sense in hindsight: no long trades fire in
that whole range regardless of the exact threshold, so of course varying
it made no difference. grid_search.py hardcoded enable_short=True in every
combination and never checked whether the long side actually contributed
trades -- fine for BTC/ETH/BNB, whose tuned entries (27-28) stayed in
normal oversold territory where longs still fire often (BTC: 62 long/15
short), but SOL's joint optimizer found it more profitable to abandon the
long side entirely and lean on shorts. Added --long-only (disables the
short leg, skips sweeping short_rsi_entry/short_rsi_exit) and a warning
that fires automatically if a non-long-only run's top result has 0 long
trades, so this blind spot doesn't recur silently. This grid is re-centered
for SOL's first --long-only pass -- the joint search's findings don't
transfer, since they were entirely a short-side artifact.

Note: total_return_pct is the return over the whole fetched period, not a
30-day figure -- use worst_30d_return_pct / best_30d_return_pct to check
against CLAUDE.md's actual +5%/30d and -4%/30d thresholds.

Usage:
    python grid_search.py --symbol SOLUSDT --source ccxt --exchange binance --long-only
    python grid_search.py --sort-by sharpe --top-n 20
"""
import argparse
import itertools
import time

import pandas as pd

from backtest import DEFAULT_SYMBOL, INTERVAL_BARS_PER_YEAR, compute_metrics, fetch_data, simulate

STOP_LOSS_PCT_GRID = [4.0, 4.5, 5.0, 5.5, 6.0]  # broad first-pass range; no long-only SOL data yet
RSI_ENTRY_GRID = [24, 25, 26, 27, 28, 29]  # centered on BTC/ETH/BNB's shared 27-28 region -- the SOL joint
# search's 10-14 result told us nothing about the long side (0 long trades fired there)
RSI_EXIT_GRID = [28, 29, 30]  # all three other coins confirmed 29; bracketing a point either side
SHORT_RSI_ENTRY_GRID = [999]  # unused placeholder in --long-only mode (short leg disabled)
SHORT_RSI_EXIT_GRID = [0]  # unused placeholder in --long-only mode (short leg disabled)
RSI_PERIOD_GRID = [12, 14]  # BTC uses 14, ETH/BNB both use 12 -- genuinely unknown for SOL long-only
RANGE_MAX_DISTANCE_PCT_GRID = [1.5, 2.0, 2.5, 3.0, 4.0]  # spans SOL's short-side-tuned 1.5 through BNB's 4.0 --
# unknown whether the long side wants the same tight filter as the (non-deployable) short-heavy result did
RANGE_MA_PERIOD = 200  # confirmed best against 100 and 300 by hand (on BTC); not swept here

SORT_KEYS = {
    "win_rate": ["win_rate_pct", "sharpe"],
    "sharpe": ["sharpe", "win_rate_pct"],
    "return": ["best_30d_return_pct", "sharpe"],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Joint grid search for the RSI strategy's parameters.")
    parser.add_argument("--source", default="yfinance", choices=["yfinance", "ccxt"])
    parser.add_argument("--exchange", default="kraken")
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--interval", default="1h", choices=sorted(INTERVAL_BARS_PER_YEAR))
    parser.add_argument("--period", default="730d")
    parser.add_argument("--position-size-r", type=float, default=0.5)
    parser.add_argument("--initial-balance", type=float, default=10000.0)
    parser.add_argument(
        "--sort-by",
        default="sharpe",
        choices=sorted(SORT_KEYS),
        help="ranking used for the printed top results (default: sharpe, since that's the "
        "current CLAUDE.md Success gap). win_rate and return are also available.",
    )
    parser.add_argument("--top-n", type=int, default=15, help="how many top results to print")
    parser.add_argument("--csv-out", default=None, help="optional path to write every combination's results")
    parser.add_argument(
        "--long-only",
        action="store_true",
        help="Disable the short leg entirely (enable_short=False) and skip sweeping "
        "short_rsi_entry/short_rsi_exit. Use when a coin's joint (long+short) search produces a "
        "result dominated or entirely carried by the short side -- SOL's did (0 long / 119 short "
        "trades in its top result), which is non-deployable since Kraken spot can't short. This "
        "forces the search to find a genuine long-only edge instead.",
    )
    args = parser.parse_args()
    if args.symbol is None:
        args.symbol = DEFAULT_SYMBOL[args.source]
    return args


def main() -> None:
    args = parse_args()

    print(f"Fetching {args.symbol} {args.interval} data ({args.source})...")
    df = fetch_data(args)
    print(f"Got {len(df)} bars. Sweeping the grid...")

    short_entry_grid = [SHORT_RSI_ENTRY_GRID[0]] if args.long_only else SHORT_RSI_ENTRY_GRID
    short_exit_grid = [SHORT_RSI_EXIT_GRID[0]] if args.long_only else SHORT_RSI_EXIT_GRID

    combos = [
        combo
        for combo in itertools.product(
            STOP_LOSS_PCT_GRID,
            RSI_ENTRY_GRID,
            RSI_EXIT_GRID,
            short_entry_grid,
            short_exit_grid,
            RSI_PERIOD_GRID,
            RANGE_MAX_DISTANCE_PCT_GRID,
        )
        if combo[1] < combo[2] and (args.long_only or combo[3] > combo[4])  # rsi_entry < rsi_exit,
        # short_entry > short_exit (short_rsi_* is a placeholder and unchecked in --long-only mode)
    ]
    print(f"{len(combos)} valid combinations (entry/exit bands non-overlapping).")
    if args.long_only:
        print("--long-only: short leg disabled, short_rsi_entry/short_rsi_exit not swept.")

    start = time.time()
    results = []
    for i, (
        stop_loss_pct,
        rsi_entry,
        rsi_exit,
        short_rsi_entry,
        short_rsi_exit,
        rsi_period,
        range_max_distance_pct,
    ) in enumerate(combos):
        result = simulate(
            df,
            rsi_period,
            rsi_entry,
            rsi_exit,
            stop_loss_pct,
            args.position_size_r,
            args.initial_balance,
            enable_short=not args.long_only,
            short_rsi_entry=short_rsi_entry,
            short_rsi_exit=short_rsi_exit,
            enable_range_filter=True,
            range_ma_period=RANGE_MA_PERIOD,
            range_max_distance_pct=range_max_distance_pct,
        )
        metrics = compute_metrics(
            result["equity"], result["trades"], args.initial_balance, INTERVAL_BARS_PER_YEAR[args.interval]
        )
        results.append(
            {
                "stop_loss_pct": stop_loss_pct,
                "rsi_entry": rsi_entry,
                "rsi_exit": rsi_exit,
                "short_rsi_entry": short_rsi_entry,
                "short_rsi_exit": short_rsi_exit,
                "rsi_period": rsi_period,
                "range_max_distance_pct": range_max_distance_pct,
                "win_rate_pct": metrics["win_rate_pct"],
                "total_return_pct": metrics["total_return_pct"],
                "worst_30d_return_pct": metrics["worst_30d_return_pct"],
                "best_30d_return_pct": metrics["best_30d_return_pct"],
                "sharpe": metrics["sharpe"],
                "max_drawdown_pct": metrics["max_drawdown_pct"],
                "num_trades": metrics["num_trades"],
                "num_long_trades": metrics["num_long_trades"],
                "num_short_trades": metrics["num_short_trades"],
            }
        )
        if (i + 1) % 200 == 0:
            print(f"  {i + 1}/{len(combos)} combinations done...")

    elapsed = time.time() - start
    print(f"Done in {elapsed:.1f}s.\n")

    results_df = pd.DataFrame(results)

    win_rate_ok = results_df["win_rate_pct"] >= 70.0
    success = (
        (results_df["best_30d_return_pct"] >= 5.0)
        & (results_df["sharpe"] >= 1.2)
        & (results_df["max_drawdown_pct"] >= -8.0)
    )
    failure = (
        (results_df["max_drawdown_pct"] < -8.0)
        | (results_df["worst_30d_return_pct"] < -4.0)
        | (results_df["sharpe"] < 0)
    )
    print(f"Combinations reaching >=70% win rate:        {win_rate_ok.sum()} / {len(results_df)}")
    print(f"Combinations clearing CLAUDE.md Success:      {success.sum()} / {len(results_df)}")
    print(f"Combinations still hitting CLAUDE.md Failure: {failure.sum()} / {len(results_df)}\n")

    sort_cols = SORT_KEYS[args.sort_by]
    results_df = results_df.sort_values(sort_cols, ascending=False)

    if not args.long_only and results_df.iloc[0]["num_long_trades"] == 0:
        print(
            "WARNING: the top-sharpe combination has 0 long trades -- this result is entirely "
            "short-side and NOT deployable on a spot exchange that can't short. Consider re-running "
            "with --long-only to find a genuine long-side edge instead.\n"
        )

    print(f"Top {args.top_n} by {args.sort_by} (tiebreak: {sort_cols[1]}):")
    with pd.option_context("display.max_columns", None, "display.width", 220):
        print(results_df.head(args.top_n).to_string(index=False))

    if args.csv_out:
        results_df.to_csv(args.csv_out, index=False)
        print(f"\nFull results ({len(results_df)} rows) written to {args.csv_out}")


if __name__ == "__main__":
    main()
