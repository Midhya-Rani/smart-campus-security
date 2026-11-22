# AI Smart Campus Security System

University prototype combining **DSA, AI (YOLO + OpenCV), Machine Learning and a Tkinter GUI**.

Pipeline: `video -> YOLO person detection -> rule engine (location + time) -> alert queues -> SQLite + GUI`

## Setup
```bash
python -m venv .venv
.venv\Scripts\activate        # Windows   (Linux/Mac: source .venv/bin/activate)
pip install -r requirements.txt
python main.py                # GUI
python main.py --demo         # text-only demo
python -m unittest discover -s tests -v   # run tests
```
Tkinter ships with Python on Windows/macOS. On Ubuntu: `sudo apt install python3-tk`.
The first run with a video downloads the `yolov8n.pt` model automatically.

## Project structure
| File | Purpose |
|------|---------|
| `campus/dsa.py` | Linked list, Queue, Priority Queue, AlertManager |
| `campus/graph.py` | Campus graph, BFS, DFS, A* |
| `campus/rules.py` | Rule engine (restricted locations + allowed times) |
| `campus/detector.py` | YOLO person detection with OpenCV |
| `campus/database.py` | SQLite storage + Pandas summaries |
| `campus/classifier.py` | Optional scikit-learn event classifier |
| `campus/gui.py` | Tkinter dashboard (7 tabs) |
| `tests/` | Unit tests |

## Responsible use
No face recognition. Person detection is not proof of wrongdoing - alerts must be reviewed by a human. Use only authorized videos.
The ML classifier is trained on synthetic data (demo of the workflow only).

## Team Members
| Member | Responsibility |
|--------|----------------|
| Sherbaz | Data structures (linked list, queue, priority queue) and graph algorithms (BFS, DFS, A*) |
| Muskan | YOLO person detection, rule engine, ML classifier |
| Midhya | SQLite database, data models, main application and dashboard |
