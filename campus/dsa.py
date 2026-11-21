"""Hand-written Data Structures used by the project.

* LinkedList     - event-history sequence (insert / traverse / delete)
* Queue          - FIFO queue built on linked nodes
* PriorityQueue  - binary-heap based priority queue (max priority first)
* AlertManager   - uses the Queue and PriorityQueue together to manage alerts
"""
import heapq
import itertools
from typing import Any, Iterator, List, Optional

from .models import Alert


class _Node:
    __slots__ = ("value", "next")

    def __init__(self, value: Any):
        self.value = value
        self.next: Optional["_Node"] = None


class LinkedList:
    """Singly linked list with head and tail pointers."""

    def __init__(self):
        self.head: Optional[_Node] = None
        self.tail: Optional[_Node] = None
        self._size = 0

    def __len__(self) -> int:
        return self._size

    def __iter__(self) -> Iterator[Any]:
        node = self.head
        while node:
            yield node.value
            node = node.next

    def append(self, value: Any) -> None:
        """Insert at the end - O(1)."""
        node = _Node(value)
        if self.tail is None:
            self.head = self.tail = node
        else:
            self.tail.next = node
            self.tail = node
        self._size += 1

    def prepend(self, value: Any) -> None:
        """Insert at the beginning - O(1)."""
        node = _Node(value)
        node.next = self.head
        self.head = node
        if self.tail is None:
            self.tail = node
        self._size += 1

    def insert_at(self, index: int, value: Any) -> None:
        """Insert at a position - O(n)."""
        if index < 0 or index > self._size:
            raise IndexError("index out of range")
        if index == 0:
            return self.prepend(value)
        if index == self._size:
            return self.append(value)
        prev = self.head
        for _ in range(index - 1):
            prev = prev.next
        node = _Node(value)
        node.next = prev.next
        prev.next = node
        self._size += 1

    def delete_at(self, index: int) -> Any:
        """Remove and return the value at a position - O(n)."""
        if index < 0 or index >= self._size:
            raise IndexError("index out of range")
        if index == 0:
            node = self.head
            self.head = node.next
            if self.head is None:
                self.tail = None
        else:
            prev = self.head
            for _ in range(index - 1):
                prev = prev.next
            node = prev.next
            prev.next = node.next
            if node is self.tail:
                self.tail = prev
        self._size -= 1
        return node.value

    def to_list(self) -> List[Any]:
        return list(self)

    def last(self, n: int) -> List[Any]:
        """Return the last n items (oldest first)."""
        items = self.to_list()
        return items[-n:] if n > 0 else []


class Queue:
    """FIFO queue (First In, First Out) built on linked nodes."""

    def __init__(self):
        self._items = LinkedList()

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[Any]:
        return iter(self._items)

    def is_empty(self) -> bool:
        return len(self._items) == 0

    def enqueue(self, value: Any) -> None:
        self._items.append(value)

    def dequeue(self) -> Any:
        if self.is_empty():
            raise IndexError("dequeue from empty queue")
        return self._items.delete_at(0)

    def peek(self) -> Any:
        if self.is_empty():
            raise IndexError("peek from empty queue")
        return self._items.head.value


class PriorityQueue:
    """Max-priority queue on top of a binary heap.

    Higher priority number = served first. Items with equal priority are
    served in arrival order (a running counter breaks ties).
    """

    def __init__(self):
        self._heap: list = []
        self._counter = itertools.count()

    def __len__(self) -> int:
        return len(self._heap)

    def is_empty(self) -> bool:
        return not self._heap

    def push(self, item: Any, priority: int) -> None:
        heapq.heappush(self._heap, (-priority, next(self._counter), item))

    def pop(self) -> Any:
        if not self._heap:
            raise IndexError("pop from empty priority queue")
        return heapq.heappop(self._heap)[2]

    def peek(self) -> Any:
        if not self._heap:
            raise IndexError("peek from empty priority queue")
        return self._heap[0][2]

    def sorted_items(self) -> List[Any]:
        """Items in the order they would be popped (non-destructive)."""
        return [entry[2] for entry in sorted(self._heap)]


class AlertManager:
    """Keeps every pending alert in BOTH a FIFO queue and a priority queue.

    * ``next_fifo()``     -> oldest pending alert
    * ``next_priority()`` -> most severe pending alert (oldest first on ties)

    When an alert is reviewed through one queue it is marked ``reviewed`` and
    skipped (lazy deletion) when the other queue reaches it.
    """

    def __init__(self):
        self.fifo = Queue()
        self.pq = PriorityQueue()

    def add(self, alert: Alert) -> None:
        self.fifo.enqueue(alert)
        self.pq.push(alert, alert.severity)

    def _pop_pending(self, take) -> Optional[Alert]:
        while True:
            try:
                alert = take()
            except IndexError:
                return None
            if alert.status == "pending":
                alert.status = "reviewed"
                return alert

    def next_fifo(self) -> Optional[Alert]:
        return self._pop_pending(self.fifo.dequeue)

    def next_priority(self) -> Optional[Alert]:
        return self._pop_pending(self.pq.pop)

    def pending_fifo(self) -> List[Alert]:
        return [a for a in self.fifo if a.status == "pending"]

    def pending_priority(self) -> List[Alert]:
        return [a for a in self.pq.sorted_items() if a.status == "pending"]

    def pending_count(self) -> int:
        return len(self.pending_fifo())
