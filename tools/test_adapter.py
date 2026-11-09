"""Adapter robustness: play tables while reshaping the state the way the real
SDK might differ from the docs, and require zero failed decisions.

    python3 tools/test_adapter.py
"""
import copy
import enum
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "bot"))
sys.path.insert(0, os.path.join(ROOT, "devkit"))
os.environ["SNGBOT_RAISE"] = "1"          # surface exceptions instead of falling back

import bots  # noqa: E402
import engine  # noqa: E402
import play  # noqa: E402
from poker_agent_sdk import LegalAction  # noqa: E402

mod = play.load_agent(os.path.join(ROOT, "bot", "agent.py"))


class Kind(enum.Enum):
    FOLD = "fold"
    CHECK = "check"
    CALL = "call"
    RAISE = "raise"


def enum_kinds(st):
    st.legal_actions = [LegalAction(Kind(la.kind), la.min_amount, la.max_amount) for la in st.legal_actions]
    return st


def dict_events(st):
    st.events = [vars(e).copy() for e in st.events]
    st.seats = [vars(s).copy() for s in st.seats]
    return st


def tuple_blinds(st):
    b = st.blinds
    st.blinds = (b.small, b.big, b.ante)
    st.config.payouts = {1: 50, 2: 30, 3: 20}
    return st


def pot_without_bets(st):
    st.pot = st.pot - sum(s.bet for s in st.seats)
    return st


def missing_fields(st):
    st.blinds = None
    st.to_call = None
    st.config.blinds = None
    st.history = None
    return st


def garbage_memory(st):
    return st


TRANSFORMS = [enum_kinds, dict_events, tuple_blinds, pot_without_bets, missing_fields, garbage_memory]


class Shaped(mod.Agent):
    def __init__(self, fn):
        self.fn = fn

    def act(self, state, memory):
        st = self.fn(copy.copy(state))
        if self.fn is garbage_memory and random.random() < 0.2:
            memory = bytes(random.getrandbits(8) for _ in range(random.choice([3, 1600, 2000])))
        return super().act(st, memory)


def main():
    ok = True
    for fn in TRANSFORMS:
        failed = decisions = 0
        for seed in range(25):
            rng = random.Random(seed)
            names = [rng.choice(bots.FIELDS["mix"]) for _ in range(8)]
            agents = [bots.ARCHETYPES[n]() for n in names]
            agents[seed % 8] = Shaped(fn)
            t = engine.Table(agents, seed=seed)
            t.run()
            st = t.stats[seed % 8]
            failed += st.failed
            decisions += st.decisions
            if st.last_error:
                print(f"   {fn.__name__}: {st.last_error}")
        status = "ok " if failed == 0 else "FAIL"
        ok &= failed == 0
        print(f"{status} {fn.__name__:18s} decisions={decisions} failed={failed}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
