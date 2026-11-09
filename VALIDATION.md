# Development validation — 2026-11-09

These checks use the local stand-in SDK, not the unreleased official starter kit.

- PokerKit 0.7.7: 1,500 random five-, six-, and seven-card showdown comparisons,
  plus wheel/two-trips ordering, exact shared-royal equity, and duplicate rejection: passed.
- Six adapter transformations over 25 tournaments each: 15,259 decisions,
  zero failed decisions. Covers enum actions, dictionary state, tuple blinds,
  differing pot conventions, missing fields, and corrupt memory.
- 400 eight-player tournaments against the local tough field, seed 1:
  default 19.12 points/table (standard error 1.01), experimental equity 19.90
  (standard error 1.02). Each completed more than 37,000 decisions with zero
  errors or illegal actions. The difference does not establish an improvement.
- Default timing in that run: p99 0.21 ms, p99.9 0.75 ms, maximum 6.09 ms.
  Experimental timing: p99 0.48 ms, p99.9 0.52 ms, maximum 8.24 ms.
  Wall-clock scheduling spikes exist; this is not proof of an official timing pass.
- A separate 100-table run with local timing enforcement enabled completed 9,270
  default-bot decisions with zero errors, illegal actions, or timeouts; maximum 0.43 ms.

The simulator's default payout is 50/30/20; the symmetric seat average is 12.5.
Results against these heuristic opponents do not predict tournament rankings or
measure GTO exploitability. Sampling is deadline-dependent and can vary between runs.

Reproduction commands are in README.md. The submission archive contains runtime
source only. Final official API, game rules, dependencies, and upload acceptance
remain unverified until the starter kit is released.
