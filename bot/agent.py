"""Tournament entry point: Agent.act(state, memory) -> (Action, memory bytes).

This is the only file that imports the organizers' SDK. Strategy lives in
sngbot/ and works on plain values (see sngbot/view.py for the adapter).
Every path returns a legal action: errors fall back to check-if-free-else-fold,
the same as the server's own fallback but without logging a failed decision.
"""
import gc
import os
import sys
import time

for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
           "VECLIB_MAXIMUM_THREADS", "NUMBA_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import poker_agent_sdk as _sdk  # noqa: E402

try:
    Action = _sdk.Action
except AttributeError:          # VERIFY: where the kit exports Action
    from poker_agent_protocol import Action  # noqa: E402

from sngbot import policy  # noqa: E402
from sngbot.auction import bids
from sngbot.tracker import Tracker  # noqa: E402
from sngbot.view import View, g, kname  # noqa: E402

# Warm every lookup table at import time (the import has its own startup allowance),
# then move everything allocated so far out of the collector's reach: full
# collections no longer rescan the tables, which keeps act() pauses short.
policy.strength([0, 5], [10, 20, 30])
gc.collect()
gc.freeze()


def _make(kind, la=None, amount=None):
    """Build an SDK Action. Named constructors first, generic constructor second."""
    if kind == "fold":
        return Action.fold()
    if kind == "check":
        return Action.check()
    if kind == "call":
        return Action.call()
    if kind == "raise" and hasattr(Action, "raise_to"):
        return Action.raise_to(int(amount))
    return Action(g(la, "kind", kind), int(amount) if amount is not None else g(la, "min_amount"))


def _legal(state):
    out = {}
    for la in g(state, "legal_actions", ()) or ():
        out[kname(g(la, "kind"))] = la
    return out


def fallback(state):
    """Check if free, else fold, else the automatic choice."""
    legal = _legal(state)
    if "check" in legal:
        return _make("check")
    if "fold" in legal:
        return _make("fold")
    las = g(state, "legal_actions", ()) or ()
    if las:
        first = las[0]
        return Action(g(first, "kind"), g(first, "min_amount"))
    return _make("check")


def to_action(d, state):
    legal = _legal(state)
    kind = d[0]
    if kind in ("raise", "allin"):
        rk = "raise" if "raise" in legal else ("bet" if "bet" in legal else None)
        if rk is None:
            kind = "call"
        else:
            la = legal[rk]
            lo = int(g(la, "min_amount", 0))
            hi = int(g(la, "max_amount", lo))
            amt = hi if kind == "allin" else max(lo, min(hi, int(d[1])))
            return _make(rk, la, amt)
    if kind == "call":
        if "call" in legal:
            return _make("call")
        kind = "check"
    if kind == "check" and "check" in legal:
        return _make("check")
    if kind in ("check", "fold"):
        return fallback(state)
    return fallback(state)


class Agent(_sdk.Agent):
    params = None   # devkit overrides this for A/B runs

    def act(self, state, memory):
        t0 = time.perf_counter_ns()
        P = self.params or policy.P_DEFAULT
        cfg = g(state, "config")
        try:
            tracker = Tracker.load(memory, g(cfg, "starting_stack", 0))
            tracker.consume(g(state, "events", ()))
            mem_out = tracker.dump()
        except Exception:
            if os.environ.get("SNGBOT_RAISE"):
                raise
            tracker = Tracker.load(b"", g(cfg, "starting_stack", 0))
            mem_out = memory if isinstance(memory, (bytes, bytearray)) else b""
        mem_out = bytes(mem_out[:g(cfg, "memory_bytes", 65536)])
        try:
            phase = kname(g(state, "phase", "betting"))
            if phase == "auction":
                return Action("bid", cards=bids(state, P.get("auction_mult", 1.0))), mem_out
            if phase != "betting":          # VERIFY: phases a variant adds
                return fallback(state), mem_out
            v = View(state, tracker)
            d = policy.decide(v, tracker, P, t0 + int(P["budget_us"]) * 1000)
            return to_action(d, state), mem_out
        except Exception:
            if os.environ.get("SNGBOT_RAISE"):
                raise
            return fallback(state), mem_out
