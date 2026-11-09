"""Decision policy.

  preflop   deep: position-based opening ranges widened against folders.
            short (<= push_bb) or facing a raise (<= reshove_bb): shove/fold by ICM EV.
            facing an all-in or a stack-committing bet: call/fold by ICM EV.
  postflop  heuristic made-hand + draw strength, discounted by the bettor's
            size and observed aggression; commits go through the same ICM call.

Opponent ranges are "top X% of hands" with X from the tracker's per-seat
frequencies, so one equity table (ranges.py) serves every all-in decision.
Decisions are tuples: ("fold",) ("check",) ("call",) ("raise", total) ("allin",).
"""
import time

from . import icm
from .equity import estimate
from .cards import (FLUSH, FULL_HOUSE, HIGH, PAIR, QUADS, STRAIGHT, TRIPS,
                    TWO_PAIR, _STRAIGHT_TOP, evaluate, hand_class)
from .ranges import eq_vs_random, eq_vs_range
from .ranges import pct as hand_pct

FOLD, CHECK, CALL, ALLIN = ("fold",), ("check",), ("call",), ("allin",)

P_DEFAULT = {
    # preflop, deep stacks: open the top X% by number of players still to act
    "open": (0.50, 0.50, 0.42, 0.28, 0.21, 0.16, 0.13, 0.11, 0.10, 0.10),
    "steal_k": 0.95, "steal_c": 0.10,   # threshold >= steal_k * P(all fold) - steal_c
    "iso_mult": 0.6,                    # tighten opens when limpers are in
    "open_bb": 2.3,
    "push_bb": 13.0,                    # first in at or below this: shove or fold
    "reshove_bb": 22.0,                 # facing one raise at or below this: reshove or fold
    "commit_frac": 0.40,                # betting this share of the stack = all-in decision
    "icm_margin": 0.0,                  # points of EV an all-in must beat folding by
    "threebet_pct": 0.035, "threebet_eq": 0.62, "3b_ip": 3.0, "3b_oop": 3.6,
    "call_eq": 0.47, "ip_bonus": 0.03, "setmine_mult": 15.0,
    "flat_edge": 0.08, "flat_max_frac": 0.15,
    "raiser_call_frac": 0.5,            # raiser calls a reshove with this share of its range
    # postflop
    "multi_exp": 0.6, "value_e": 0.66, "value_multi": 0.06, "value_size": 0.65,
    "cbet_size": 0.5, "cbet_fold_min": 0.40, "semibluff_draw": 0.30, "semibluff_size": 0.6,
    "bet_disc": 0.12, "raise_e": 0.85, "call_margin": 0.02,
    "implied_frac": 0.12, "implied_bonus": 0.06,
    "budget_us": 550,                   # skip ICM loops past this many microseconds
    "sample_equity": False,
}


def decide(v, T, P, deadline_ns):
    if len(v.hole) != 2:            # VERIFY: a variant with other hole-card counts needs its own path
        return CHECK if "check" in v.legal else FOLD
    if v.street == 0:
        return preflop(v, T, P, deadline_ns)
    return postflop(v, T, P, deadline_ns)


def _fold(v):
    return CHECK if "check" in v.legal else FOLD


# ------------------------------------------------------------------ ICM EVs
def _base(v):
    return {s: v.stack[s] for s in v.alive}


def ev_passive(v, winner):
    """Fold (or check-fold): the pot goes to `winner`."""
    f = _base(v)
    if winner is not None and winner in f and winner != v.me:
        f[winner] += v.pot
    return icm.value(f, v.me, v.payouts)


def ev_check(v, cls):
    """Rough value of checking through: hero takes an equity share of the pot."""
    f = _base(v)
    share = eq_vs_random(cls, max(1, len(v.opps)))
    f[v.me] += int(v.pot * share)
    if v.opps:
        f[v.opps[0]] += int(v.pot * (1 - share))
    return icm.value(f, v.me, v.payouts)


