"""Opponent archetypes for local testing, guessed from what a 60-minute,
AI-assisted build tends to produce. Replace or reweight them with what the
round hand histories show the real field doing.
"""
import random

from poker_agent_sdk import Action, Agent
from sngbot.cards import PAIR, TWO_PAIR, evaluate, hand_class, parse_cards
from sngbot.ranges import pct


def _legal(state):
    return {la.kind: la for la in state.legal_actions}


def _check_fold(L):
    return Action.check() if "check" in L else Action.fold()


def _raise(L, total):
    la = L.get("raise")
    if la is None:
        return Action.call() if "call" in L else _check_fold(L)
    return Action.raise_to(max(la.min_amount, min(la.max_amount, int(total))))


def _bb(state):
    return state.blinds.big


def _me(state):
    return next(s for s in state.seats if s.seat == state.seat)


def _made(state):
    hole, board = parse_cards(state.cards), parse_cards(state.board)
    v = evaluate(hole + board)
    cat = v >> 20
    top = max((c >> 2 for c in board), default=0)
    top_pair = cat == PAIR and (v >> 16 & 15) >= top
    return cat, top_pair


class CheckOrFold(Agent):
    """Also stands in for bots that time out on every decision."""
    def act(self, state, memory):
        return _check_fold(_legal(state)), memory


class MinRaiser(Agent):
    def act(self, state, memory):
        L = _legal(state)
        if "raise" in L:
            return Action.raise_to(L["raise"].min_amount), memory
        return (Action.call() if "call" in L else Action.check()), memory


class Station(Agent):
    def act(self, state, memory):
        L = _legal(state)
        return (Action.call() if "call" in L else Action.check()), memory


class Maniac(Agent):
    """Shoves a wide range preflop, shoves any pair postflop."""
    def act(self, state, memory):
        L = _legal(state)
        if not state.board:
            hp = pct(hand_class(*parse_cards(state.cards)))
            if hp <= 0.40:
                return _raise(L, 10 ** 9), memory
            return _check_fold(L), memory
        cat, _ = _made(state)
        if cat >= PAIR:
            return _raise(L, 10 ** 9), memory
        return _check_fold(L), memory


class Tight(Agent):
    """Chart bot: top 12% raise 3x, shoves top 25% when short, bets pot with top pair+."""
    def act(self, state, memory):
        L = _legal(state)
        bb = _bb(state)
        me = _me(state)
        if not state.board:
            hp = pct(hand_class(*parse_cards(state.cards)))
            depth = (me.stack + me.bet) / bb
            if depth <= 10:
                return (_raise(L, 10 ** 9) if hp <= 0.25 else _check_fold(L)), memory
            if state.to_call <= bb:
                return (_raise(L, 3 * bb) if hp <= 0.12 else _check_fold(L)), memory
            if hp <= 0.03:
                return _raise(L, 3 * max(s.bet for s in state.seats)), memory
            if hp <= 0.08 and "call" in L:
                return Action.call(), memory
            return _check_fold(L), memory
        cat, top_pair = _made(state)
        if cat >= TWO_PAIR or top_pair:
            if state.to_call == 0:
                return _raise(L, state.pot), memory
            return (Action.call() if "call" in L else Action.check()), memory
        if cat >= PAIR and state.to_call <= state.pot / 3 and "call" in L:
            return Action.call(), memory
        return _check_fold(L), memory


class Loose(Agent):
    """Loose-aggressive: opens 35%, calls raises with 25%, bets pairs and some air."""
    def act(self, state, memory):
        L = _legal(state)
        bb = _bb(state)
        if not state.board:
            hp = pct(hand_class(*parse_cards(state.cards)))
            if state.to_call <= bb:
                return (_raise(L, 2.5 * bb) if hp <= 0.35 else _check_fold(L)), memory
            if hp <= 0.06:
                return _raise(L, 3 * max(s.bet for s in state.seats)), memory
            if hp <= 0.25 and "call" in L:
                return Action.call(), memory
            return _check_fold(L), memory
        cat, top_pair = _made(state)
        if state.to_call == 0:
            if cat >= PAIR or random.random() < 0.3:
                return _raise(L, 0.75 * state.pot), memory
            return Action.check(), memory
        if cat >= TWO_PAIR:
            return _raise(L, 3 * state.to_call + max(s.bet for s in state.seats)), memory
        if cat >= PAIR and "call" in L:
            return Action.call(), memory
        return _check_fold(L), memory


class RandomBot(Agent):
    def act(self, state, memory):
        L = _legal(state)
        r = random.random()
        if "raise" in L and r < 0.1:
            la = L["raise"]
            return Action.raise_to(random.randint(la.min_amount, la.max_amount)), memory
        if "call" in L and r < 0.6:
            return Action.call(), memory
        return _check_fold(L), memory


ARCHETYPES = {
    "check_or_fold": CheckOrFold, "min_raiser": MinRaiser, "station": Station,
    "maniac": Maniac, "tight": Tight, "loose": Loose, "random": RandomBot,
}

# Opponent mixes for play.py --field
FIELDS = {
    "mix": ["tight", "tight", "loose", "loose", "maniac", "station", "check_or_fold", "min_raiser", "random"],
    "kit": ["check_or_fold", "min_raiser"],
    "tough": ["tight", "tight", "loose", "maniac"],
    "soft": ["station", "check_or_fold", "random", "min_raiser", "loose"],
}
