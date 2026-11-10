# Official-kit validation — 2026-11-09

Variant: flop_auction_holdem, unmodified supplied SDK/engine, Python 3.12,
PokerKit 0.7.6 for simulation and eval7 0.1.11 in the bot. The lightweight SDK
environment does not install unused ML dependencies from the full kit list.

## Strategy comparison

Eight players, default 2,000-chip stacks, 250-hand cap, 50/30/20 payouts.
The baseline uses the same corrected adapter with bidding and sampling disabled.
Values are average tournament points, followed by standard error, per table.

| Profile | Mixed bots, 100 tables, seed 7000 | Auction bots, 100 tables, seed 9000 |
|---|---:|---:|
| Baseline | 21.50 ± 1.60 | 8.50 ± 1.32 |
| Equity + auction | 26.80 ± 1.80 | 10.10 ± 1.60 |
| Aggressive betting | 27.40 ± 1.81 | 13.70 ± 1.86 |
| Pressure (selected) | 28.60 ± 1.83 | 16.10 ± 1.86 |

Earlier tuning used 60 tables per profile starting at seed 1000 against baseline
bots: baseline 14.00, auction 17.67, equity 20.50, aggressive 21.17 points/table.
In total, 1,040 strategy-comparison tables completed without illegal actions or
uncaught decision exceptions. These direct-call benchmarks do not enforce timeouts.
The pressure profile evaluated 23,766 hero decisions and 2,055 auctions in its
two 100-table runs. Hero seats rotate; comparison profiles use the same deal seeds.

These are selected test families, not real opponents or a GTO exploitability test.
The modest advantage of pressure over aggressive remains uncertain at this sample
size. Fresh seeds were used after initial tuning, but the final profile was selected
using these results; they are not an independent estimate of tournament performance.
Wall-clock deadlines make sampling and scores sensitive to machine load.

## Correctness and packaging

- Six official-state regression tests passed: legal budgeted bids, useful card
  selection, dead-card exclusion, all-in opponent retention, memory corruption
  and limits, and payout structures beyond four places. Legal-action testing uses
  two-, eight-, and ten-player official tables and fresh Agent objects per call.
- Four PokerKit comparison tests passed, including 1,500 random five-/six-/seven-card
  comparisons, wheel and full-house ordering, shared-board ties, duplicate rejection.
- The official packer and checker accepted the complete 12-file, 27,146-byte ZIP.
  SHA-256: 8c216998c9663f1b9e0460e72d59eaa2a03e990eeb519603dc45ba487a23c87d.

## Process timing

Actual SDK subprocess tests use 1 ms decision limits, no time bank, and the SDK's
default 2 ms transport allowance. Twenty 20-hand self-play tables completed 456
hero decisions with zero failures. An initial ten-table min-raiser run had three
failed decisions out of 262. A diagnostic rerun of twenty tables completed 486
decisions with zero failures and no runner errors. Twenty check/fold tables
completed 200 decisions with zero failures and no runner errors.

The official CLI also completed twenty eight-player tables against four min-raisers
and three check/fold examples: 45.0 points/table, 18 first places, and zero failed
decisions for every seat. These examples are weak opponents, so this is an integration
check rather than evidence of dominance over competitive bots.

Timing is not guaranteed: direct-call runs on this shared machine had scheduling
outliers above 500 ms. The earlier three failures were not diagnosed conclusively;
the later zero-failure run does not erase them. The hosted upload validator is the
final acceptance gate. No upload or active-bot change has been performed.

Reproduce with the commands in README.md and tools/smoke_official.py. The old
devkit results are obsolete for the auction variant and are not used here.
