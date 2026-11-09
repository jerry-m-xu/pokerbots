"""Compare the submission evaluator with the independent PokerKit evaluator."""
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'bot'))
from pokerkit import Card, StandardHighHand
from sngbot.cards import card_str, evaluate, parse_cards
from evaluate_position import evaluate_position


class EvaluatorTests(unittest.TestCase):
    def test_random_showdowns(self):
        rng = random.Random(2026)
        for size in (5, 6, 7):
            for _ in range(500):
                cards = rng.sample(range(52), size + 2)
                left, right = cards[:size], cards[2:]
                ours = (evaluate(left) > evaluate(right)) - (evaluate(left) < evaluate(right))
                first = StandardHighHand.from_game(''.join(map(card_str, left)))
                second = StandardHighHand.from_game(''.join(map(card_str, right)))
                self.assertEqual(ours, (first > second) - (first < second), cards)

    def test_wheel_and_two_trips(self):
        for stronger, weaker in [('2s3s4s5s6s', 'As2s3s4s5s'), ('AhAdAcKhKdKc2s', 'QhQdQcJhJdJc2s')]:
            self.assertGreater(evaluate(parse_cards([stronger[index:index+2] for index in range(0, len(stronger), 2)])),
                               evaluate(parse_cards([weaker[index:index+2] for index in range(0, len(weaker), 2)])))

    def test_shared_royal_flush(self):
        result = evaluate_position(list(Card.parse('2c3d')), list(Card.parse('AsKsQsJsTs')), 1)
        self.assertEqual(result['equity'], .5)
        self.assertEqual(result['samples'], 990)
        self.assertTrue(result['exact'])

    def test_duplicate_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_position(list(Card.parse('AsAs')), [], 1)


if __name__ == '__main__':
    unittest.main()
