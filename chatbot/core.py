"""Trust boundaries and conversation orchestration; no networking."""

from collections import OrderedDict
from dataclasses import dataclass
import json
import logging
import re
import threading
import time
from typing import Callable, Protocol

MAX_INPUT = 1000
MAX_RESPONSE = 240
ORDER_ID = re.compile(r"ORD-[0-9]{3}")
LOG = logging.getLogger("chatbot")


@dataclass(frozen=True)
class Principal:
    name: str
    chat_id: int


# These handles represent trusted transport context, NEVER fields in an update.
TRANSPORTS = {"fixture-alice": Principal("alice", 101),
              "fixture-bob": Principal("bob", 202)}


@dataclass(frozen=True)
class State:
    intent: str | None = None
    order_id: str | None = None
    touched: float = 0


class LLMProvider(Protocol):
    def decide(self, text: str, state: State) -> object:
        """Return only {intent: status|return|unknown, order_id: str|None}."""
        ...


def validate_decision(value: object) -> tuple[str, str | None]:
    if type(value) is not dict or set(value) != {"intent", "order_id"}:
        raise ValueError("invalid decision")
    intent, order = value["intent"], value["order_id"]
    if type(intent) is not str or intent not in ("status", "return", "unknown"):
        raise ValueError("invalid intent")
    if order is not None and (type(order) is not str or not ORDER_ID.fullmatch(order)):
        raise ValueError("invalid order")
    return intent, order


class MockProvider:
    """Deterministic keyword matching, not reasoning or a language model."""

    def decide(self, text: str, state: State) -> object:
        lowered = text.lower()
        intent = ("return" if "return" in lowered else
                  "status" if "status" in lowered or "where" in lowered else "unknown")
        orders = ORDER_ID.findall(text.upper())
        # Ambiguous multiple IDs must not silently choose an order.
        result = {"intent": "unknown" if len(set(orders)) > 1 else intent,
                  "order_id": orders[0] if len(set(orders)) == 1 else None}
        validate_decision(result)
        return result


class TransientAPIError(Exception):
    """Only this explicit failure class permits retry."""


class DeadlineExceeded(Exception):
    pass


@dataclass(frozen=True)
class Order:
    order_id: str
    status: str
    return_eligible: bool


class OrderAPI:
    """Authorization precedes every fixture read, including each retry."""

    _owners = {"ORD-101": "alice", "ORD-102": "alice", "ORD-201": "bob"}
    _orders = {"ORD-101": Order("ORD-101", "delivered", True),
               "ORD-102": Order("ORD-102", "shipped", False),
               "ORD-201": Order("ORD-201", "processing", False)}

    def authorized(self, principal: Principal, order_id: str) -> bool:
        return self._owners.get(order_id) == principal.name

    def read(self, principal: Principal, order_id: str) -> Order:
        if not self.authorized(principal, order_id):
            raise PermissionError("unavailable")
        return self._fetch(order_id)

    def _fetch(self, order_id: str) -> Order:
        return self._orders[order_id]


def render(order: Order, requested: str, intent: str) -> str:
    if (type(order) is not Order or order.order_id != requested
            or order.status not in ("processing", "shipped", "delivered")
            or type(order.return_eligible) is not bool):
        raise ValueError("invalid API response")
    if intent == "return":
        result = f"{requested}: " + ("eligible for a return in this fixture."
                                       if order.return_eligible else
                                       "not eligible for a return in this fixture.")
    else:
        result = f"{requested}: {order.status}."
    if len(result) > MAX_RESPONSE:
        raise ValueError("response too long")
    return result


