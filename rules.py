"""Rule engine: compares a detection (location + time) against security rules.

A rule describes WHEN people are allowed in a location. If people are detected
there outside that window, an alert is created.
"""
from dataclasses import dataclass
from datetime import datetime, time
from typing import Dict, List, Optional

from models import Alert


def parse_time(text: str) -> time:
    """'18:30' -> datetime.time(18, 30). Raises ValueError on bad input."""
    return datetime.strptime(text.strip(), "%H:%M").time()


@dataclass
class Rule:
    location: str
    allowed_from: time          # access allowed from ...
    allowed_to: time            # ... until (may wrap past midnight)
    severity: int = 3
    enabled: bool = True

    def is_allowed(self, t: time) -> bool:
        if self.allowed_from <= self.allowed_to:
            return self.allowed_from <= t <= self.allowed_to
        # window crosses midnight, e.g. 20:00 -> 06:00
        return t >= self.allowed_from or t <= self.allowed_to

    @property
    def window_text(self) -> str:
        return f"{self.allowed_from:%H:%M}-{self.allowed_to:%H:%M}"


DEFAULT_RULES = [
    Rule("Computer Lab", time(8, 0), time(20, 0), 3),
    Rule("Physics Lab", time(8, 0), time(17, 0), 3),
    Rule("Admin Block", time(8, 0), time(16, 0), 2),
    Rule("Library", time(8, 0), time(22, 0), 1),
    Rule("Parking", time(6, 0), time(22, 0), 1),
]


class RuleEngine:
    def __init__(self, rules: Optional[List[Rule]] = None):
        self.rules: Dict[str, Rule] = {}
        for r in rules or []:
            self.set_rule(r)

    def set_rule(self, rule: Rule) -> None:
        self.rules[rule.location] = rule

    def remove_rule(self, location: str) -> None:
        self.rules.pop(location, None)

    def evaluate(self, location: str, person_count: int, now: datetime) -> Optional[Alert]:
        """Return an Alert if the detection breaks a rule, otherwise None."""
        if person_count <= 0:
            return None
        rule = self.rules.get(location)
        if rule is None or not rule.enabled or rule.is_allowed(now.time()):
            return None
        plural = "person" if person_count == 1 else "people"
        return Alert(
            location=location,
            description=(f"{person_count} {plural} detected in {location} at "
                         f"{now:%H:%M} (access allowed {rule.window_text})"),
            severity=rule.severity,
            timestamp=now,
            person_count=person_count,
        )
