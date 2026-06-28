"""Unit tests for the Publish-Subscribe hub fan-out (no real socket needed).

Runnable two ways:
    python tests/test_pubsub.py        # standalone
    pytest tests/test_pubsub.py        # if pytest installed
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from messaging.pubsub import PubSubHub  # noqa: E402


class FakeSub:
    def __init__(self, name: str) -> None:
        self.id = name
        self.received: list[str] = []

    async def send(self, text: str) -> None:
        self.received.append(text)

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other: object) -> bool:
        return getattr(other, "id", None) == self.id


def _run(coro):
    return asyncio.run(coro)


def test_fanout_to_channel_subscribers_only():
    async def main():
        hub = PubSubHub()
        a, b, c = FakeSub("a"), FakeSub("b"), FakeSub("c")
        await hub.subscribe("ch1", a)
        await hub.subscribe("ch1", b)
        await hub.subscribe("ch2", c)
        delivered = await hub.publish("ch1", "hello")
        assert delivered == 2, delivered
        assert a.received == ["hello"]
        assert b.received == ["hello"]
        assert c.received == []  # different channel untouched

    _run(main())


def test_unsubscribe_stops_delivery():
    async def main():
        hub = PubSubHub()
        a = FakeSub("a")
        await hub.subscribe("ch", a)
        await hub.unsubscribe("ch", a)
        assert await hub.publish("ch", "x") == 0
        assert a.received == []

    _run(main())


def test_retained_replayed_on_late_subscribe():
    async def main():
        hub = PubSubHub()
        await hub.publish("ch", "latest")  # no subscribers yet -> retained
        late = FakeSub("late")
        await hub.subscribe("ch", late)
        assert late.received == ["latest"]

    _run(main())


def test_failed_send_drops_subscriber():
    async def main():
        hub = PubSubHub()

        class Boom(FakeSub):
            async def send(self, text: str) -> None:
                raise RuntimeError("socket closed")

        good, bad = FakeSub("good"), Boom("bad")
        await hub.subscribe("ch", good)
        await hub.subscribe("ch", bad)
        delivered = await hub.publish("ch", "m")
        assert delivered == 1, delivered
        assert hub.subscriber_count("ch") == 1  # bad one removed

    _run(main())


def test_unsubscribe_all():
    async def main():
        hub = PubSubHub()
        a = FakeSub("a")
        await hub.subscribe("c1", a)
        await hub.subscribe("c2", a)
        await hub.unsubscribe_all(a)
        assert hub.subscriber_count("c1") == 0
        assert hub.subscriber_count("c2") == 0

    _run(main())


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except AssertionError as e:
                failures += 1
                print("FAIL", name, "-", e)
    print(f"pubsub: {'all tests passed' if not failures else f'{failures} FAILED'}")
    sys.exit(1 if failures else 0)
