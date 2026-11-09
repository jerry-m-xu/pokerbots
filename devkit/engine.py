"""No-limit hold'em sit-and-go engine for local testing against the stand-in SDK.

Mirrors the published rules: blinds rise every `hands_per_level` hands, the
table ends when one seat holds every chip or at `hand_cap` (survivors split
the payouts by ICM), simultaneous busts are ordered by chips at hand start,
and failed decisions play check-if-free-else-fold. A timeout or exception
keeps the previous memory and re-delivers that turn's events; an illegal
action stores the returned memory.

Not modelled: the kit's exact blind schedule (VERIFY), short all-in raises not
reopening the betting, and process/transport overhead in the time limit.
"""
import random
import time

from poker_agent_sdk import Blinds, Config, Event, LegalAction, SeatState, State
from sngbot.cards import card_str, evaluate
from sngbot.icm import icm_me

# Guess until the kit is out: starts 10/20, roughly x1.5 per level.
DEFAULT_SCHEDULE = [(10, 20, 0), (15, 30, 0), (25, 50, 0), (40, 80, 0), (50, 100, 0),
                    (75, 150, 0), (100, 200, 0), (150, 300, 0), (200, 400, 0),
                    (300, 600, 0), (400, 800, 0), (600, 1200, 0), (800, 1600, 0)]


def _kname(k):
    k = getattr(k, "value", k)
    return str(k).lower().rsplit(".", 1)[-1]


class SeatStats:
    __slots__ = ("decisions", "failed", "errors", "illegal", "timeouts", "hist", "max_ms", "last_error")

    def __init__(self):
        self.decisions = self.failed = self.errors = self.illegal = self.timeouts = 0
        self.hist = [0] * 501          # 10 us buckets up to 5 ms
        self.max_ms = 0.0
        self.last_error = None


