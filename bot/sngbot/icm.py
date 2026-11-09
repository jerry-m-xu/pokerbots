"""ICM (Malmuth-Harville) for one player, plus outcome valuation.

Only the hero's equity is computed, which keeps an 8-player, 3-payout
evaluation to ~50 inner iterations (~10 us). Payouts deeper than 4 places
are ignored (the 4th+ places pay 0 by default anyway).
"""


def icm_me(stacks, i, payouts):
    """Expected payout of player i given positive stacks (survivors only)."""
    n = len(stacks)
    k = min(len(payouts), n, 4)
    total = float(sum(stacks))
    s = stacks[i]
    if s <= 0 or total <= 0:
        return 0.0
    if n == 1:
        return payouts[0] if payouts else 0.0
    ev = payouts[0] * s / total if k >= 1 else 0.0
    if k < 2:
        return ev
    p1, p2 = payouts[1], (payouts[2] if k >= 3 else 0.0)
    p3 = payouts[3] if k >= 4 else 0.0
    for a in range(n):
        if a == i:
            continue
        sa = stacks[a]
        ta = total - sa
        pa = sa / total
        ev += p1 * pa * s / ta
        if k < 3:
            continue
        for b in range(n):
            if b == i or b == a:
                continue
            sb = stacks[b]
            tb = ta - sb
            pb = pa * sb / ta
            ev += p2 * pb * s / tb
            if k < 4:
                continue
            for c in range(n):
                if c == i or c == a or c == b:
                    continue
                sc = stacks[c]
                ev += p3 * pb * sc / tb * s / (tb - sc)
    return ev


def value(final, me, payouts):
    """Hero's points for a dict seat -> chips after a hand.

    A hero who busts takes the place just below every survivor. Opponents who
    bust are simply dropped, which hands their place's payout to nobody here.
    """
    mine = final.get(me, 0)
    alive = [s for s, c in final.items() if c > 0]
    if mine <= 0:
        place = len(alive)
        return float(payouts[place]) if place < len(payouts) else 0.0
    stacks = [final[s] for s in alive]
    return icm_me(stacks, alive.index(me), payouts)
