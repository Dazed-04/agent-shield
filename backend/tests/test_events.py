import asyncio
import threading

from app.events import SSEBroadcaster


def test_publish_from_worker_threads_wakes_the_event_loop_and_filters_by_owner():
    async def run():
        b = SSEBroadcaster()
        admin = await b.subscribe("alice", True)
        sam = await b.subscribe("sam", False)
        sue = await b.subscribe("sue", False)

        def worker():  # FastAPI sync routes publish from threadpool threads
            b.publish_sync("chat_message", {"x": 1}, owner="sam")
            b.publish_sync("analytics_updated", {"y": 2}, admin_only=True)

        threading.Thread(target=worker).start()
        got_admin = [await asyncio.wait_for(admin.queue.get(), 2) for _ in range(2)]
        got_sam = await asyncio.wait_for(sam.queue.get(), 2)
        await asyncio.sleep(0.05)
        assert [e for e, _ in got_admin] == ["chat_message", "analytics_updated"]
        assert got_sam[0] == "chat_message"
        assert sam.queue.empty() and sue.queue.empty()

    asyncio.run(run())


def test_slow_subscriber_is_bounded_not_unbounded():
    async def run():
        b = SSEBroadcaster(max_queue=2)
        sub = await b.subscribe("alice", True)
        for i in range(10):
            b.publish_sync("e", i)
        await asyncio.sleep(0.05)
        assert sub.queue.qsize() == 2

    asyncio.run(run())


def test_unsubscribe_stops_delivery():
    async def run():
        b = SSEBroadcaster()
        sub = await b.subscribe("alice", True)
        b.unsubscribe(sub)
        b.publish_sync("e", 1)
        await asyncio.sleep(0.05)
        assert sub.queue.empty()

    asyncio.run(run())
