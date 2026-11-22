"""OPTIONAL Machine-Learning extension: classify an event into a category.

Features : hour of day, number of people, rule severity
Classes  : Routine / Suspicious / Intrusion

NOTE: no real labelled dataset exists for this prototype, so the model is
trained on SYNTHETIC data generated from simple assumptions. It demonstrates
the scikit-learn workflow (dataset -> train -> evaluate -> predict); replace
`make_synthetic_data` with real labelled events for a real system.
"""
import random
from typing import List, Tuple

try:
    from sklearn.model_selection import train_test_split
    from sklearn.tree import DecisionTreeClassifier
    SKLEARN_AVAILABLE = True
except ImportError:                                   # scikit-learn is optional
    SKLEARN_AVAILABLE = False


def _label(hour: int, count: int, severity: int) -> str:
    night = hour >= 22 or hour < 5
    if night and severity >= 3:
        return "Intrusion"
    if night or count >= 3 or severity >= 3:
        return "Suspicious"
    return "Routine"


def make_synthetic_data(n: int = 600, seed: int = 42) -> Tuple[List[list], List[str]]:
    rng = random.Random(seed)
    X, y = [], []
    for _ in range(n):
        hour, count, sev = rng.randint(0, 23), rng.randint(1, 6), rng.randint(1, 3)
        X.append([hour, count, sev])
        y.append(_label(hour, count, sev))
    return X, y


class EventClassifier:
    def __init__(self):
        self.model = None
        self.accuracy = 0.0

    @property
    def available(self) -> bool:
        return SKLEARN_AVAILABLE and self.model is not None

    def train(self) -> float:
        """Train on synthetic data; returns accuracy on a held-out test split."""
        if not SKLEARN_AVAILABLE:
            return 0.0
        X, y = make_synthetic_data()
        X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=0)
        self.model = DecisionTreeClassifier(max_depth=5, random_state=0).fit(X_tr, y_tr)
        self.accuracy = float(self.model.score(X_te, y_te))
        return self.accuracy

    def predict(self, hour: int, person_count: int, severity: int) -> str:
        if not self.available:
            return ""
        return str(self.model.predict([[hour, person_count, severity]])[0])
