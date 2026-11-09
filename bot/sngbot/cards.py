"""Cards, a fast 5-7 card hand evaluator, and the 169 starting-hand classes.

Cards are ints 0..51: rank * 4 + suit, with rank 0 = deuce .. 12 = ace.
Pure stdlib: about 5-10 microseconds per 7-card evaluation in CPython.
"""

RANKS = "23456789TJQKA"
SUITS = "cdhs"

CARD = {}
for _r, _rc in enumerate(RANKS):
    for _s, _sc in enumerate(SUITS):
        for _a in (_rc, _rc.lower()):
            for _b in (_sc, _sc.upper()):
                CARD[_a + _b] = _r * 4 + _s
for _s, _sc in enumerate(SUITS):
    CARD["10" + _sc] = 8 * 4 + _s


def card_str(c):
    return RANKS[c >> 2] + SUITS[c & 3]


def parse_cards(cards):
    """Strings like 'As' (or ints) -> ints. Hidden/unknown cards are skipped."""
    out = []
    if not cards:
        return out
    for c in cards:
        if isinstance(c, int):
            out.append(c)
            continue
        v = CARD.get(str(c).strip())
        if v is not None:
            out.append(v)
    return out


# ---------------------------------------------------------------- evaluator
HIGH, PAIR, TWO_PAIR, TRIPS, STRAIGHT, FLUSH, FULL_HOUSE, QUADS, STRAIGHT_FLUSH = range(9)
CAT_SHIFT = 20

_STRAIGHT_TOP = [-1] * 8192   # rank mask -> top rank of best straight, or -1
_TOP5 = [0] * 8192            # rank mask -> top five ranks packed as nibbles (left aligned)
_POP = [0] * 8192
for _m in range(8192):
    _top = -1
    for _t in range(12, 3, -1):
        _w = 0x1F << (_t - 4)
        if _m & _w == _w:
            _top = _t
            break
    if _top < 0 and _m & 0x100F == 0x100F:   # wheel A-2-3-4-5
        _top = 3
    _STRAIGHT_TOP[_m] = _top
    _v = 0
    _n = 0
    for _r in range(12, -1, -1):
        if _m >> _r & 1:
            _v = (_v << 4) | _r
            _n += 1
            if _n == 5:
                break
    _TOP5[_m] = _v << (4 * (5 - _n))
    _POP[_m] = bin(_m).count("1")


def evaluate(cards):
    """Best poker hand among 3-7 int cards. Higher is better; category = value >> 20."""
    sm = [0, 0, 0, 0]
    cnt = [0] * 13
    for c in cards:
        r = c >> 2
        cnt[r] += 1
        sm[c & 3] |= 1 << r
    for m in sm:
        if _POP[m] >= 5:
            t = _STRAIGHT_TOP[m]
            if t >= 0:
                return (STRAIGHT_FLUSH << 20) | (t << 16)
            return (FLUSH << 20) | _TOP5[m]
    mask = sm[0] | sm[1] | sm[2] | sm[3]
    if _POP[mask] == len(cards):          # all ranks distinct
        t = _STRAIGHT_TOP[mask]
        if t >= 0:
            return (STRAIGHT << 20) | (t << 16)
        return _TOP5[mask]
    quad = trip = trip2 = p1 = p2 = -1
    for r in range(12, -1, -1):
        n = cnt[r]
        if n < 2:
            continue
        if n == 4:
            if quad < 0:
                quad = r
        elif n == 3:
            if trip < 0:
                trip = r
            elif trip2 < 0:
                trip2 = r
        elif p1 < 0:
            p1 = r
        elif p2 < 0:
            p2 = r
    if quad >= 0:
        return (QUADS << 20) | (quad << 16) | ((_TOP5[mask & ~(1 << quad)] >> 16) << 12)
    if trip >= 0:
        pr = trip2 if trip2 > p1 else p1
        if pr >= 0:
            return (FULL_HOUSE << 20) | (trip << 16) | (pr << 12)
    t = _STRAIGHT_TOP[mask]
    if t >= 0:
        return (STRAIGHT << 20) | (t << 16)
    if trip >= 0:
        kk = _TOP5[mask & ~(1 << trip)]
        return (TRIPS << 20) | (trip << 16) | (kk >> 4 & 0xFF00)
    if p2 >= 0:
        kk = _TOP5[mask & ~(1 << p1) & ~(1 << p2)]
        return (TWO_PAIR << 20) | (p1 << 16) | (p2 << 12) | ((kk >> 16) << 8)
    kk = _TOP5[mask & ~(1 << p1)]
    return (PAIR << 20) | (p1 << 16) | (kk >> 4 & 0xFFF0)


def category(value):
    return value >> CAT_SHIFT


# ------------------------------------------------------- starting-hand classes
# 169 classes on a 13x13 grid: pairs on the diagonal, suited above it
# (row = high rank), offsuit below it (row = low rank).
def hand_class(c1, c2):
    r1, r2 = c1 >> 2, c2 >> 2
    if r1 < r2:
        r1, r2 = r2, r1
    if r1 == r2 or (c1 & 3) == (c2 & 3):
        return r1 * 13 + r2
    return r2 * 13 + r1


def class_name(k):
    row, col = divmod(k, 13)
    if row == col:
        return RANKS[row] * 2
    if row > col:
        return RANKS[row] + RANKS[col] + "s"
    return RANKS[col] + RANKS[row] + "o"


def class_combos(k):
    row, col = divmod(k, 13)
    return 6 if row == col else (4 if row > col else 12)


def class_cards(k):
    """All concrete (c1, c2) combos of a class."""
    row, col = divmod(k, 13)
    out = []
    if row == col:
        for s1 in range(4):
            for s2 in range(s1 + 1, 4):
                out.append((row * 4 + s1, row * 4 + s2))
    elif row > col:
        for s in range(4):
            out.append((row * 4 + s, col * 4 + s))
    else:
        for s1 in range(4):
            for s2 in range(4):
                if s1 != s2:
                    out.append((col * 4 + s1, row * 4 + s2))
    return out
