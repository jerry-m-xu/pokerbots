"""Per-seat opponent statistics carried in the table's memory bytes.

The table's public event stream is folded into a fixed-layout int32 array,
which round-trips through `memory` in about a microsecond. Layout changes
bump MAGIC, so stale memory is discarded instead of misread.

Event semantics (from the kit docs; verify against RULES.md on the day):
  hand(amount=hand no.)  ante/blind(amount=chips posted)
  fold  check  call(amount=chips added)  raise(amount=total bet this round)
  board(cards=new cards)  show(cards)  win(amount)  stack(amount=stack at hand end)
"""
from array import array

from .cards import hand_class, parse_cards
from .ranges import PCT

MAGIC = 0x5B0703
MAXS = 16          # seats tracked (ids 0..15)

# header slots
H_MAGIC, H_HAND, H_STREET, H_MAXBET, H_RAISES, H_LASTRAISER, H_LASTAI, \
    H_PFRAISES, H_PFAGG, H_SB, H_BB, H_ANTE, H_NBLINDS, H_NLIMP = range(14)
HS = 16

# per-seat slots
(S_HANDS, S_VPIP, S_PFR, S_OPEN_OPP, S_OPEN, S_SHOVE, S_FR_OPP, S_FR_FOLD,
 S_AI_OPP, S_AI_CALL, S_P_AGG, S_P_CALL, S_P_FOLD, S_P_CHECK,
 S_SH_SUM, S_SH_N, S_CA_SUM, S_CA_N, S_FLAGS, S_STACK, S_RBET, S_START) = range(22)
NS = 24

F_IN, F_VPIP, F_PFR, F_OPENOPP, F_FROPP, F_SHOVED, F_CALLEDAI, F_FOLDED = (1 << i for i in range(8))

ACTIONS = {"fold", "check", "call", "raise", "bet"}

# Population priors: (prior rate, pseudo-observations). Refit these from the
# round hand histories between rounds.
PRIOR = {
    "vpip": (0.28, 8), "pfr": (0.16, 8), "open": (0.20, 8), "shove": (0.05, 12),
    "fold_to_raise": (0.68, 5), "call_ai": (0.22, 4), "agg": (0.35, 6),
}


def _kind(ev):
    k = getattr(ev, "kind", None)
    if k is None and isinstance(ev, dict):
        k = ev.get("kind")
    k = getattr(k, "value", k)
    return str(k).lower().rsplit(".", 1)[-1] if k is not None else ""


def _field(ev, name):
    v = getattr(ev, name, None)
    if v is None and isinstance(ev, dict):
        v = ev.get(name)
    return v


