"""
Variable definitions for django_datalog.
"""

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class Var:
    """Variable placeholder for datalog queries."""

    name: str
    where: Any = None  # Q object for additional constraints

    def __repr__(self):
        if self.where is not None:
            return f"Var({self.name!r}, where={self.where!r})"
        return f"Var({self.name!r})"
