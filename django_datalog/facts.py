"""
Fact system for djdatalog - handles fact definitions, storage, and retrieval.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Self, get_type_hints

import uuid6
from django.db import models


class FactConjunction(tuple):
    """
    A specialized tuple for representing conjunctive (AND) fact combinations.

    This provides better type safety and pattern matching than raw tuples
    while maintaining all tuple functionality for backward compatibility.
    """

    def __new__(cls, facts):
        """Create a new FactConjunction from a sequence of facts."""
        return super().__new__(cls, facts)

    def __repr__(self):
        if len(self) == 0:
            return "FactConjunction()"
        elif len(self) == 1:
            return f"{self[0]}"
        else:
            return " & ".join(str(fact) for fact in self)

    def __or__(self, other) -> list:
        """Implement | operator for FactConjunction | other."""
        from django_datalog.facts import Fact  # Avoid circular import

        match other:
            case Fact():
                return [self, other]
            case list():
                return [self, *other]
            case tuple() | FactConjunction():
                return [self, other]
            case _:
                raise TypeError(
                    f"Cannot use | operator between FactConjunction and {type(other).__name__}."
                )

    def __and__(self, other) -> FactConjunction:
        """Implement & operator for FactConjunction & other."""
        from django_datalog.facts import Fact  # Avoid circular import

        match other:
            case Fact():
                return FactConjunction(list(self) + [other])
            case tuple() | FactConjunction():
                return FactConjunction(list(self) + list(other))
            case list():
                raise TypeError(
                    "Cannot use & operator between FactConjunction and list. "
                    "Lists represent disjunction (OR)."
                )
            case _:
                raise TypeError(
                    f"Cannot use & operator between FactConjunction and {type(other).__name__}."
                )

    def __ror__(self, other) -> list:
        """Implement right-side | operator for other | FactConjunction."""
        from django_datalog.facts import Fact  # Avoid circular import

        match other:
            case Fact():
                return [other, self]
            case list():
                return [*other, self]
            case tuple() | FactConjunction():
                return [other, self]
            case _:
                raise TypeError(
                    f"Cannot use | operator between {type(other).__name__} and FactConjunction."
                )

    def __rand__(self, other) -> FactConjunction:
        """Implement right-side & operator for other & FactConjunction."""
        from django_datalog.facts import Fact  # Avoid circular import

        match other:
            case Fact():
                return FactConjunction([other] + list(self))
            case tuple() | FactConjunction():
                return FactConjunction(list(other) + list(self))
            case list():
                raise TypeError(
                    "Cannot use & operator between list and FactConjunction. "
                    "Lists represent disjunction (OR)."
                )
            case _:
                raise TypeError(
                    f"Cannot use & operator between {type(other).__name__} and FactConjunction."
                )


class FactModel(models.Model):
    """Abstract base model for storing datalog facts."""

    id = models.UUIDField(primary_key=True, default=uuid6.uuid7, editable=False)

    class Meta:
        abstract = True
        unique_together = (("subject", "object"),)


@dataclass(eq=False)  # Disable auto-generated __eq__
class Fact:
    """Base class for all datalog facts."""

    subject: Any
    object: Any
    _django_model: ClassVar[type[models.Model] | None]
    _is_inferred: ClassVar[bool] = False

    def __init_subclass__(cls, inferred=False, **kwargs):
        """Automatically generate Django models for fact storage and apply dataclass decorator."""
        super().__init_subclass__(**kwargs)

        # Apply dataclass decorator with unsafe_hash=True to the subclass
        cls = dataclass(unsafe_hash=True)(cls)

        # Set inferred flag
        cls._is_inferred = inferred

        # Only create Django model if not inferred
        if inferred:
            cls._django_model = None
        else:
            cls._django_model = cls._create_django_model()

    @classmethod
    def _create_django_model(cls):
        """Dynamically create a Django model for this fact type."""
        import sys

        # Generate model name
        model_name = f"{cls.__name__}Storage"

        # Get type annotations from the class
        try:
            type_hints = get_type_hints(cls)
        except (NameError, AttributeError):
            # Fallback to raw annotations if get_type_hints fails
            type_hints = getattr(cls, "__annotations__", {})

        if "subject" not in type_hints or "object" not in type_hints:
            raise ValueError(f"Fact {cls.__name__} must have subject and object type annotations")

        # Extract Django model types from Union annotations
        subject_model = cls._extract_django_model_from_annotation(type_hints["subject"])
        object_model = cls._extract_django_model_from_annotation(type_hints["object"])

        if not subject_model or not object_model:
            raise ValueError(
                f"Could not extract Django model types from {cls.__name__} annotations"
            )

        # Create Django model fields
        model_fields = {
            "subject": models.ForeignKey(subject_model, on_delete=models.CASCADE, related_name="+"),
            "object": models.ForeignKey(object_model, on_delete=models.CASCADE, related_name="+"),
            "__module__": cls.__module__,
        }

        # Create the Django model class
        django_model = type(model_name, (FactModel,), model_fields)

        # Inject the model into the fact's module so Django can find it
        fact_module = sys.modules[cls.__module__]
        setattr(fact_module, model_name, django_model)

        return django_model

    @classmethod
    def _extract_django_model_from_annotation(cls, type_annotation):
        """Extract Django model type from Union annotation like 'User | Var'."""
        if hasattr(type_annotation, "__args__"):
            # Handle Union types (User | Var)
            for arg_type in type_annotation.__args__:
                if hasattr(arg_type, "_meta") and hasattr(arg_type._meta, "app_label"):
                    return arg_type
        elif hasattr(type_annotation, "_meta") and hasattr(type_annotation._meta, "app_label"):
            # Direct Django model reference
            return type_annotation
        return None

    def __hash__(self):
        """Make facts hashable for use in sets."""
        # Use PKs for Django models, actual values for other types
        subject_key = getattr(self.subject, "pk", self.subject)
        object_key = getattr(self.object, "pk", self.object)
        return hash((type(self), subject_key, object_key))

    def __eq__(self, other):
        """Compare facts for equality."""
        if not isinstance(other, type(self)):
            return False

        # Use PKs for Django models, actual values for other types
        subject_key = getattr(self.subject, "pk", self.subject)
        other_subject_key = getattr(other.subject, "pk", other.subject)
        object_key = getattr(self.object, "pk", self.object)
        other_object_key = getattr(other.object, "pk", other.object)

        return subject_key == other_subject_key and object_key == other_object_key

    def __or__(
        self, other: Self | list[Self | FactConjunction] | FactConjunction
    ) -> list[Self | FactConjunction]:
        """Implement | operator for disjunction (OR logic)."""
        match other:
            case Fact():
                return [self, other]
            case list():
                return [self, *other]
            case tuple() | FactConjunction():
                return [self, other]
            case _:
                raise TypeError("Cannot use | operator between Fact and unsupported type.")

    def __and__(self, other: Self | FactConjunction) -> FactConjunction:
        """Implement & operator for conjunction (AND logic)."""
        match other:
            case Fact():
                return FactConjunction([self, other])
            case tuple() | FactConjunction():
                return FactConjunction([self] + list(other))
            case list():
                raise TypeError(
                    "Cannot use & operator between Fact and list. Lists represent disjunction (OR)."
                )
            case _:
                raise TypeError("Cannot use & operator between Fact and unsupported type.")

    def __ror__(
        self, other: list[Self | FactConjunction] | FactConjunction
    ) -> list[Self | FactConjunction]:
        """Implement right-side | operator for [Fact1, Fact2] | Fact3 or (Fact1, Fact2) | Fact3."""
        match other:
            case list():
                return [*other, self]
            case tuple() | FactConjunction():
                return [other, self]
            case _:
                raise TypeError(f"Cannot use | operator between {type(other).__name__} and Fact.")

    def __rand__(self, other: FactConjunction) -> FactConjunction:
        """Implement right-side & operator for (Fact1, Fact2) & Fact3."""
        match other:
            case tuple() | FactConjunction():
                return FactConjunction(list(other) + [self])
            case list():
                raise TypeError(
                    "Cannot use & operator between list and Fact. Lists represent disjunction (OR)."
                )
            case _:
                raise TypeError("Cannot use & operator between unsupported type and Fact.")


def store_facts(*facts: Fact) -> None:
    """Store facts in the database."""
    if not facts:
        return

    # Filter out inferred facts - they cannot be stored
    storable_facts = []
    for fact in facts:
        if type(fact)._is_inferred:
            raise ValueError(
                f"Cannot store inferred fact: {fact}. "
                f"Inferred facts are computed automatically from rules."
            )
        storable_facts.append(fact)

    if not storable_facts:
        return

    # Group facts by type for batch operations
    facts_by_type = {}
    for fact in storable_facts:
        fact_type = type(fact)
        if fact_type not in facts_by_type:
            facts_by_type[fact_type] = []
        facts_by_type[fact_type].append(fact)

    # Bulk create for each fact type
    for fact_type, fact_list in facts_by_type.items():
        django_model = fact_type._django_model
        model_instances = []

        for fact in fact_list:
            # Store Django model instances directly in ForeignKey fields
            model_instances.append(django_model(subject=fact.subject, object=fact.object))

        # Use ignore_conflicts to handle duplicates
        django_model.objects.bulk_create(model_instances, ignore_conflicts=True)


def retract_facts(*facts: Fact) -> None:
    """Remove facts from the database."""
    if not facts:
        return

    # Filter out inferred facts - they cannot be retracted
    retractable_facts = []
    for fact in facts:
        if type(fact)._is_inferred:
            raise ValueError(
                f"Cannot retract inferred fact: {fact}. "
                f"Inferred facts are computed automatically from rules."
            )
        retractable_facts.append(fact)

    if not retractable_facts:
        return

    # Group facts by type for batch operations
    facts_by_type = {}
    for fact in retractable_facts:
        fact_type = type(fact)
        if fact_type not in facts_by_type:
            facts_by_type[fact_type] = []
        facts_by_type[fact_type].append(fact)

    # Batch delete for each fact type
    for fact_type, fact_list in facts_by_type.items():
        django_model = fact_type._django_model

        for fact in fact_list:
            # Delete using Django model instances directly
            django_model.objects.filter(subject=fact.subject, object=fact.object).delete()
