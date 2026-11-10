"""Budgeted sealed bids over the ten possible flops."""
from itertools import combinations

from .cards import parse_cards
from .policy import strength

TRIPLES = tuple(combinations(range(5), 3))


def bids(state, multiplier=1.0):
    legal = state.can("bid")
    balance = max(0, legal.max_amount)
    cards = parse_cards(state.variant.get("auction_cards", ()))
    hole = parse_cards(state.cards)
    if not balance or len(cards) != 5 or len(hole) != 2:
        return (0, 0, 0, 0, 0)
    values = []
    for triple in TRIPLES:
        made, draw = strength(hole, [cards[index] for index in triple])
        values.append(made + (1 - made) * draw)
    best = max(range(10), key=lambda index: values[index])
    advantage = values[best] - sum(values) / 10
    if advantage < .04 or values[best] < .32:
        return (0, 0, 0, 0, 0)
    remaining = max(1, state.config.hand_cap - state.hand_number + 1)
    horizon = min(remaining, max(12, 70 - state.hand_number // 2))
    big_blind = state.blinds.big_blind
    importance = min(3.0, max(.6, state.pot / max(1, big_blind * 8)))
    budget = min(balance, int(balance / horizon * importance * (1 + 5 * advantage) * multiplier))
    if best == 0:
        budget //= 3
    if budget < 3:
        return (0, 0, 0, 0, 0)
    selected = TRIPLES[best]
    amounts = [0] * 5
    for position, index in enumerate(selected):
        amounts[index] = budget // 3 + (position < budget % 3)
    return tuple(int(amount) for amount in amounts)
