import asyncio
import threading


class OrderEvents:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: set[tuple[asyncio.AbstractEventLoop, asyncio.Queue[int]]] = set()
        self._pending: dict[asyncio.Queue[int], int] = {}

    def subscribe(self) -> asyncio.Queue[int]:
        queue: asyncio.Queue[int] = asyncio.Queue(maxsize=1)
        with self._lock:
            if len(self._subscribers) >= 100:
                raise ValueError("Too many event streams")
            self._subscribers.add((asyncio.get_running_loop(), queue))
        return queue

    def unsubscribe(self, queue: asyncio.Queue[int]) -> None:
        with self._lock:
            self._subscribers = {(loop, item) for loop, item in self._subscribers if item is not queue}
            self._pending.pop(queue, None)

    def publish(self, order_id: int) -> None:
        def deliver(queue: asyncio.Queue[int]) -> None:
            with self._lock:
                value = self._pending.pop(queue, None)
            if value is None:
                return
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(value)

        with self._lock:
            for loop, queue in self._subscribers:
                scheduled = queue in self._pending
                self._pending[queue] = order_id
                if not scheduled:
                    loop.call_soon_threadsafe(deliver, queue)
