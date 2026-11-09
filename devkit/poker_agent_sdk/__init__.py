"""Stand-in for the organizers' poker_agent_sdk, built from the published docs.

Only for local testing before the starter kit is released: devkit/play.py puts
this directory first on sys.path. Once the real kit is installed, test with
its `poker-agent play` instead and delete nothing here: the bot never ships it.
"""
from dataclasses import dataclass
from typing import Any, List, Optional


@dataclass
class Action:
    kind: str
    amount: Optional[int] = None

    @classmethod
    def fold(cls):
        return cls("fold")

    @classmethod
    def check(cls):
        return cls("check")

    @classmethod
    def call(cls):
        return cls("call")

    @classmethod
    def raise_to(cls, total):
        return cls("raise", total)


@dataclass
class LegalAction:
    kind: str
    min_amount: Optional[int] = None
    max_amount: Optional[int] = None


@dataclass
class Event:
    kind: str
    seat: Optional[int] = None
    amount: Optional[int] = None
    cards: Optional[List[str]] = None


@dataclass
class SeatState:
    seat: int
    stack: int
    bet: int
    status: str            # active | folded | all_in | busted
    shown_cards: Optional[List[str]] = None


@dataclass
class Blinds:
    small: int
    big: int
    ante: int = 0


@dataclass
class Config:
    table_id: str
    seat: int
    variant: str
    players: int
    starting_stack: int
    blinds: List[Blinds]
    hands_per_level: int
    hand_cap: int
    payouts: List[float]
    decision_ms: float = 1.0
    time_bank_ms: float = 100.0
    memory_bytes: int = 65536


@dataclass
class State:
    seat: int
    cards: List[str]
    board: List[str]
    pot: int
    to_call: int
    legal_actions: List[LegalAction]
    history: List[Event]
    phase: str
    variant: Any
    seats: List[SeatState]
    button: int
    blind_level: int
    blinds: Blinds
    hands_until_next_level: int
    hand_number: int
    players_remaining: int
    bust_order: List[int]
    config: Config
    events: List[Event]
    time_bank_ms: float = 100.0

    def can(self, kind):
        for la in self.legal_actions:
            if la.kind == kind:
                return la
        return None


class Agent:
    def act(self, state, memory):  # pragma: no cover - interface
        raise NotImplementedError
