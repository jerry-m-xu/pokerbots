"""Reproducible strategy comparisons using the unmodified official variant engine."""
import argparse
import json
import math
import os
from pathlib import Path
import random
import sys
import time
from multiprocessing import Pool

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'bot'))
os.environ['SNGBOT_RAISE'] = '1'
from agent import Agent
from sngbot.policy import P_DEFAULT
from sngbot.auction import bids
from sngbot.cards import parse_cards, hand_class, evaluate
from sngbot.ranges import pct
from poker_agent_sdk import Action
from poker_engine.table import SitAndGo, TableRules
from poker_engine.variant import load_variant
from poker_engine.scoring import table_points

BASE = dict(P_DEFAULT, fast_equity=False, sample_equity=False, auction_mult=0,
            open=(.50, .50, .42, .28, .21, .16, .13, .11, .10, .10),
            threebet_pct=.035, value_e=.66, cbet_size=.5)
PROFILES = {
    'baseline': BASE,
    'auction': dict(BASE, auction_mult=1),
    'equity': dict(BASE, auction_mult=1, fast_equity=True),
    'aggressive': dict(BASE, auction_mult=1, fast_equity=True,
                       open=(.65, .60, .48, .32, .24, .18, .15, .13, .11, .11),
                       threebet_pct=.045, value_e=.63, cbet_size=.4),
}
PROFILES['pressure'] = dict(PROFILES['aggressive'], auction_mult=3)


class Opponent:
    def __init__(self, style):
        self.style = style

    def act(self, state, memory):
        if state.phase == 'auction':
            return Action('bid', cards=bids(state, 1.5 if self.style == 'loose' else .7)), memory
        legal = {action.kind: action for action in state.legal_actions}
        passive = Action.check() if 'check' in legal else Action.fold()
        call = Action.call() if 'call' in legal else passive
        if self.style == 'station':
            return call, memory
        hole = parse_cards(state.cards)
        percentile = pct(hand_class(*hole))
        size = 0
        if not state.board:
            threshold = .16 if self.style == 'tight' else .40
            if self.style == 'jam':
                size = 10**9 if percentile < .30 else 0
            elif percentile < .04:
                size = max(state.blinds.big_blind * 3, max(seat.bet for seat in state.seats) * 3)
            elif percentile < threshold and state.to_call <= state.blinds.big_blind:
                size = state.blinds.big_blind * 3
            elif percentile < threshold * .6:
                return call, memory
        else:
            category = evaluate(hole + parse_cards(state.board)) >> 20
            if category >= 2 or (category >= 1 and self.style != 'tight'):
                size = state.pot if not state.to_call else 0
                if not size:
                    return call, memory
        if size and 'raise' in legal:
            bound = legal['raise']
            return Action.raise_to(max(bound.min_amount, min(bound.max_amount, size))), memory
        if size:
            return call, memory
        return passive, memory


def run(job):
    seed, profile, field, players, hand_cap = job
    rng = random.Random(seed)
    hero = seed % players
    rules = TableRules(players=players, hand_cap=hand_cap)
    table = SitAndGo(rules=rules, variant=load_variant('flop_auction_holdem'), table_id=str(seed), seed=str(seed))
    agents = []
    for seat in range(players):
        if seat == hero or field != 'mixed':
            agent = Agent()
            agent.params = PROFILES[profile if seat == hero else field]
        else:
            agent = Opponent(rng.choice(['tight', 'loose', 'jam', 'station']))
        agents.append(agent)
    memory = [b''] * players
    failures = [0] * players
    decisions = [0] * players
    latencies = []
    auction_count = 0
    while (state := table.decision()) is not None:
        seat = state.seat
        start = time.perf_counter_ns()
        action, memo = agents[seat].act(state, memory[seat])
        elapsed = (time.perf_counter_ns() - start) / 1e6
        memory[seat] = memo[:state.config.memory_bytes]
        decisions[seat] += 1
        if seat == hero:
            latencies.append(elapsed)
            auction_count += state.phase == 'auction'
        if not table.apply(action):
            failures[seat] += 1
    result = table.result(tuple(failures), tuple(decisions))
    return dict(points=table_points(result, table.payouts)[hero], failures=sum(failures),
                decisions=decisions[hero], auctions=auction_count, timings=latencies)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tables', type=int, default=100)
    parser.add_argument('--seed', type=int, default=1000)
    parser.add_argument('--profiles', nargs='+', choices=PROFILES, default=['baseline', 'auction', 'equity', 'aggressive'])
    parser.add_argument('--field', choices=['mixed', *PROFILES], default='baseline')
    parser.add_argument('--players', type=int, default=8)
    parser.add_argument('--hand-cap', type=int, default=250)
    parser.add_argument('--procs', type=int, default=2)
    args = parser.parse_args()
    report = {}
    with Pool(args.procs) as pool:
        for profile in args.profiles:
            results = pool.map(run, [(seed, profile, args.field, args.players, args.hand_cap) for seed in range(args.seed, args.seed + args.tables)])
            points = [result['points'] for result in results]
            timings = sorted(value for result in results for value in result['timings'])
            average = sum(points) / len(points)
            report[profile] = dict(tables=len(points), seed=args.seed, field=args.field, points=average,
                standard_error=math.sqrt(sum((point - average)**2 for point in points) / max(1,len(points)-1) / len(points)),
                failures=sum(result['failures'] for result in results), decisions=sum(result['decisions'] for result in results),
                auctions=sum(result['auctions'] for result in results), p99_ms=timings[int(.99*(len(timings)-1))], max_ms=max(timings))
            print(json.dumps({profile: report[profile]}), flush=True)


if __name__ == '__main__':
    main()
