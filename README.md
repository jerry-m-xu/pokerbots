# Kaden — Flop Auction Hold'em

Tournament bot for the Boston NO LIMIT '26 starter kit. Upload **dist/bot.zip**,
which contains agent.py and its sngbot modules at the archive root. Do not upload
the whole repository or agent.py alone. No site upload is performed by these tools.

This is an opponent-adaptive strategy with ICM decisions and sampled equity, not
a solved Nash/GTO strategy. The sealed auction and multiway tournament game have
not been solved here. Results measure performance against test bot families,
not unknown competitors; see VALIDATION.md.

The selected default is the pressure profile: wider opening and three-betting
ranges, smaller continuation bets, and three times the initial auction budget.
It scored best in our tested fields; the sample does not prove universal superiority.

## Variant strategy

- Auction: evaluates all ten possible flops and bids on the strongest combination.
  Spending scales with improvement, pot size, balance and the hand horizon.
- Equity: uses permitted eval7, excluding the two dead auction cards, our hole
  cards and the board from samples. Opponent ranges use observed participation.
  Small samples are shrunk toward a made-hand/draw estimate and stop at a deadline.
- Preflop: position ranges, steals against frequent folders, three-bets and
  payout-aware push/fold decisions. Unknown opponents start with conservative priors.
- Postflop: value bets, selective semi-bluffs, pot odds and payout risk. All-in
  opponents remain in equity calculations even when their round bet becomes zero.
- Runtime: table memory carries observations. Static tables load at import;
  legal raises are clamped and auction bids cannot exceed the balance.

## Build box

The official SDK environment is at ~/work/starter-kit/.venv.

```bash
cd ~/work/kaden-bot
source ~/work/starter-kit/.venv/bin/activate
python tools/test_official.py
python tools/pack.py
poker-agent check dist/bot.zip
```

For a fresh computer, unpack the official starter kit beside this repository,
create its Python 3.12 environment, install eval7==0.1.11, and install its three
SDK packages as described in the kit's README. The engine installs PokerKit 0.7.6
for local testing. Our runtime needs only eval7 and the SDK/protocol, not the
optional ML libraries. Never put the SDK or virtual environment inside bot/.

## Official matches and replay

Run a full eight-seat match, with seven example opponents:

```bash
poker-agent play bot ../starter-kit/examples/min_raiser ../starter-kit/examples/check_or_fold ../starter-kit/examples/min_raiser ../starter-kit/examples/check_or_fold ../starter-kit/examples/min_raiser ../starter-kit/examples/check_or_fold ../starter-kit/examples/min_raiser --tables 20 --seed kaden-final --no-history
python tools/smoke_official.py --opponent ../starter-kit/examples/min_raiser --tables 10
```

The smoke test uses actual SDK subprocesses, 1 ms decisions, zero bank and
20-hand heads-up tables. It approximates the published upload test; the hosted
validator remains the final authority. Normal SDK play uses a time bank.
Omit --no-history to save a replay, then run replay FILE --no-open. Over SSH,
forward the viewer's printed port to your Mac before opening it locally.

## Strategy comparisons

```bash
python tools/benchmark_official.py --tables 100 --seed 9000 --field auction --profiles baseline equity aggressive pressure --procs 2
python tools/benchmark_official.py --tables 100 --seed 7000 --field mixed --profiles baseline equity aggressive pressure --procs 2
```

The benchmark uses the unmodified official engine and scoring. It calls bots
directly for speed; its timings do not certify subprocess timing. The baseline
disables auctions and sampling but retains the corrected adapter. Auction
opponents actively bid; mixed includes tight, loose, shoving and calling bots.
Seeds differ from the initial tuning run and hero seats rotate. Deadline-based
sampling can produce different results under different machine loads.

The old devkit/ simulator is historical and does not implement this variant.
Use the official tools above for current validation.

## Offline position analysis

tools/evaluate_position.py uses PokerKit for standard Hold'em showdown equity.
It assumes random opponent hands and does not model the auction, so it is only
a reference. tools/test_evaluator.py cross-checks hand ranks against PokerKit.
Both stay outside the submission. Runtime sampling excludes auction dead cards.

Never commit participant keys or SSH private keys. Rebuild the ZIP after bot edits.