def ev_call_allin(v, opp, eq):
    """(EV call, EV fold) when calling resolves the hand against `opp` at equity `eq`."""
    me = v.me
    call = min(v.to_call, v.stack[me])
    excess = max(0, v.bet.get(opp, 0) - (v.bet[me] + call))
    pot_c = v.pot + call - excess
    base = _base(v)
    fold = dict(base)
    if opp in fold:
        fold[opp] += v.pot
    win = dict(base)
    win[me] = base[me] - call + pot_c
    win[opp] = base.get(opp, 0) + excess
    lose = dict(base)
    lose[me] = base[me] - call
    lose[opp] = base.get(opp, 0) + excess + pot_c
    pay = v.payouts
    ev_c = eq * icm.value(win, me, pay) + (1 - eq) * icm.value(lose, me, pay)
    return ev_c, icm.value(fold, me, pay)


def ev_shove(v, eq_fn, callers):
    """EV of shoving; callers = [(seat, calling-range width)] in calling order.

    Each caller in turn calls with probability = its range width (given the
    earlier ones folded); only one caller is modelled. eq_fn(q) gives hero's
    equity against a top-q calling range.
    """
    me = v.me
    pay = v.payouts
    behind, mybet = v.stack[me], v.bet[me]
    shove_to = mybet + behind
    base = _base(v)
    ev = 0.0
    reach = 1.0
    for s, q in callers:
        if q <= 0.0:
            continue
        e = eq_fn(q)
        matched = min(shove_to, v.stack[s] + v.bet[s])
        mine = max(0, matched - mybet)
        theirs = max(0, matched - v.bet[s])
        pot_f = v.pot + mine + theirs
        win = dict(base)
        win[me] = behind - mine + pot_f
        win[s] = v.stack[s] - theirs
        lose = dict(base)
        lose[me] = behind - mine
        lose[s] = v.stack[s] - theirs + pot_f
        ev += reach * q * (e * icm.value(win, me, pay) + (1 - e) * icm.value(lose, me, pay))
        reach *= 1.0 - q
    steal = dict(base)
    steal[me] = behind + v.pot
    return ev + reach * icm.value(steal, me, pay)


# ------------------------------------------------------------ range estimates
def _call_q(v, T, s):
    """Width of the range seat s calls an all-in with."""
    q = T.call_ai(s)
    tot = v.total(s)
    if tot <= 4 * v.bb or v.bet.get(s, 0) >= 0.5 * tot:
        q = max(q, 0.5)                 # short or pot-committed
    elif s == v.bb_seat and v.street == 0:
        q = max(q, 0.3)
    return min(1.0, q)


def _shove_range(v, T, s):
    """Width of the range seat s shoves with, from stack depth and observed shoves."""
    depth = v.total(s) / v.bb
    prior = 0.55 if depth <= 4 else 0.35 if depth <= 8 else 0.22 if depth <= 15 else 0.10
    x = max(T.shove_rate(s) * 1.3, prior)
    shown = T.shown_shove_width(s)
    if shown is not None:
        x = 0.5 * x + 0.5 * shown
    if T.pf_raises >= 2:
        x *= 0.6                        # a reshove over a raise is narrower
    return min(1.0, max(0.02, x))


def _raise_range(T, s):
    if T.pf_raises <= 1:
        return min(1.0, max(0.03, T.open_rate(s)))
    return min(1.0, max(0.02, T.pfr(s) * 0.35))


def _cheap_shove(hp, eff_bb):
    """Fallback push chart when out of time budget."""
    return hp <= min(0.75, 1.4 / max(eff_bb, 1.0))


# --------------------------------------------------------------------- preflop
def preflop(v, T, P, deadline):
    me, bb = v.me, v.bb
    cls = hand_class(v.hole[0], v.hole[1])
    hp = hand_pct(cls)
    my_total = v.total(me)
    opp_max = max((v.total(s) for s in v.opps), default=my_total)
    eff_bb = min(my_total, opp_max) / bb

    if v.max_bet <= bb:
        return _unopened(v, T, P, cls, hp, my_total, eff_bb, deadline)

    agg = max(v.opps, key=lambda s: (v.bet[s], s == T.pf_aggressor)) if v.opps else None
    if agg is None:
        return _fold(v)
    agg_allin = v.stack.get(agg, 0) == 0
    if agg_allin or v.to_call >= P["commit_frac"] * v.stack[me] or v.to_call >= v.stack[me]:
        return _facing_allin(v, T, P, cls, agg, agg_allin, deadline)
    return _facing_raise(v, T, P, cls, hp, agg, my_total, deadline)