class Tracker:
    __slots__ = ("a",)

    def __init__(self, a):
        self.a = a

    # ------------------------------------------------------------ memory
    @classmethod
    def load(cls, memory, starting_stack=0):
        if memory and len(memory) == 4 * (HS + MAXS * NS):
            a = array("i")
            a.frombytes(bytes(memory))
            if a[H_MAGIC] == MAGIC:
                return cls(a)
        a = array("i", [0]) * (HS + MAXS * NS)
        a[H_MAGIC] = MAGIC
        a[H_LASTRAISER] = -1
        a[H_PFAGG] = -1
        for s in range(MAXS):
            a[HS + s * NS + S_STACK] = int(starting_stack or 0)
        return cls(a)

    def dump(self):
        return self.a.tobytes()

    # ------------------------------------------------------------ events
    def consume(self, events):
        if not events:
            return
        a = self.a
        for ev in events:
            k = _kind(ev)
            if k in ACTIONS:
                s = _field(ev, "seat")
                if s is not None and 0 <= s < MAXS:
                    self._action(int(s), k, int(_field(ev, "amount") or 0))
            elif k == "hand":
                self._new_hand(int(_field(ev, "amount") or 0))
            elif k == "blind" or k == "ante":
                s = _field(ev, "seat")
                amt = int(_field(ev, "amount") or 0)
                if s is None or not 0 <= s < MAXS:
                    continue
                b = HS + int(s) * NS
                self._enter(b)
                a[b + S_STACK] -= amt
                if k == "ante":
                    if amt > a[H_ANTE]:
                        a[H_ANTE] = amt
                    continue
                a[b + S_RBET] += amt
                if a[b + S_RBET] > a[H_MAXBET]:
                    a[H_MAXBET] = a[b + S_RBET]
                if a[H_NBLINDS] == 0:
                    a[H_SB] = amt
                elif amt > a[H_BB]:
                    a[H_BB] = amt
                a[H_NBLINDS] += 1
            elif k == "board":
                a[H_STREET] += 1
                a[H_MAXBET] = 0
                a[H_RAISES] = 0
                a[H_LASTAI] = 0
                for s in range(MAXS):
                    a[HS + s * NS + S_RBET] = 0
            elif k == "show":
                s = _field(ev, "seat")
                cards = parse_cards(_field(ev, "cards"))
                if s is None or not 0 <= s < MAXS or len(cards) != 2:
                    continue
                pct = int(1000 * PCT[hand_class(cards[0], cards[1])])
                b = HS + int(s) * NS
                fl = a[b + S_FLAGS]
                if fl & F_SHOVED:
                    a[b + S_SH_SUM] += pct
                    a[b + S_SH_N] += 1
                if fl & F_CALLEDAI:
                    a[b + S_CA_SUM] += pct
                    a[b + S_CA_N] += 1
            elif k == "stack":
                s = _field(ev, "seat")
                if s is not None and 0 <= s < MAXS:
                    a[HS + int(s) * NS + S_STACK] = int(_field(ev, "amount") or 0)

    def _new_hand(self, n):
        a = self.a
        a[H_HAND] = n
        for i in (H_STREET, H_MAXBET, H_RAISES, H_LASTAI, H_PFRAISES, H_NBLINDS, H_NLIMP):
            a[i] = 0
        a[H_LASTRAISER] = -1
        a[H_PFAGG] = -1
        for s in range(MAXS):
            b = HS + s * NS
            a[b + S_FLAGS] = 0
            a[b + S_RBET] = 0
            a[b + S_START] = a[b + S_STACK]

    def _enter(self, b):
        a = self.a
        if not a[b + S_FLAGS] & F_IN:
            a[b + S_FLAGS] |= F_IN
            a[b + S_HANDS] += 1

    def _action(self, s, k, amt):
        a = self.a
        b = HS + s * NS
        self._enter(b)
        fl = a[b + S_FLAGS]
        facing = a[H_MAXBET] - a[b + S_RBET]
        facing_ai = a[H_LASTAI] and facing > 0
        if a[H_STREET] == 0:
            if a[H_RAISES] == 0:
                if k != "check" and not fl & F_OPENOPP:
                    fl |= F_OPENOPP
                    a[b + S_OPEN_OPP] += 1
                if k == "call":
                    a[H_NLIMP] += 1
            elif not fl & (F_FROPP | F_VPIP):
                fl |= F_FROPP
                a[b + S_FR_OPP] += 1
                if k == "fold":
                    a[b + S_FR_FOLD] += 1
            if k == "call" or k == "raise" or k == "bet":
                if not fl & F_VPIP:
                    fl |= F_VPIP
                    a[b + S_VPIP] += 1
            if k == "raise" or k == "bet":
                if not fl & F_PFR:
                    fl |= F_PFR
                    a[b + S_PFR] += 1
                if a[H_RAISES] == 0:
                    a[b + S_OPEN] += 1
        else:
            if k == "raise" or k == "bet":
                a[b + S_P_AGG] += 1
            elif k == "call":
                a[b + S_P_CALL] += 1
            elif k == "fold":
                a[b + S_P_FOLD] += 1
            else:
                a[b + S_P_CHECK] += 1
        if facing_ai:
            a[b + S_AI_OPP] += 1
            if k == "call":
                a[b + S_AI_CALL] += 1
                if a[H_STREET] == 0:
                    fl |= F_CALLEDAI
        if k == "call":
            a[b + S_STACK] -= amt
            a[b + S_RBET] += amt
        elif k == "raise" or k == "bet":
            a[b + S_STACK] -= amt - a[b + S_RBET]
            a[b + S_RBET] = amt
            if amt > a[H_MAXBET]:
                a[H_MAXBET] = amt
                a[H_RAISES] += 1
                a[H_LASTRAISER] = s
                a[H_LASTAI] = 1 if a[b + S_STACK] <= 0 else 0
                if a[H_STREET] == 0:
                    a[H_PFRAISES] += 1
                    a[H_PFAGG] = s
            if a[H_STREET] == 0 and a[b + S_STACK] <= 0 and not fl & F_SHOVED:
                fl |= F_SHOVED
                a[b + S_SHOVE] += 1
        elif k == "fold":
            fl |= F_FOLDED
        a[b + S_FLAGS] = fl

    # ------------------------------------------------------------ stats
    def _rate(self, s, num, den, prior):
        p, k = PRIOR[prior]
        if not 0 <= s < MAXS:
            return p
        b = HS + s * NS
        return (self.a[b + num] + p * k) / (self.a[b + den] + k)

    def hands(self, s):
        return self.a[HS + s * NS + S_HANDS] if 0 <= s < MAXS else 0

    def vpip(self, s):
        return self._rate(s, S_VPIP, S_HANDS, "vpip")

    def pfr(self, s):
        return self._rate(s, S_PFR, S_HANDS, "pfr")

    def open_rate(self, s):
        return self._rate(s, S_OPEN, S_OPEN_OPP, "open")

    def fold_to_raise(self, s):
        return self._rate(s, S_FR_FOLD, S_FR_OPP, "fold_to_raise")

    def call_ai(self, s):
        return self._rate(s, S_AI_CALL, S_AI_OPP, "call_ai")

    def shove_rate(self, s):
        return self._rate(s, S_SHOVE, S_HANDS, "shove")

    def aggression(self, s):
        """Share of postflop actions that are bets or raises."""
        p, k = PRIOR["agg"]
        if not 0 <= s < MAXS:
            return p
        b = HS + s * NS
        a = self.a
        n = a[b + S_P_AGG] + a[b + S_P_CALL] + a[b + S_P_CHECK] + a[b + S_P_FOLD]
        return (a[b + S_P_AGG] + p * k) / (n + k)

    def fold_to_bet(self, s):
        """Postflop folds per postflop fold/call/raise decision (a proxy for fold-to-bet)."""
        p, k = PRIOR["fold_to_raise"]
        p *= 0.65
        if not 0 <= s < MAXS:
            return p
        b = HS + s * NS
        a = self.a
        n = a[b + S_P_FOLD] + a[b + S_P_CALL] + a[b + S_P_AGG]
        return (a[b + S_P_FOLD] + p * k) / (n + k)

    def committed(self, stacks_now):
        """Chips put into this hand so far, from hand-start stacks minus current stacks."""
        a = self.a
        tot = 0
        for s, st in stacks_now.items():
            if 0 <= s < MAXS:
                d = a[HS + s * NS + S_START] - st
                if d > 0:
                    tot += d
        return tot

    def shown_shove_width(self, s):
        """Range width implied by shown shoving hands (mean percentile x2), or None."""
        if not 0 <= s < MAXS:
            return None
        b = HS + s * NS
        n = self.a[b + S_SH_N]
        if n < 2:
            return None
        return min(1.0, 2.0 * self.a[b + S_SH_SUM] / (1000.0 * n))

    @property
    def street(self):
        return self.a[H_STREET]

    @property
    def pf_raises(self):
        return self.a[H_PFRAISES]

    @property
    def pf_aggressor(self):
        return self.a[H_PFAGG]

    @property
    def limpers(self):
        return self.a[H_NLIMP]

    def hand_blinds(self):
        a = self.a
        return a[H_SB], a[H_BB], a[H_ANTE]
