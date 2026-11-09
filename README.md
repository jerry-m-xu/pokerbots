# Pokerbot: 8-player sit-and-go (No Limit 2026, Boston)

Team "Fade GTO-Jam or GTFO". Bot written against the starter-kit API as documented
before the kit's release; everything SDK-specific is in `bot/agent.py` and
`bot/sngbot/view.py`, marked `VERIFY`.

## Layout

```
bot/                    the upload: zip this folder (agent.py at the root)
  agent.py              Agent.act(state, memory): adapter, safety wrapper, legal-action builder
  sngbot/view.py        state -> plain values (duck-typed; positions, pot, blinds, payouts)
  sngbot/tracker.py     event stream -> per-seat stats, packed into memory (~1.6 KB)
  sngbot/policy.py      the strategy; tunable knobs in P_DEFAULT
  sngbot/icm.py         hero-only Malmuth-Harville ICM (~10 us)
  sngbot/ranges.py      hand percentile + equity vs top-X% ranges
  sngbot/preflop_data.py  generated tables (tools/build_preflop.py)
  sngbot/cards.py       card parsing, 7-card evaluator (~1.5 us), 169 hand classes
devkit/                 local testing only, never uploaded
  poker_agent_sdk/      stand-in SDK built from the docs
  engine.py             8-max NLHE SNG engine (side pots, blind levels, hand cap + ICM)
  bots.py               opponent archetypes and field mixes
  play.py               simulator: points/table, places, failed decisions, act() timing, A/B
tools/
  build_preflop.py      regenerate preflop tables (~40 s on 16 cores)
  test_adapter.py       plays tables with reshaped states (enum kinds, dicts, tuple blinds...)
  pack.py               zip bot/ with the upload checks
```

## Commands

```bash
python3 devkit/play.py --tables 1000                    # vs default field mix
python3 devkit/play.py --tables 2000 --field tough      # mix | tough | soft | kit | self
python3 devkit/play.py --tables 3000 --ab '{"push_bb": 10}'   # A/B a knob, same seeds
python3 devkit/play.py --tables 800 --procs 4 --enforce-time  # 1 ms + 100 ms bank rule
python3 tools/test_adapter.py                           # must print ok for every line
python3 tools/pack.py                                   # -> dist/bot.zip
rsync -az --exclude __pycache__ --exclude dist ./ no-limit-2026-build:work/pokerbots/
```

Run timing checks with `--procs 4` or fewer: with every core busy, the OS adds
multi-millisecond stalls that are not the bot's.

Baseline (default knobs, 2026-11-09), points per table, where a random seat
gets 12.5: mix 25.4, tough 19.6, soft 26.3, kit examples 31.7, self-play 12.9.
On the build box: act() p50 0.06 ms, p99.9 0.24 ms, max 0.40 ms; import 39 ms.

## Strategy

- **Deep (> 13 BB first in):** open the top X% of hands by players left to act
  (BTN ~42%, UTG ~11%), widened to `0.95 * P(all fold) - 0.10` against seats
  that fold to raises (worth about +1.4 points/table in A/B). Raise 2.3 BB.
- **Short:** first in at <= 13 BB, or facing one raise at <= 22 BB: shove or
  fold, whichever has the higher **ICM** value. Callers each call with their
  observed call-vs-all-in frequency; equity comes from `ranges.eq_vs_range`.
- **Facing an all-in** (or a bet of >= 40% of the stack): call only if ICM
  EV(call) > EV(fold). This automatically tightens on the bubble (a 4k stack
  needs ~70% to call the 6k leader at 6k/4k/4k/2k) and loosens heads-up.
- **Postflop:** made-hand + draw strength, discounted by bet size and the
  bettor's aggression (passive bots betting big = strong). Value-bet ~65% pot,
  heads-up c-bets against folders, semi-bluff strong draws, no multiway bluffs.
- **Opponent model:** per-seat VPIP, PFR, open %, fold-to-raise, call-vs-all-in,
  shove %, postflop aggression, and shown shoving hands, shrunk to `tracker.PRIOR`.

## When the kit drops (event start)

1. Put the kit on the build box: rerun `/no-limit-2026-setup`, or download it
   with the saved API key, then `scp` it to the box. Read `RULES.md`, `AGENTS.md`,
   `README.md` and `sdk/`.
2. **Variant check.** If it isn't 2-card hold'em with a 52-card deck: update
   `cards.py` (deck/evaluator), `tools/build_preflop.py` (deal sizes), and
   `policy.decide` (currently it check/folds when `len(hole) != 2`). New phases
   or action kinds play the automatic choice in `agent.py` until handled.
3. **Resolve the VERIFY items** against the real SDK:
   - imports: `poker_agent_sdk.Agent`, and where `Action` lives
   - action kind names (`raise` vs `bet`) and how a raise is built
   - `state.blinds` / `config.blinds` shape, `config.payouts` shape
   - seat `status` strings; seat ids increase clockwise; heads-up button posts SB
   - event kinds and amounts: `call` = chips added, `raise` = total bet this round
   - `state.pot` with or without current bets (the view handles both)
4. Set `devkit/engine.py` `DEFAULT_SCHEDULE` to the real blind schedule.
5. Test with the real kit (8 seats = repeat folders):
   ```bash
   poker-agent check bot/agent.py
   poker-agent play bot examples/check_or_fold examples/min_raiser bot examples/min_raiser examples/check_or_fold bot examples/min_raiser --tables 200
   poker-agent pack bot bot.zip
   ```
   Zero failed decisions, then upload by ~T+15 so practice runs score it.
6. Upload at least 5 minutes before each scored round (the test match must pass).

## Between rounds

- Download the round hand history. Refit `tracker.PRIOR` to the real field
  (open, shove and call-vs-all-in rates; fold-to-raise) and reweight
  `devkit/bots.py` `FIELDS` to look like it.
- Finish distribution: many 4ths = bubble leak, many 8ths = early stack-offs.
- One change per round, A/B tested with 3,000+ tables; keep the last good
  upload ready to reactivate. Nothing untested before rounds 5-6 (52% of score).

## Next upgrades

- Postflop equity by Monte Carlo against the bettor's range (eval7 is installed on
  the servers), within a measured time budget.
- Bet-size fingerprints for common bots (fixed 3x, always min-raise, pot).
- Hand-cap awareness: fold marginal spots when the blinds can't bust us before hand 250.
- A hand-history analyzer once the real format is known.