def _unopened(v, T, P, cls, hp, my_total, eff_bb, deadline):
    me, bb = v.me, v.bb
    behind = v.behind()
    limpers = [s for s in v.opps if v.bet[s] >= bb and s != v.bb_seat]
    if eff_bb <= P["push_bb"]:
        if hp <= 0.03:
            return ALLIN
        if time.perf_counter_ns() > deadline:
            return ALLIN if _cheap_shove(hp, eff_bb) else _fold(v)
        callers = [(s, _call_q(v, T, s)) for s in behind]
        callers += [(s, _call_q(v, T, s)) for s in v.opps if s in v.can_act and s not in behind]
        ev_s = ev_shove(v, lambda q: eq_vs_range(cls, q), callers)
        if v.to_call == 0:
            ev_alt = ev_check(v, cls)
        else:
            ev_alt = ev_passive(v, v.bb_seat)
        return ALLIN if ev_s > ev_alt + P["icm_margin"] else _fold(v)

    opens = P["open"]
    thr = opens[min(len(behind), len(opens) - 1)]
    p_fold = 1.0
    for s in behind:
        p_fold *= T.fold_to_raise(s)
    thr = max(thr, P["steal_k"] * p_fold - P["steal_c"])
    if limpers:
        thr *= P["iso_mult"]
    if hp <= thr:
        size = int(P["open_bb"] * bb + bb * len(limpers))
        if size >= P["commit_frac"] * my_total:
            return ALLIN
        return ("raise", size)
    return _fold(v)


def _facing_raise(v, T, P, cls, hp, agg, my_total, deadline):
    me, bb = v.me, v.bb
    x_r = _raise_range(T, agg)
    e = eq_vs_range(cls, x_r)
    eff_bb = min(my_total, v.total(agg)) / bb
    odds = v.to_call / float(v.pot + v.to_call)

    if eff_bb <= P["reshove_bb"]:
        if time.perf_counter_ns() <= deadline:
            q_r = min(x_r, max(T.call_ai(agg), P["raiser_call_frac"] * x_r))
            callers = [(agg, q_r)] + [(s, _call_q(v, T, s)) for s in v.behind() if s != agg]
            ev_s = ev_shove(v, lambda q: eq_vs_range(cls, q), callers)
            if ev_s > ev_passive(v, agg) + P["icm_margin"]:
                return ALLIN
        elif hp <= 0.6 * x_r:
            return ALLIN
        if e >= odds + P["flat_edge"] and v.to_call <= P["flat_max_frac"] * v.stack[me]:
            return CALL
        return _fold(v)

    ip = v.in_position_vs(agg)
    if hp <= P["threebet_pct"] or e >= P["threebet_eq"]:
        size = int(v.max_bet * (P["3b_ip"] if ip else P["3b_oop"]))
        if size >= P["commit_frac"] * my_total:
            return ALLIN
        return ("raise", size)
    pair = cls // 13 == cls % 13
    implied = pair and min(my_total, v.total(agg)) >= P["setmine_mult"] * v.to_call
    if e > odds and (e >= P["call_eq"] - (P["ip_bonus"] if ip else 0.0) or implied):
        return CALL
    return _fold(v)


def _facing_allin(v, T, P, cls, agg, agg_allin, deadline):
    me = v.me
    x_a = _shove_range(v, T, agg) if agg_allin else _raise_range(T, agg) * 0.7
    e = eq_vs_range(cls, x_a)
    for s in v.opps:                     # players already in the pot shrink our equity
        if s != agg and v.bet[s] > v.bb:
            e *= eq_vs_range(cls, _call_q(v, T, s))
    ev_c, ev_f = ev_call_allin(v, agg, e)
    best, choice = ev_f, _fold(v)
    if ev_c > best + P["icm_margin"]:
        best, choice = ev_c, CALL
    if not agg_allin and v.stack[me] > v.to_call and time.perf_counter_ns() <= deadline:
        q = min(x_a, max(T.call_ai(agg), 0.6 * x_a))
        ev_s = ev_shove(v, lambda qq: eq_vs_range(cls, qq), [(agg, q)])
        if ev_s > best + P["icm_margin"]:
            choice = ALLIN
    return choice


