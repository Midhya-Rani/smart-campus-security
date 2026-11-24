"""Shared data models used across the project."""
from dataclasses import dataclass, field
from datetime import datetime

SEVERITY_NAMES = {1: "Low", 2: "Medium", 3: "High"}


@dataclass
class Alert:
    """One security alert / event record."""

    location: str
    description: str
    severity: int = 2                      # 1 = Low, 2 = Medium, 3 = High
    timestamp: datetime = field(default_factory=datetime.now)
    person_count: int = 1
    category: str = ""                     # filled by the optional ML classifier
    status: str = "pending"                # pending | reviewed
    id: int = 0                            # assigned by the database

    @property
    def severity_name(self) -> str:
        return SEVERITY_NAMES.get(self.severity, str(self.severity))
