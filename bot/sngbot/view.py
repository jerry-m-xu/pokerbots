"""Normalize the SDK's state object into plain Python values.

Everything here reads the state by duck typing (attribute or dict key), so
small differences in the real kit's classes degrade gracefully. Assumptions
to verify against the kit on the day are marked VERIFY.
"""
from .cards import parse_cards

_MISSING = object()
DEFAULT_PAYOUTS = (50.0, 30.0, 20.0)


def g(o, name, default=None):
    if o is None:
        return default
    v = getattr(o, name, _MISSING)
    if v is _MISSING:
        if isinstance(o, dict):
            return o.get(name, default)
        return default
    return default if v is None else v


def kname(k):
    """'raise', ActionKind.RAISE, 'ActionKind.RAISE' -> 'raise'."""
    k = getattr(k, "value", k)
    return str(k).lower().rsplit(".", 1)[-1]


def _num(x, default=0):
    try:
        return int(x)
    except (TypeError, ValueError):
        return default


def parse_blinds(b):
    """VERIFY: shape of state.blinds / config.blinds entries. Returns (sb, bb, ante) or None."""
    if b is None:
        return None
    if isinstance(b, (int, float)):
        return (int(b) // 2, int(b), 0)
    if isinstance(b, (list, tuple)):
        nums = [int(x) for x in b if isinstance(x, (int, float))]
        if len(nums) >= 2:
            return (nums[0], nums[1], nums[2] if len(nums) > 2 else 0)
        return None
    sb = bb = None
    for n in ("small", "sb", "small_blind"):
        sb = g(b, n)
        if sb is not None:
            break
    for n in ("big", "bb", "big_blind"):
        bb = g(b, n)
        if bb is not None:
            break
    if bb is None:
        return None
    return (_num(sb, int(bb) // 2), _num(bb), _num(g(b, "ante", 0)))


def parse_payouts(p):
    if isinstance(p, dict):
        items = sorted((_num(k), float(v)) for k, v in p.items())
        return tuple(v for _, v in items) or DEFAULT_PAYOUTS
    if isinstance(p, (list, tuple)) and p:
        out = []
        for x in p:
            if isinstance(x, (int, float)):
                out.append(float(x))
            else:
                out.append(float(g(x, "points", g(x, "amount", 0))))
        return tuple(out)
    return DEFAULT_PAYOUTS


class View:
    """Everything the policy needs, as plain values. Seats are ints."""

    def __init__(self, state, tracker):
        cfg = g(state, "config")
        self.me = me = _num(g(state, "seat", g(cfg, "seat", 0)))
        self.hole = parse_cards(g(state, "cards"))
        self.board = parse_cards(g(state, "board"))
        auction = parse_cards(g(g(state, "variant", {}), "auction_cards", ()))
        self.dead = [card for card in auction if card not in self.board] if self.board else []
        self.street = len(self.board)            # 0 = preflop, 3 flop, 4 turn, 5 river

        stack, bet, status = {}, {}, {}
        for st in g(state, "seats", ()) or ():
            s = _num(g(st, "seat"), -1)
            if s < 0:
                continue
            stack[s] = _num(g(st, "stack"))
            bet[s] = _num(g(st, "bet"))
            status[s] = kname(g(st, "status", "active"))
        self.stack, self.bet, self.status = stack, bet, status
        stack.setdefault(me, 0)
        bet.setdefault(me, 0)
        status.setdefault(me, "active")

        # VERIFY: status strings are active / folded / all_in / busted.
        self.alive = sorted(s for s in stack if status[s] != "busted")
        if me not in self.alive:
            self.alive = sorted(self.alive + [me])
        self.in_hand = [s for s in self.alive if status[s] in ("active", "all_in", "allin")]
        if me not in self.in_hand:
            self.in_hand.append(me)
        self.opps = [s for s in self.in_hand if s != me]
        self.can_act = {s for s in self.in_hand if status[s] == "active" and stack[s] > 0}

        # blinds: state, then the config schedule, then this hand's blind events
        bl = parse_blinds(g(state, "blinds"))
        if bl is None:
            sched = g(cfg, "blinds")
            lvl = _num(g(state, "blind_level", 0))
            if isinstance(sched, (list, tuple)) and sched:
                bl = parse_blinds(sched[max(0, min(lvl, len(sched) - 1))])
        if bl is None or bl[1] <= 0:
            tsb, tbb, tante = tracker.hand_blinds()
            bl = (tsb, tbb, tante) if tbb > 0 else (10, 20, 0)
        self.sb, self.bb, self.ante = bl[0], max(1, bl[1]), bl[2]

        self.max_bet = max(bet.values()) if bet else 0
        tc = g(state, "to_call")
        self.to_call = _num(tc) if tc is not None else max(0, self.max_bet - bet[me])
        self.to_call = min(self.to_call, stack[me])

        # VERIFY: whether state.pot includes the current round's bets. The
        # tracker's committed-chips count settles it when it is consistent.
        raw = _num(g(state, "pot", 0))
        bets = sum(bet.values())
        committed = tracker.committed(stack)
        if committed >= bets and committed > 0 and (abs(committed - raw) <= 2 or abs(committed - raw - bets) <= 2):
            self.pot = committed
        else:
            self.pot = raw if raw >= bets else raw + bets

        legal = {}
        for la in g(state, "legal_actions", ()) or ():
            legal[kname(g(la, "kind"))] = (_num(g(la, "min_amount", 0)), _num(g(la, "max_amount", 0)), la)
        self.legal = legal

        self.payouts = parse_payouts(g(cfg, "payouts"))
        self.hand_number = _num(g(state, "hand_number", 0))
        self.hand_cap = _num(g(cfg, "hand_cap", 0))
        self.players_left = _num(g(state, "players_remaining", len(self.alive))) or len(self.alive)
        self.time_bank_ms = float(g(state, "time_bank_ms", 0) or 0)

        # positions. VERIFY: seat ids increase clockwise and the button posts SB heads-up.
        alive = self.alive
        btn = _num(g(state, "button", alive[0]), alive[0])
        after = [s for s in alive if s > btn] + [s for s in alive if s <= btn]
        if len(alive) == 2:
            b = btn if btn in alive else after[-1]
            o = alive[0] if alive[1] == b else alive[1]
            self.pre_order = [b, o]
            self.post_order = [o, b]
            self.sb_seat, self.bb_seat = b, o
        else:
            self.post_order = after                 # SB, BB, ..., BTN
            self.pre_order = after[2:] + after[:2]  # UTG ... BTN, SB, BB
            self.sb_seat, self.bb_seat = after[0], after[1]
        self.button = self.post_order[-1]

    # ------------------------------------------------------------ helpers
    def behind(self):
        """Seats still able to act that act after me this street."""
        order = self.pre_order if self.street == 0 else self.post_order
        if self.me not in order:
            return []
        i = order.index(self.me)
        return [s for s in order[i + 1:] if s in self.can_act]

    def total(self, s):
        """Chips a seat had at the start of this betting round."""
        return self.stack.get(s, 0) + self.bet.get(s, 0)

    def in_position_vs(self, s):
        po = self.post_order
        return s in po and self.me in po and po.index(self.me) > po.index(s)
