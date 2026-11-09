# Kaden tournament pokerbot

A working **standard no-limit Texas Hold'em starting bot**, prepared for adaptation
when the tournament starter kit arrives. The submission adapter currently targets
a local stand-in SDK. **Official submission compatibility is not yet verified.**

This is a game-theory-informed, opponent-adaptive baseline, not a solved GTO
strategy. No exploitability bound or guarantee of winning against other bots is
claimed. Multiway no-limit tournament equilibrium is not solved by these heuristics.

## Strategy

- Position-dependent opening ranges and precomputed equity against starting-hand ranges.
- Short-stack shove/call decisions that account for tournament payouts through ICM.
- Persistent opponent estimates for opens, folds, aggression, and all-in calls,
  using conservative priors when observations are sparse.
- Postflop made-hand/draw estimates, pot odds, value betting and selective semi-bluffs.
- Legal-action clamping, bounded memory, time-aware calculations, and safe fallback actions.
- Experimental blocker-aware postflop sampling, available through `sample_equity`.
  It remains disabled by default unless testing supports enabling it.

The default simulator uses eight players, 2,000 chips, increasing blinds and
50/30/20 payouts. These are development assumptions, not confirmed event rules.

## Layout

`bot/` contains the submission source; `agent.py` is its entry point.
`devkit/` contains the local SDK, simulator, and several opponent archetypes.
`tools/` contains packaging, PokerKit position analysis, and verification tools.
`dist/bot.zip` is the prepared archive, with `agent.py` at its root.
Upload that ZIP after validating with the official kit; uploading `agent.py` alone
will omit the required `sngbot/` modules. Do not upload the repository ZIP.

## Run locally

Use Python 3.12. Simulation and packaging require only the standard library.

```bash
python3 devkit/play.py --tables 400 --field tough --procs 2
python3 devkit/play.py --tables 100 --field self --procs 2
python3 tools/test_adapter.py
python3 tools/pack.py
```

The simulator reports tournament points, placements, illegal actions, exceptions,
and decision timing. Its opponents are heuristics, not external tournament bots.
Its simplified engine does not implement short all-in raises failing to reopen
betting. Use the official engine for the final acceptance test.

## PokerKit position evaluation

PokerKit is used in offline analysis and independent evaluator tests. The inherited
packaging checks prohibit importing `pokerkit` and `poker_engine` in submission
source; that restriction must be checked against the official starter kit. The
runtime uses a standard-library evaluator validated against PokerKit.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python tools/test_evaluator.py
.venv/bin/python tools/evaluate_position.py --hero AsKh --board QsJh2c --samples 5000
```

The analyzer reports equity, wins, ties, sample count and standard error against
uniform random legal opponent hands. Heads-up river equity is enumerated exactly;
other positions are sampled reproducibly. Equity alone is not an action-EV estimate
and does not account for opponents' betting ranges or future decisions.

## When the starter kit arrives

1. Verify variant, deck, hole cards, seats, payouts, blinds, limits and memory budget.
2. Replace assumptions in `bot/agent.py` and `bot/sngbot/view.py` with the real SDK.
3. Resolve `VERIFY` markers, particularly action amounts and whether pot includes bets.
4. Run the official validator and matches against its example bots; check timeouts.
5. Rebuild `dist/bot.zip`, upload it on the Bot page, and confirm the site's test match passes.

Keep participant keys in a local environment or secret store, never in Git or the ZIP.