class Table:
    def __init__(self, agents, seed=0, starting_stack=2000, schedule=DEFAULT_SCHEDULE,
                 hands_per_level=20, hand_cap=250, payouts=(50, 30, 20),
                 decision_ms=1.0, time_bank_ms=100.0, enforce_time=False,
                 allowance_ms=0.5, memory_bytes=65536):
        self.rng = random.Random(seed)
        self.agents = agents
        self.n = n = len(agents)
        self.stack = [starting_stack] * n
        self.mem = [b""] * n
        self.bank = [float(time_bank_ms)] * n
        self.events = []
        self.ev_idx = [0] * n
        self.bust_order = []
        self.places = [None] * n
        self.hand_number = 0
        self.button = self.rng.randrange(n)
        self.schedule = [Blinds(*b) for b in schedule]
        self.hpl = hands_per_level
        self.hand_cap = hand_cap
        self.payouts = list(payouts)
        self.decision_ms = decision_ms
        self.enforce = enforce_time
        self.allowance = allowance_ms
        self.memory_bytes = memory_bytes
        self.stats = [SeatStats() for _ in range(n)]
        self.cfgs = [Config(f"t{seed}", i, "nlhe", n, starting_stack, self.schedule, hands_per_level,
                            hand_cap, list(payouts), decision_ms, time_bank_ms, memory_bytes)
                     for i in range(n)]

    # ------------------------------------------------------------ helpers
    def emit(self, kind, seat=None, amount=None, cards=None):
        self.events.append(Event(kind, seat, amount, cards))

    def alive(self):
        return [i for i in range(self.n) if self.stack[i] > 0]

    def _next(self, s, pool):
        for k in range(1, self.n + 1):
            t = (s + k) % self.n
            if t in pool:
                return t
        return None

    def _status(self, i):
        if i not in self.dealt:
            return "busted"
        if i in self.folded:
            return "folded"
        if self.stack[i] == 0:
            return "all_in"
        return "active"

    # ------------------------------------------------------------ table loop
    def run(self):
        while len(self.alive()) > 1 and self.hand_number < self.hand_cap:
            self.play_hand()
        return self.finish()

    def finish(self):
        points = [0.0] * self.n
        alive = self.alive()
        if len(alive) == 1:
            self.places[alive[0]] = 1
        else:
            stacks = [self.stack[s] for s in alive]
            for i, s in enumerate(alive):
                points[s] = icm_me(stacks, i, self.payouts)
            for rank, s in enumerate(sorted(alive, key=lambda s: -self.stack[s])):
                self.places[s] = rank + 1
            alive = set(alive)
        for s in range(self.n):
            if s in alive and len(alive) > 1:
                continue
            p = self.places[s]
            points[s] = float(self.payouts[p - 1]) if p and p - 1 < len(self.payouts) else 0.0
        return points

    def play_hand(self):
        self.hand_number += 1
        level = min((self.hand_number - 1) // self.hpl, len(self.schedule) - 1)
        bl = self.schedule[level]
        self.level, self.blinds = level, bl
        alive = self.alive()
        self.dealt = set(alive)
        if self.hand_number > 1 or self.button not in self.dealt:
            self.button = self._next(self.button, self.dealt)
        start = list(self.stack)
        self.hand_start = len(self.events)
        self.folded = set()
        self.contrib = [0] * self.n
        self.bet = [0] * self.n
        self.emit("hand", None, self.hand_number)

        if len(alive) == 2:
            sb_seat = self.button
            bb_seat = self._next(sb_seat, self.dealt)
        else:
            sb_seat = self._next(self.button, self.dealt)
            bb_seat = self._next(sb_seat, self.dealt)
        if bl.ante:
            for s in alive:
                a = min(bl.ante, self.stack[s])
                self.stack[s] -= a
                self.contrib[s] += a
                self.emit("ante", s, a)
        for s, amt in ((sb_seat, bl.small), (bb_seat, bl.big)):
            a = min(amt, self.stack[s])
            self.stack[s] -= a
            self.bet[s] += a
            self.contrib[s] += a
            self.emit("blind", s, a)

        deck = list(range(52))
        self.rng.shuffle(deck)
        self.hole = {s: [deck.pop(), deck.pop()] for s in alive}
        self.board = []
        self.betting_round(self._next(bb_seat, self.dealt), bl.big)
        for k in (3, 1, 1):
            if len(self.dealt - self.folded) <= 1:
                break
            new = [deck.pop() for _ in range(k)]
            self.board += new
            self.emit("board", None, None, [card_str(c) for c in new])
            self.bet = [0] * self.n
            self.betting_round(self._next(self.button, self.dealt), bl.big)
        self.award()
        for s in sorted(self.dealt):
            self.emit("stack", s, self.stack[s])

        busted = sorted((s for s in alive if self.stack[s] == 0), key=lambda s: start[s])
        remaining = len(self.alive())
        for k, s in enumerate(busted):
            self.places[s] = remaining + len(busted) - k
            self.bust_order.append(s)

    # ------------------------------------------------------------ betting
    def _can_act(self, s):
        return s in self.dealt and s not in self.folded and self.stack[s] > 0

    def betting_round(self, first, bb):
        max_bet = max(self.bet)
        last_raise = bb
        pending = {s for s in self.dealt if self._can_act(s)}
        if len(pending) <= 1:
            s = next(iter(pending), None)
            if s is None or self.bet[s] >= max_bet:
                return
        p = first
        while pending:
            if len(self.dealt - self.folded) <= 1:
                return
            s = p
            while s not in pending:
                s = (s + 1) % self.n
            p = (s + 1) % self.n
            to_call = max_bet - self.bet[s]
            legal = []
            if to_call <= 0:
                legal.append(LegalAction("check"))
            else:
                c = min(to_call, self.stack[s])
                legal += [LegalAction("fold"), LegalAction("call", c, c)]
            others = any(self._can_act(o) for o in self.dealt if o != s)
            if self.stack[s] > to_call and others:
                hi = self.bet[s] + self.stack[s]
                legal.append(LegalAction("raise", min(max_bet + last_raise, hi), hi))
            kind, amt = self.ask(s, legal, max(0, to_call))
            pending.discard(s)
            if kind == "fold":
                self.folded.add(s)
                self.emit("fold", s)
            elif kind == "check":
                self.emit("check", s)
            elif kind == "call":
                a = min(to_call, self.stack[s])
                self.stack[s] -= a
                self.bet[s] += a
                self.contrib[s] += a
                self.emit("call", s, a)
            else:
                add = amt - self.bet[s]
                self.stack[s] -= add
                self.contrib[s] += add
                self.bet[s] = amt
                if amt - max_bet >= last_raise:
                    last_raise = amt - max_bet
                max_bet = max(max_bet, amt)
                self.emit("raise", s, amt)
                pending = {o for o in self.dealt if o != s and self._can_act(o)}

    def ask(self, s, legal, to_call):
        st = self.stats[s]
        n = self.n
        state = State(
            seat=s, cards=[card_str(c) for c in self.hole[s]], board=[card_str(c) for c in self.board],
            pot=sum(self.contrib), to_call=min(to_call, self.stack[s]), legal_actions=legal,
            history=self.events[self.hand_start:], phase="betting", variant={},
            seats=[SeatState(i, self.stack[i], self.bet[i], self._status(i)) for i in range(n)],
            button=self.button, blind_level=self.level, blinds=self.blinds,
            hands_until_next_level=self.hpl - (self.hand_number - 1) % self.hpl,
            hand_number=self.hand_number, players_remaining=len(self.dealt),
            bust_order=list(self.bust_order), config=self.cfgs[s],
            events=self.events[self.ev_idx[s]:], time_bank_ms=self.bank[s])
        t0 = time.perf_counter_ns()
        try:
            res = self.agents[s].act(state, self.mem[s])
            err = None
        except Exception as e:  # noqa: BLE001
            res, err = None, e
        ms = (time.perf_counter_ns() - t0) / 1e6
        st.decisions += 1
        st.hist[min(500, int(ms * 100))] += 1
        st.max_ms = max(st.max_ms, ms)

        timeout = False
        if self.enforce:
            over = ms - (self.decision_ms + self.allowance)
            if over > 0:
                if self.bank[s] >= over:
                    self.bank[s] -= over
                else:
                    self.bank[s] = 0.0
                    timeout = True
        legal_by = {la.kind: la for la in legal}
        fallback = ("check", None) if "check" in legal_by else ("fold", None)
        if err is not None or timeout or not isinstance(res, tuple) or len(res) != 2:
            st.failed += 1
            if err is not None:
                st.errors += 1
                st.last_error = repr(err)
            if timeout:
                st.timeouts += 1
            return fallback               # memory kept, events re-delivered
        action, mem = res
        self.ev_idx[s] = len(self.events)
        self.mem[s] = bytes(mem or b"")[: self.memory_bytes]
        kind = _kname(getattr(action, "kind", ""))
        amt = getattr(action, "amount", None)
        la = legal_by.get(kind)
        if la is None:
            st.failed += 1
            st.illegal += 1
            st.last_error = f"illegal kind {kind} not in {list(legal_by)}"
            return fallback
        if kind == "raise":
            try:
                amt = int(amt)
            except (TypeError, ValueError):
                amt = -1
            if not la.min_amount <= amt <= la.max_amount:
                st.failed += 1
                st.illegal += 1
                st.last_error = f"raise {amt} outside [{la.min_amount}, {la.max_amount}]"
                return fallback
        return kind, amt

    # ------------------------------------------------------------ showdown
    def award(self):
        contenders = [s for s in self.dealt if s not in self.folded]
        n = self.n
        won = [0] * n
        if len(contenders) == 1:
            w = contenders[0]
            won[w] = sum(self.contrib)
        else:
            order = sorted(range(n), key=lambda s: -self.contrib[s])
            top, second = order[0], order[1]
            refund = self.contrib[top] - self.contrib[second]
            if refund > 0:
                self.contrib[top] -= refund
                self.stack[top] += refund
            vals = {s: evaluate(self.hole[s] + self.board) for s in contenders}
            for s in contenders:
                self.emit("show", s, None, [card_str(c) for c in self.hole[s]])
            prev = 0
            for lvl in sorted({c for c in self.contrib if c > 0}):
                amount = sum(min(c, lvl) - min(c, prev) for c in self.contrib)
                elig = [s for s in contenders if self.contrib[s] >= lvl] or contenders
                best = max(vals[s] for s in elig)
                winners = [s for s in elig if vals[s] == best]
                winners.sort(key=lambda s: (s - self.button - 1) % n)
                share, rem = divmod(amount, len(winners))
                for k, w in enumerate(winners):
                    won[w] += share + (1 if k < rem else 0)
                prev = lvl
        for s in range(n):
            if won[s]:
                self.stack[s] += won[s]
                self.emit("win", s, won[s])
