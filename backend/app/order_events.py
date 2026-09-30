import asyncio
import threading


class OrderEvents:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: set[tuple[asyncio.AbstractEventLoop, asyncio.Queue[int]]] = set()

    def subscribe(self) -> asyncio.Queue[int]:
        queue: asyncio.Queue[int] = asyncio.Queue(maxsize=1)
        with self._lock:
            self._subscribers.add((asyncio.get_running_loop(), queue))
        return queue

    def unsubscribe(self, queue: asyncio.Queue[int]) -> None:
        with self._lock:
            self._subscribers = {(loop, item) for loop, item in self._subscribers if item is not queue}

    def publish(self, order_id: int) -> None:
        def deliver(queue: asyncio.Queue[int]) -> None:
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(order_id)

        with self._lock:
            subscribers = tuple(self._subscribers)
        for loop, queue in subscribers:
            loop.call_soon_threadsafe(deliver, queue)
