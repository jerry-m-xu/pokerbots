"""Regression checks against the official Flop Auction Hold'em SDK."""
from dataclasses import replace
import os
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'bot'))
os.environ['SNGBOT_RAISE'] = '1'
from agent import Agent
from sngbot.auction import bids
from sngbot.cards import parse_cards
from sngbot.fast_equity import estimate, CARDS
from sngbot.tracker import Tracker
from sngbot.view import View
from poker_agent_sdk import Action
from poker_agent_protocol.game import LegalAction, is_legal
from poker_engine.table import SitAndGo, TableRules
from poker_engine.variant import load_variant


def initial(players=8):
    return SitAndGo(rules=TableRules(players=players), variant=load_variant('flop_auction_holdem'), table_id='test', seed='test')


def auction_state():
    table = initial()
    while (state := table.decision()).phase != 'auction':
        table.apply(Action.call() if state.can('call') else Action.check())
    return state


class OfficialTests(unittest.TestCase):
    def test_full_payout_structure(self):
        from sngbot.icm import icm_me
        self.assertAlmostEqual(icm_me([100] * 5, 0, [40, 25, 20, 10, 5]), 20)

    def test_auction_budget_and_selected_cards(self):
        state = replace(auction_state(), cards=('As', 'Ah'), variant={'auction_cards': ['2c', '7d', '9h', 'Ac', 'Ad']})
        for balance in (0, 1, 2, 3, 10, 1000):
            current = replace(state, legal_actions=(LegalAction('bid', 0, balance),))
            action, _ = Agent().act(current, b'')
            self.assertEqual(action.kind, 'bid')
            self.assertEqual(action.amount, 0)
            self.assertEqual(len(action.cards), 5)
            self.assertTrue(all(type(value) is int and value >= 0 for value in action.cards))
            self.assertLessEqual(sum(action.cards), balance)
        amounts = bids(replace(state, legal_actions=(LegalAction('bid', 0, 1000),)))
        self.assertGreater(amounts[3], 0)
        self.assertGreater(amounts[4], 0)

    def test_dead_cards_not_sampled(self):
        state = replace(auction_state(), phase='betting', cards=('Qs', 'Qh'), board=('2c', '7d', '9h'),
                        variant={'auction_cards': ['2c', '7d', '9h', 'Ac', 'Ad']})
        tracker = Tracker.load(b'', 2000)
        view = View(state, tracker)
        self.assertEqual(set(view.dead), set(parse_cards(['Ac', 'Ad'])))
        import eval7
        real_evaluate = eval7.evaluate
        dead = {CARDS[index] for index in view.dead}

        def checked(cards):
            self.assertFalse(dead.intersection(cards))
            self.assertEqual(len(set(cards)), len(cards))
            return real_evaluate(cards)

        with patch('sngbot.fast_equity.eval7.evaluate', checked):
            value = estimate(view, tracker, time.perf_counter_ns() + 1_000_000_000, .5)
        self.assertTrue(0 <= value <= 1)

    def test_all_in_player_remains_opponent(self):
        state = initial().decision()
        other = next(seat for seat in state.seats if seat.seat != state.seat)
        seats = tuple(replace(seat, stack=0, bet=0, status='all_in') if seat == other else seat for seat in state.seats)
        view = View(replace(state, seats=seats), Tracker.load(b'', 2000))
        self.assertIn(other.seat, view.opps)

    def test_real_states_stateless_and_memory_limits(self):
        for players in (2, 8, 10):
            table = initial(players)
            memory = [b''] * players
            count = 0
            while (state := table.decision()) is not None and count < 500:
                memo = memory[state.seat]
                if count % 23 == 0:
                    memo = b'invalid memory'
                action, following = Agent().act(state, memo)
                self.assertTrue(is_legal(action, state.legal_actions))
                self.assertLessEqual(len(following), state.config.memory_bytes)
                self.assertTrue(table.apply(action))
                memory[state.seat] = following
                count += 1

    def test_tiny_memory_limit(self):
        state = initial().decision()
        state = replace(state, config=replace(state.config, memory_bytes=32))
        _, memory = Agent().act(state, b'')
        self.assertLessEqual(len(memory), 32)


if __name__ == '__main__':
    unittest.main()
