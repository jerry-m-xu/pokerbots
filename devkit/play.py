"""Local sit-and-go simulator: our bot in one random seat, a field of archetypes.

    python3 devkit/play.py --tables 400                     # vs the default mix
    python3 devkit/play.py --tables 400 --field tough
    python3 devkit/play.py --tables 800 --ab '{"push_bb": 15}'   # A/B a parameter change
    python3 devkit/play.py --tables 200 --field self        # 8 copies of our bot
    python3 devkit/play.py --enforce-time                   # apply the 1 ms + bank rule

Prints average points per table (+- standard error), finishing places,
failed decisions and act() timing for our seat. Points are 50/30/20 for
1st/2nd/3rd, ICM split at the hand cap; a random bot averages 12.5.
"""
import argparse
import importlib.util
import json
import os
import random
import sys
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "bot"))
sys.path.insert(0, HERE)                     # stand-in SDK shadows any installed one

import bots  # noqa: E402
from engine import Table  # noqa: E402

_AGENT_MOD = None


def load_agent(path):
    global _AGENT_MOD
    if _AGENT_MOD is None:
        spec = importlib.util.spec_from_file_location("sngbot_agent", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _AGENT_MOD = mod
    return _AGENT_MOD


def run_one(job):
    seed, args, params = job
    random.seed(seed)
    mod = load_agent(os.path.join(ROOT, "bot", "agent.py"))
    hero = mod.Agent()
    if params:
        from sngbot.policy import P_DEFAULT
        hero.params = dict(P_DEFAULT, **params)
    rng = random.Random(seed)
    n = args["players"]
    if args["field"] == "self":
        agents, names = [mod.Agent() for _ in range(n)], ["self"] * n
        hero_seat = rng.randrange(n)
        agents[hero_seat] = hero
    else:
        pool = bots.FIELDS[args["field"]]
        names = [rng.choice(pool) for _ in range(n)]
        agents = [bots.ARCHETYPES[nm]() for nm in names]
        hero_seat = rng.randrange(n)
        agents[hero_seat] = hero
    names[hero_seat] = "HERO"
    table = Table(agents, seed=seed, hand_cap=args["hand_cap"], enforce_time=args["enforce_time"],
                  decision_ms=args["decision_ms"])
    points = table.run()
    st = table.stats[hero_seat]
    by_type = {}
    for s, nm in enumerate(names):
        if s != hero_seat:
            by_type.setdefault(nm, []).append(points[s])
    return dict(points=points[hero_seat], place=table.places[hero_seat], hands=table.hand_number,
                decisions=st.decisions, failed=st.failed, errors=st.errors, illegal=st.illegal,
                timeouts=st.timeouts, hist=st.hist, max_ms=st.max_ms, last_error=st.last_error,
                by_type=by_type)


def run(args, params, seeds, procs):
    jobs = [(s, args, params) for s in seeds]
    if procs <= 1:
        return [run_one(j) for j in jobs]
    with Pool(procs) as pool:
        return pool.map(run_one, jobs, chunksize=max(1, len(jobs) // (procs * 4)))


def summarize(res, label):
    n = len(res)
    pts = [r["points"] for r in res]
    mean = sum(pts) / n
    var = sum((p - mean) ** 2 for p in pts) / max(1, n - 1)
    places = [0] * 9
    for r in res:
        if r["place"]:
            places[r["place"]] += 1
    hist = [0] * 501
    for r in res:
        for i, c in enumerate(r["hist"]):
            hist[i] += c
    total = sum(hist)

    def q(p):
        acc = 0
        for i, c in enumerate(hist):
            acc += c
            if acc >= p * total:
                return i / 100.0
        return 5.0
    dec = sum(r["decisions"] for r in res)
    failed = sum(r["failed"] for r in res)
    print(f"\n== {label}: {n} tables, avg {sum(r['hands'] for r in res) / n:.0f} hands/table")
    print(f"   points/table {mean:6.2f} +- {(var / n) ** 0.5:.2f}   (random seat = 12.50)")
    print("   places       " + "  ".join(f"{p}:{100 * places[p] / n:4.1f}%" for p in range(1, 9)))
    print(f"   decisions    {dec}  failed {failed} (errors {sum(r['errors'] for r in res)}, "
          f"illegal {sum(r['illegal'] for r in res)}, timeouts {sum(r['timeouts'] for r in res)})")
    print(f"   act() ms     p50 {q(0.5):.2f}  p99 {q(0.99):.2f}  p99.9 {q(0.999):.2f}  "
          f"max {max(r['max_ms'] for r in res):.2f}")
    errs = [r["last_error"] for r in res if r["last_error"]]
    if errs:
        print(f"   last error   {errs[-1]}")
    by = {}
    for r in res:
        for nm, ps in r["by_type"].items():
            by.setdefault(nm, []).extend(ps)
    if by:
        print("   field avg    " + "  ".join(f"{nm}:{sum(v) / len(v):.1f}" for nm, v in sorted(by.items())))
    return mean, var / n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tables", type=int, default=200)
    ap.add_argument("--field", default="mix", choices=sorted(bots.FIELDS) + ["self"])
    ap.add_argument("--players", type=int, default=8)
    ap.add_argument("--hand-cap", type=int, default=250)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--procs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--enforce-time", action="store_true")
    ap.add_argument("--decision-ms", type=float, default=1.0)
    ap.add_argument("--params", default="", help="JSON overrides of policy.P_DEFAULT")
    ap.add_argument("--ab", default="", help="JSON overrides to compare against --params on the same seeds")
    a = ap.parse_args()
    args = dict(field=a.field, players=a.players, hand_cap=a.hand_cap,
                enforce_time=a.enforce_time, decision_ms=a.decision_ms)
    seeds = [a.seed * 1_000_003 + i for i in range(a.tables)]
    base = json.loads(a.params) if a.params else {}
    m1, v1 = summarize(run(args, base, seeds, a.procs), f"A {base or 'defaults'}")
    if a.ab:
        alt = dict(base, **json.loads(a.ab))
        m2, v2 = summarize(run(args, alt, seeds, a.procs), f"B {alt}")
        print(f"\n   B - A = {m2 - m1:+.2f} points/table  (+- {(v1 + v2) ** 0.5:.2f}, same seeds)")


if __name__ == "__main__":
    main()
