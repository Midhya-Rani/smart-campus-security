import unittest

from campus.dsa import AlertManager, LinkedList, PriorityQueue, Queue
from campus.models import Alert


def mk(i, sev):
    return Alert(location="Lab", description=f"a{i}", severity=sev, id=i)


class TestLinkedList(unittest.TestCase):
    def test_append_prepend_insert_delete(self):
        ll = LinkedList()
        ll.append(2); ll.append(3); ll.prepend(1)
        ll.insert_at(3, 5); ll.insert_at(3, 4)
        self.assertEqual(ll.to_list(), [1, 2, 3, 4, 5])
        self.assertEqual(ll.delete_at(0), 1)
        self.assertEqual(ll.delete_at(3), 5)
        ll.append(9)
        self.assertEqual(ll.to_list(), [2, 3, 4, 9])
        self.assertEqual(len(ll), 4)
        self.assertEqual(ll.last(2), [4, 9])
    def test_last_returns_independent_list(self):
        ll = LinkedList()

        for value in [10, 20, 30]:
            ll.append(value)

        result = ll.last(2)
        result.append(40)

        self.assertEqual(result, [20, 30, 40])
        self.assertEqual(ll.to_list(), [10, 20, 30]) 

    def test_index_errors(self):
        with self.assertRaises(IndexError):
            LinkedList().delete_at(0)

    def test_last_edge_cases(self):
        ll = LinkedList()

        self.assertEqual(ll.last(3), [])
        self.assertEqual(ll.last(0), [])
        self.assertEqual(ll.last(-2), [])

        for value in [10, 20, 30, 40, 50]:
            ll.append(value)

        self.assertEqual(ll.last(2), [40, 50])
        self.assertEqual(ll.last(5), [10, 20, 30, 40, 50])
        self.assertEqual(ll.last(10), [10, 20, 30, 40, 50])

class TestQueue(unittest.TestCase):
    def test_fifo(self):
        q = Queue()
        for i in (1, 2, 3):
            q.enqueue(i)
        self.assertEqual([q.dequeue(), q.dequeue(), q.peek()], [1, 2, 3])
        q.dequeue()
        self.assertTrue(q.is_empty())
        with self.assertRaises(IndexError):
            q.dequeue()


class TestPriorityQueue(unittest.TestCase):
    def test_order_and_ties(self):
        pq = PriorityQueue()
        pq.push("low", 1); pq.push("high1", 3); pq.push("mid", 2); pq.push("high2", 3)
        self.assertEqual(pq.sorted_items(), ["high1", "high2", "mid", "low"])
        self.assertEqual([pq.pop() for _ in range(4)], ["high1", "high2", "mid", "low"])


class TestAlertManager(unittest.TestCase):
    def test_both_queues_stay_in_sync(self):
        m = AlertManager()
        for a in (mk(1, 1), mk(2, 3), mk(3, 2)):
            m.add(a)
        self.assertEqual([a.id for a in m.pending_priority()], [2, 3, 1])
        self.assertEqual([a.id for a in m.pending_fifo()], [1, 2, 3])
        self.assertEqual(m.next_priority().id, 2)       # most severe
        self.assertEqual(m.next_fifo().id, 1)           # oldest
        self.assertEqual(m.next_fifo().id, 3)           # skips already-reviewed #2
        self.assertIsNone(m.next_priority())
        self.assertEqual(m.pending_count(), 0)


if __name__ == "__main__":
    unittest.main()
