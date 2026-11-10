"""Real SDK subprocess test with a 1 ms decision limit and zero time bank."""
import argparse
import asyncio
import json
from pathlib import Path
import sys

from poker_agent_protocol.process import BotPool
from poker_engine.play import play_table
from poker_engine.table import SitAndGo, TableRules
from poker_engine.variant import load_variant


async def run(bot, opponent, tables):
    pools = [BotPool([sys.executable, '-m', 'poker_agent_sdk.guest', str(path)], copies=2, cwd=str(path))
             for path in (bot, opponent)]
    failures = decisions = 0
    per_table = []
    try:
        for number in range(tables):
            table = SitAndGo(rules=TableRules(players=2, hand_cap=20, decision_ms=1, time_bank_ms=0),
                             variant=load_variant('flop_auction_holdem'), table_id=str(number), seed=f'upload-{number}')
            seats = pools if number % 2 == 0 else pools[::-1]
            result = await play_table(table, seats)
            hero = number % 2
            failures += result.failures[hero]
            decisions += result.decisions[hero]
            per_table.append(dict(decisions=result.decisions[hero], failures=result.failures[hero]))
    finally:
        for pool in pools:
            await pool.stop()
    print(json.dumps(dict(tables=tables, decisions=decisions, failures=failures, time_bank_ms=0,
                         decision_ms=1, per_table=per_table, errors=pools[0].take_errors())))
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bot', type=Path, default=Path(__file__).resolve().parents[1] / 'bot')
    parser.add_argument('--opponent', type=Path, required=True)
    parser.add_argument('--tables', type=int, default=10)
    args = parser.parse_args()
    asyncio.run(run(args.bot.resolve(), args.opponent.resolve(), args.tables))
