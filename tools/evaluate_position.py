"""PokerKit showdown-equity analysis for a Hold'em position."""
import argparse
import itertools
import json
import math
import random

from pokerkit import Card, StandardHighHand


def evaluate_position(hero, board, opponents, samples=5000, seed=1):
    if len(hero) != 2 or len(board) not in (0, 3, 4, 5):
        raise ValueError("Use two hole cards and zero, three, four, or five board cards")
    if not 1 <= opponents <= 7 or samples < 1:
        raise ValueError("Use 1–7 opponents and a positive sample count")
    known = hero + board
    if len(set(known)) != len(known):
        raise ValueError("Duplicate cards")
    deck = [card for card in Card.parse(''.join(rank + suit for rank in '23456789TJQKA' for suit in 'cdhs')) if card not in known]
    rng = random.Random(seed)
    exact = len(board) == 5 and opponents == 1
    deals = itertools.combinations(deck, 2) if exact else (rng.sample(deck, 2 * opponents + 5 - len(board)) for _ in range(samples))
    total = wins = ties = 0
    shares = squares = 0.0
    for deal in deals:
        runout = board + list(deal[2 * opponents:])
        hands = [StandardHighHand.from_game(hero, runout)]
        hands.extend(StandardHighHand.from_game(deal[2 * seat:2 * seat + 2], runout) for seat in range(opponents))
        best = max(hands)
        winners = sum(hand == best for hand in hands)
        share = 1 / winners if hands[0] == best else 0.0
        wins += share == 1
        ties += 0 < share < 1
        shares += share
        squares += share * share
        total += 1
    equity = shares / total
    error = 0 if exact else math.sqrt(max(0, (squares - total * equity ** 2) / max(1, total - 1)) / total)
    return dict(equity=equity, win_probability=wins / total, tie_probability=ties / total,
                samples=total, standard_error=error, exact=exact, opponent_model="uniform random legal hands")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hero', required=True, help='Example: AsKh')
    parser.add_argument('--board', default='', help='Example: QsJh2c')
    parser.add_argument('--opponents', type=int, default=1)
    parser.add_argument('--samples', type=int, default=5000)
    parser.add_argument('--seed', type=int, default=1)
    args = parser.parse_args()
    result = evaluate_position(list(Card.parse(args.hero)), list(Card.parse(args.board)), args.opponents, args.samples, args.seed)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
