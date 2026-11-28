"""Entry point.

    python main.py          -> start the desktop GUI
    python main.py --demo   -> run a text-only demo (no GUI / camera needed)
"""
import argparse
from datetime import datetime

from classifier import EventClassifier
from campus.dsa import AlertManager
from campus.graph import CampusGraph
from rules import DEFAULT_RULES, RuleEngine


def demo() -> None:
    graph = CampusGraph()
    print("== Graph traversal from Security Office ==")
    print("BFS:", " -> ".join(graph.bfs_order("Security Office")))
    print("DFS:", " -> ".join(graph.dfs_order("Security Office")))

    print("\n== Route Security Office -> Physics Lab ==")
    for result in (graph.bfs_path("Security Office", "Physics Lab"),
                   graph.astar("Security Office", "Physics Lab")):
        print(f"{result.algorithm:3}: {' -> '.join(result.path)}  (distance {result.cost})")

    print("\n== Rule engine + alert queues ==")
    engine, manager, clf = RuleEngine(DEFAULT_RULES), AlertManager(), EventClassifier()
    clf.train()
    today = datetime.now().replace(second=0, microsecond=0)
    events = [("Library", 2, 23), ("Computer Lab", 1, 22), ("Physics Lab", 3, 2),
              ("Computer Lab", 2, 12)]          # last one is allowed -> no alert
    for i, (loc, people, hour) in enumerate(events, 1):
        alert = engine.evaluate(loc, people, today.replace(hour=hour, minute=0))
        if alert:
            alert.id, alert.category = i, clf.predict(hour, people, alert.severity)
            manager.add(alert)
            print(f"ALERT #{i} [{alert.severity_name}/{alert.category}] {alert.description}")
        else:
            print(f"ok    {loc} at {hour:02d}:00 - access allowed")
    print("\nFIFO order    :", [a.id for a in manager.pending_fifo()])
    print("Priority order:", [a.id for a in manager.pending_priority()])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Smart Campus Security System")
    parser.add_argument("--demo", action="store_true", help="run text-only demo")
    parser.add_argument("--db", default="campus_security.db", help="SQLite database file")
    args = parser.parse_args()
    if args.demo:
        demo()
    else:
        from campus.gui import run          # imported here so --demo works without Tk
        run(args.db)