class Bot:
    def __init__(self, provider: LLMProvider | None = None, api: OrderAPI | None = None,
                 clock: Callable[[], float] = time.monotonic,
                 backoff: Callable[[float], None] = time.sleep,
                 ttl: float = 300, dedup_limit: int = 128):
        if ttl <= 0 or dedup_limit < 1:
            raise ValueError("positive limits required")
        self.provider = provider or MockProvider()
        self.api = api or OrderAPI()
        self.clock, self.backoff, self.ttl = clock, backoff, ttl
        self.dedup_limit = dedup_limit
        self._sessions: dict[Principal, State] = {}
        self._seen: OrderedDict[tuple[Principal, int], None] = OrderedDict()
        self._watermarks: dict[Principal, tuple[int, int]] = {}
        self._lock = threading.Lock()

    def _check(self, deadline: float) -> None:
        if self.clock() >= deadline:
            raise DeadlineExceeded()

    @staticmethod
    def _reply(event: str, text: str) -> str:
        # Callers supply fixed event constants only; never log payloads/exceptions.
        LOG.info(json.dumps({"event": event}, separators=(",", ":")))
        assert len(text) <= MAX_RESPONSE
        return text

    def handle(self, update: object, *, transport_handle: str) -> str:
        deadline = self.clock() + 5
        principal = TRANSPORTS.get(transport_handle) if type(transport_handle) is str else None
        if principal is None:
            return self._reply("auth_rejected", "Transport not authorized.")
        try:
            if type(update) is not dict:
                raise ValueError()
            uid, msg = update["update_id"], update["message"]
            mid, chat, text = msg["message_id"], msg["chat"], msg["text"]
            if (type(uid) is not int or uid < 0 or type(mid) is not int or mid < 1
                    or type(chat["id"]) is not int or chat["id"] != principal.chat_id
                    or chat["type"] != "private"):
                raise ValueError()
            if type(text) is not str or not text.strip() or len(text) > MAX_INPUT:
                raise ValueError()
        except (KeyError, TypeError, ValueError):
            return self._reply("input_rejected", "Invalid private-chat update or input (1–1000 characters).")
        # Serializes duplicates AND session transitions. Deadline includes lock wait.
        with self._lock:
            try:
                self._check(deadline)
                key = (principal, uid)
                if key in self._seen:
                    return self._reply("duplicate", "Duplicate update ignored.")
                previous = self._watermarks.get(principal, (-1, 0))
                if uid <= previous[0] or mid <= previous[1]:
                    return self._reply("stale", "Stale update ignored.")
                self._watermarks[principal] = (uid, mid)
                self._seen[key] = None
                while len(self._seen) > self.dedup_limit:
                    self._seen.popitem(last=False)
                now = self.clock()
                state = self._sessions.get(principal, State())
                if now - state.touched >= self.ttl:
                    state = State()
                    self._sessions.pop(principal, None)
                if text.strip().lower() in ("cancel", "/cancel", "reset", "/reset"):
                    self._sessions.pop(principal, None)
                    return self._reply("reset", "Conversation reset. Ask for order status or return eligibility.")
                self._check(deadline)
                decision = self.provider.decide(text, state)
                self._check(deadline)
                intent, order_id = validate_decision(decision)
                # Unknown text never triggers a read of a remembered order.
                if intent == "unknown" and order_id is None:
                    return self._reply("clarification", "Ask for status or return eligibility, with an order ID like ORD-101.")
                intent = state.intent if intent == "unknown" else intent
                order_id = order_id or state.order_id
                if order_id and not self.api.authorized(principal, order_id):
                    return self._reply("order_denied", "Order unavailable for this account.")
                if not intent or not order_id:
                    self._sessions[principal] = State(intent, order_id, now)
                    prompt = ("Which order? Use an ID like ORD-101." if not order_id else
                              "Would you like status or return eligibility?")
                    return self._reply("clarification", prompt)
                for attempt in range(2):
                    self._check(deadline)
                    try:
                        order = self.api.read(principal, order_id)
                    except TransientAPIError:
                        self._check(deadline)
                        if attempt == 1:
                            raise
                        self.backoff(0.1)
                        self._check(deadline)
                    except Exception:
                        self._check(deadline)
                        raise
                    else:
                        self._check(deadline)
                        break
                response = render(order, order_id, intent)
                self._sessions[principal] = State(intent, order_id, self.clock())
                return self._reply("answered", response)
            except DeadlineExceeded:
                return self._reply("timeout", "Request timed out. Please send a new message to try again.")
            except Exception:
                return self._reply("failure", "Unable to complete this request. Please send a new message to try again.")
