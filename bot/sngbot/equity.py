"""Time-bounded, blocker-aware equity estimates for postflop decisions."""
import random
import time

from .cards import evaluate, hand_class
from .ranges import pct


def estimate(hole, board, widths, deadline, prior):
    known = set(hole + board)
    deck = [card for card in range(52) if card not in known]
    opponents = len(widths)
    count = weight_sum = square_sum = share_sum = 0.0
    while count < 32 and time.perf_counter_ns() < deadline:
        drawn = random.sample(deck, 2 * opponents + 5 - len(board))
        runout = board + drawn[2 * opponents:]
        hero = evaluate(hole + runout)
        best = hero
        ties = 1
        weight = 1.0
        for seat, width in enumerate(widths):
            cards = drawn[2 * seat:2 * seat + 2]
            rank = evaluate(cards + runout)
            if rank > best:
                best, ties = rank, 1
            elif rank == best:
                ties += 1
            weight *= 1.0 if pct(hand_class(*cards)) <= width else .05
        share_sum += weight / ties if hero == best else 0.0
        weight_sum += weight
        square_sum += weight * weight
        count += 1
    if weight_sum == 0:
        return prior
    effective_samples = weight_sum * weight_sum / square_sum
    trust = effective_samples / (effective_samples + 32)
    return prior * (1 - trust) + share_sum / weight_sum * trust
