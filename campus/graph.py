"""Virtual campus modelled as a graph (NetworkX stores it, our code searches it).

Vertices = campus locations, edges = walking paths, edge weight = distance.
BFS, DFS and A* are implemented by hand to demonstrate the algorithms.
"""
import heapq
import math
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import networkx as nx

# name -> (x, y) on a 0..100 map grid
DEFAULT_LOCATIONS: Dict[str, Tuple[float, float]] = {
    "Main Gate": (10, 50),
    "Security Office": (22, 25),
    "Admin Block": (35, 50),
    "Library": (55, 22),
    "Cafeteria": (55, 72),
    "Computer Lab": (78, 40),
    "Physics Lab": (86, 12),
    "Auditorium": (68, 58),
    "Hostel": (90, 82),
    "Parking": (10, 85),
    "Sports Ground": (35, 90),
}

DEFAULT_PATHS: List[Tuple[str, str]] = [
    ("Main Gate", "Security Office"),
    ("Main Gate", "Admin Block"),
    ("Main Gate", "Parking"),
    ("Security Office", "Admin Block"),
    ("Admin Block", "Library"),
    ("Admin Block", "Cafeteria"),
    ("Library", "Computer Lab"),
    ("Library", "Physics Lab"),
    ("Computer Lab", "Physics Lab"),
    ("Computer Lab", "Auditorium"),
    ("Cafeteria", "Auditorium"),
    ("Cafeteria", "Sports Ground"),
    ("Auditorium", "Hostel"),
    ("Parking", "Sports Ground"),
]


@dataclass
class PathResult:
    algorithm: str
    path: List[str] = field(default_factory=list)
    cost: float = 0.0
    explored: List[str] = field(default_factory=list)   # nodes visited, in order

    @property
    def found(self) -> bool:
        return bool(self.path)


class CampusGraph:
    def __init__(self, locations=None, paths=None):
        self.g = nx.Graph()
        self.pos: Dict[str, Tuple[float, float]] = {}
        for name, xy in (locations or DEFAULT_LOCATIONS).items():
            self.add_location(name, *xy)
        for a, b in (paths or DEFAULT_PATHS):
            self.add_path(a, b)

    # ---- building the graph -------------------------------------------
    def add_location(self, name: str, x: float, y: float) -> None:
        self.g.add_node(name)
        self.pos[name] = (x, y)

    def add_path(self, a: str, b: str, weight: Optional[float] = None) -> None:
        """Add a walking path after validating its locations and distance."""
        self._check(a, b)

        if weight is None:
            weight = round(self._euclid(a, b), 1)

        if isinstance(weight, bool) or not isinstance(weight, (int, float)):
            raise TypeError("Path weight must be a number")

        if not math.isfinite(weight) or weight < 0:
            raise ValueError("Path weight must be finite and non-negative")

        self.g.add_edge(a, b, weight=weight)

    # ---- helpers --------------------------------------------------------
    def locations(self) -> List[str]:
        return sorted(self.g.nodes)

    def neighbors(self, node: str) -> List[str]:
        return sorted(self.g.neighbors(node))   # sorted => deterministic output

    def weight(self, a: str, b: str) -> float:
        return self.g[a][b]["weight"]

    def path_cost(self, path: List[str]) -> float:
        return round(sum(self.weight(a, b) for a, b in zip(path, path[1:])), 1)

    def _euclid(self, a: str, b: str) -> float:
        (x1, y1), (x2, y2) = self.pos[a], self.pos[b]
        return math.hypot(x1 - x2, y1 - y2)

    def _check(self, *names: str) -> None:
        for n in names:
            if n not in self.g:
                raise KeyError(f"Unknown location: {n}")

    # ---- traversal ------------------------------------------------------
    def bfs_order(self, start: str) -> List[str]:
        """Breadth-first traversal order (level by level)."""
        self._check(start)
        seen, order, queue = {start}, [], deque([start])
        while queue:
            node = queue.popleft()
            order.append(node)
            for nb in self.neighbors(node):
                if nb not in seen:
                    seen.add(nb)
                    queue.append(nb)
        return order

    def dfs_order(self, start: str) -> List[str]:
        """Depth-first traversal order (go deep first)."""
        self._check(start)
        seen, order, stack = set(), [], [start]
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            order.append(node)
            # reversed so the alphabetically-first neighbour is visited first
            for nb in reversed(self.neighbors(node)):
                if nb not in seen:
                    stack.append(nb)
        return order

    # ---- routing --------------------------------------------------------
    def bfs_path(self, start: str, goal: str) -> PathResult:
        """Fewest-hops route (ignores distance)."""
        self._check(start, goal)
        parent = {start: None}
        explored, queue = [], deque([start])
        while queue:
            node = queue.popleft()
            explored.append(node)
            if node == goal:
                path = self._rebuild(parent, goal)
                return PathResult("BFS", path, self.path_cost(path), explored)
            for nb in self.neighbors(node):
                if nb not in parent:
                    parent[nb] = node
                    queue.append(nb)
        return PathResult("BFS", [], 0.0, explored)

    def astar(self, start: str, goal: str) -> PathResult:
        """Shortest-distance route: f(n) = g(n) + h(n), h = straight-line distance."""
        self._check(start, goal)
        open_heap = [(self._euclid(start, goal), 0.0, start)]
        g_cost = {start: 0.0}
        parent = {start: None}
        closed, explored = set(), []
        while open_heap:
            _, g, node = heapq.heappop(open_heap)
            if node in closed:
                continue
            closed.add(node)
            explored.append(node)
            if node == goal:
                path = self._rebuild(parent, goal)
                return PathResult("A*", path, round(g, 1), explored)
            for nb in self.neighbors(node):
                new_g = g + self.weight(node, nb)
                if new_g < g_cost.get(nb, float("inf")):
                    g_cost[nb] = new_g
                    parent[nb] = node
                    heapq.heappush(open_heap, (new_g + self._euclid(nb, goal), new_g, nb))
        return PathResult("A*", [], 0.0, explored)

    @staticmethod
    def _rebuild(parent: dict, goal: str) -> List[str]:
        path, node = [], goal
        while node is not None:
            path.append(node)
            node = parent[node]
        return path[::-1]