# -------------------------------------------------------------------- postflop
def _texture(board):
    """(most cards of one suit, most distinct ranks inside any 5-rank straight window)."""
    suits = [0, 0, 0, 0]
    mask = 0
    for c in board:
        suits[c & 3] += 1
        mask |= 1 << (c >> 2)
    m = (mask << 1) | (mask >> 12 & 1)  # bit 0 = ace playing low
    straight_n = 0
    for lo in range(10):
        w = bin((m >> lo) & 0x1F).count("1")
        if w > straight_n:
            straight_n = w
    return max(suits), straight_n


def strength(hole, board):
    """(made, draw): made ~ P(best now vs one opponent), draw ~ P(improve to likely best)."""
    full = evaluate(hole + board)
    cat = full >> 20
    bv = evaluate(board)
    bcat = bv >> 20
    br = sorted((c >> 2 for c in board), reverse=True)
    h1, h2 = sorted((hole[0] >> 2, hole[1] >> 2), reverse=True)
    flush_n, straight_n = _texture(board)
    paired_board = bcat >= PAIR

    if cat >= QUADS:
        made = 0.99 if cat > bcat else 0.5
    elif cat == FULL_HOUSE:
        if bcat <= PAIR:
            made = 0.96
        elif bcat == TWO_PAIR:
            made = 0.90
        elif bcat == TRIPS:
            made = 0.85 if h1 >= 10 else 0.75
        else:
            made = 0.7 if full > bv else 0.3
    elif cat == FLUSH:
        if bcat >= FLUSH:
            made = 0.75 if full > bv else 0.25
        else:
            fs = max(range(4), key=lambda s: sum(1 for c in board + hole if c & 3 == s))
            top = max((c >> 2 for c in hole if c & 3 == fs), default=0)
            made = 0.95 if top == 12 else 0.9 if top >= 10 else 0.82
            if paired_board:
                made *= 0.92
    elif cat == STRAIGHT:
        if bcat == STRAIGHT:
            made = 0.6 if full > bv else 0.25
        else:
            made = 0.85 if flush_n < 3 else 0.7 if flush_n == 3 else 0.5
            if paired_board:
                made *= 0.92
    else:
        if cat == TRIPS:
            if h1 == h2:
                made = 0.92
            elif bcat == TRIPS:
                made = 0.30 if h1 >= 11 else 0.2
            else:
                kick = h2 if h1 in br else h1
                made = 0.85 if kick >= 10 else 0.78
        elif cat == TWO_PAIR:
            if bcat == TWO_PAIR:
                made = 0.25
            elif h1 == h2:
                made = 0.72 if h1 > br[0] else 0.45
            elif bcat == PAIR:
                pr = h1 if h1 in br else h2
                made = _pair_value(pr, h2 if pr == h1 else h1, br) + 0.05
            else:
                made = 0.88 if (h1 == br[0] and h2 == br[1]) else 0.82
        elif cat == PAIR and bcat == HIGH:
            if h1 == h2:
                made = min(0.85, 0.80 + 0.01 * (h1 - 10)) if h1 > br[0] else (0.52 if h1 > br[1] else 0.35)
            else:
                pr = h1 if h1 in br else h2
                made = _pair_value(pr, h2 if pr == h1 else h1, br)
        else:                            # no pair of our own
            made = 0.12 + 0.05 * (h1 > br[0]) + 0.04 * (h2 > br[0]) + 0.04 * (h1 == 12)
        if flush_n == 3:
            made *= 0.88
        elif flush_n >= 4:
            made *= 0.65
        if straight_n == 4:
            made *= 0.8
        elif straight_n == 3:
            made *= 0.93

    draw = 0.0
    if len(board) < 5 and cat < STRAIGHT:
        allc = hole + board
        outs = 0
        fd = False
        for su in {hole[0] & 3, hole[1] & 3}:
            if sum(1 for c in allc if c & 3 == su) == 4:
                fd = True
        if fd:
            outs += 9
        mask = 0
        bmask = 0
        for c in allc:
            mask |= 1 << (c >> 2)
        for c in board:
            bmask |= 1 << (c >> 2)
        srank = 0
        for r in range(13):
            if not mask >> r & 1 and _STRAIGHT_TOP[mask | 1 << r] >= 0 and _STRAIGHT_TOP[bmask | 1 << r] < 0:
                srank += 1
        outs += min(8, 4 * srank) - (2 if fd and srank else 0)
        if outs:
            p = outs / 47.0
            draw = 0.85 * ((1 - (1 - p) * (1 - outs / 46.0)) if len(board) == 3 else outs / 46.0)
    return made, draw



