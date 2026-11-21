import unittest

import networkx as nx

from campus.graph import CampusGraph


class TestGraph(unittest.TestCase):
    def setUp(self):
        self.g = CampusGraph()

    def test_traversals_visit_every_location_once(self):
        for order in (self.g.bfs_order("Main Gate"), self.g.dfs_order("Main Gate")):
            self.assertEqual(sorted(order), self.g.locations())
            self.assertEqual(order[0], "Main Gate")

    def test_bfs_visits_neighbours_before_deeper_nodes(self):
        order = self.g.bfs_order("Main Gate")
        for nb in self.g.neighbors("Main Gate"):
            self.assertLess(order.index(nb), order.index("Library"))

    def test_bfs_path_has_fewest_hops(self):
        res = self.g.bfs_path("Security Office", "Physics Lab")
        expected = nx.shortest_path_length(self.g.g, "Security Office", "Physics Lab")
        self.assertEqual(len(res.path) - 1, expected)

    def test_astar_matches_dijkstra_for_every_pair(self):
        names = self.g.locations()
        for a in names:
            for b in names:
                res = self.g.astar(a, b)
                expected = nx.dijkstra_path_length(self.g.g, a, b, weight="weight")
                self.assertAlmostEqual(res.cost, expected, delta=0.2)   # rounding to 0.1

    def test_same_start_and_goal(self):
        self.assertEqual(self.g.astar("Library", "Library").path, ["Library"])

    def test_unreachable_and_unknown(self):
        self.g.add_location("Island", 50, 50)
        self.assertFalse(self.g.astar("Library", "Island").found)
        self.assertFalse(self.g.bfs_path("Library", "Island").found)
        with self.assertRaises(KeyError):
            self.g.bfs_order("Nowhere")


if __name__ == "__main__":
    unittest.main()
