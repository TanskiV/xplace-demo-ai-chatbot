"""A socket-blocked, deterministic demo, with synthetic transport context."""

import argparse
from contextlib import contextmanager
import socket
from unittest.mock import patch

from .core import Bot


@contextmanager
def offline():
    """Fail immediately if code attempts an outbound socket connection."""
    with patch.object(socket.socket, "connect", side_effect=AssertionError("offline")), \
            patch.object(socket.socket, "connect_ex", side_effect=AssertionError("offline")), \
            patch.object(socket, "create_connection", side_effect=AssertionError("offline")):
        yield


def update(number: int, text: str, chat_id: int = 101) -> dict:
    return {"update_id": number, "message": {"message_id": number,
            "from": {"id": chat_id}, "chat": {"id": chat_id, "type": "private"},
            "text": text}}


def demo() -> str:
    lines = ["Synthetic offline order-support reference (MockProvider)."]
    with offline():
        bot = Bot()
        for i, text in enumerate(("status", "ORD-101", "Can I return it?", "/reset",
                                  "ORD-102", "status", "status ORD-201"), 1):
            lines.extend((f"You: {text}",
                          "Bot: " + bot.handle(update(i, text), transport_handle="fixture-alice")))
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["demo"])
    parser.parse_args()
    print(demo(), end="")


if __name__ == "__main__":
    main()