def _pair_value(pr, kicker, br):
    if pr == br[0]:
        return 0.66 + 0.01 * kicker
    if len(br) > 1 and pr == br[1]:
        return 0.50 + 0.005 * kicker
    return 0.38


def _bet(v, P, amount):
    me = v.me
    amount = max(int(amount), v.bb)
    if amount >= P["commit_frac"] * v.stack[me]:
        return ALLIN
    return ("raise", v.bet[me] + amount)


def postflop(v, T, P, deadline):
    me = v.me
    made, draw = strength(v.hole, v.board)
    n = max(1, len(v.opps))
    e_made = made ** (1.0 + P["multi_exp"] * (n - 1))
    e = e_made + (1.0 - e_made) * draw
    if P.get("sample_equity"):
        widths = [max(.15, T.vpip(seat)) for seat in v.opps]
        e = estimate(v.hole, v.board, widths, deadline - 100_000, e)
        e_made = max(0.0, (e - draw) / max(.01, 1 - draw))
    pot = v.pot

    if v.to_call == 0:
        if e >= P["value_e"] + P["value_multi"] * (n - 1):
            return _bet(v, P, P["value_size"] * pot)
        if n == 1 and v.street == 3 and T.pf_aggressor == me:
            opp = v.opps[0]
            if (made < 0.35 or draw >= 0.15) and T.fold_to_bet(opp) >= P["cbet_fold_min"]:
                return _bet(v, P, P["cbet_size"] * pot)
        if draw >= P["semibluff_draw"] and n <= 2:
            return _bet(v, P, P["semibluff_size"] * pot)
        return CHECK

    agg = max(v.opps, key=lambda s: v.bet[s]) if v.opps else None
    ratio = v.to_call / float(max(1, pot - v.to_call))
    disc = P["bet_disc"] * min(ratio, 1.5)
    af = T.aggression(agg) if agg is not None else 0.35
    if af < 0.2:
        disc *= 1.4
    elif af > 0.5:
        disc *= 0.6
    if v.street == 5:
        disc *= 1.15
    e_adj = max(0.0, e_made - disc) + (1.0 - e_made) * draw
    odds = v.to_call / float(pot + v.to_call)
    my_behind = v.stack[me]
    agg_allin = agg is not None and v.stack.get(agg, 0) == 0

    if agg is not None and (agg_allin or v.to_call >= P["commit_frac"] * my_behind):
        if e_adj >= P["raise_e"] and not agg_allin and "raise" in v.legal:
            return ALLIN
        ev_c, ev_f = ev_call_allin(v, agg, e_adj)
        return CALL if ev_c > ev_f + P["icm_margin"] else FOLD
    if e_adj >= P["raise_e"] and ("raise" in v.legal or "bet" in v.legal):
        size = int(v.max_bet * 3)
        if size - v.bet[me] >= P["commit_frac"] * my_behind:
            return ALLIN
        return ("raise", size)
    if e_adj >= odds + P["call_margin"]:
        return CALL
    eff = min(my_behind, max((v.stack[s] for s in v.opps), default=0))
    if draw > 0 and v.street < 5 and v.to_call <= P["implied_frac"] * eff and draw >= odds - P["implied_bonus"]:
        return CALL
    return FOLD
