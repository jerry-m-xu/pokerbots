"""Sample legal runouts without auction dead cards, using the permitted eval7 library."""
import random
import time

import eval7

from .cards import card_str, hand_class
from .ranges import pct

CARDS = tuple(eval7.Card(card_str(card)) for card in range(52))
PERCENTILES = tuple(tuple(pct(hand_class(first, second)) if first != second else 1.0
                          for second in range(52)) for first in range(52))
eval7.evaluate(list(CARDS[:7]))


def estimate(view, tracker, deadline, prior, samples=48):
    known = set(view.hole + view.board + view.dead)
    deck = [card for card in range(52) if card not in known]
    opponents = view.opps
    if not opponents:
        return 1.0
    rng = random.Random(bytes(view.hole + view.board + view.dead) + str(view.hand_number).encode())
    widths = [max(.12, tracker.vpip(seat)) for seat in opponents]
    hero = [CARDS[card] for card in view.hole]
    board = [CARDS[card] for card in view.board]
    weight_sum = square_sum = share_sum = 0.0
    count = 0
    while count < samples and time.perf_counter_ns() < deadline:
        drawn = rng.sample(deck, 2 * len(opponents) + 5 - len(board))
        runout = board + [CARDS[card] for card in drawn[2 * len(opponents):]]
        mine = eval7.evaluate(hero + runout)
        best, ties, weight = mine, 1, 1.0
        for index, width in enumerate(widths):
            first, second = drawn[2 * index:2 * index + 2]
            value = eval7.evaluate([CARDS[first], CARDS[second]] + runout)
            if value > best:
                best, ties = value, 1
            elif value == best:
                ties += 1
            weight *= 1.0 if PERCENTILES[first][second] <= width else .15
        if mine == best:
            share_sum += weight / ties
        weight_sum += weight
        square_sum += weight * weight
        count += 1
    if not count:
        return prior
    effective = weight_sum * weight_sum / square_sum
    trust = effective / (effective + 12)
    return prior * (1 - trust) + share_sum / weight_sum * trust
