"""
Fact system for djdatalog - handles fact definitions, storage, and retrieval.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, dataclass_transform

from asgiref.sync import sync_to_async
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


@dataclass_transform(eq_default=False)
@dataclass(eq=False)  # Disable auto-generated __eq__
class Fact:
    """Base class for all datalog facts.

    Decorated with ``@dataclass_transform`` so type checkers treat every
    subclass as a dataclass and synthesize an ``__init__`` from its annotated
    ``subject``/``object`` slots -- even though the actual ``@dataclass`` is
    applied dynamically in ``__init_subclass__``. That is what lets a typed
    ``Var[Employee]`` be checked against a ``subject: Term[Employee]`` slot.
    """

    subject: Any
    object: Any
    # Storage binding. Bind a fact to an explicit Django model with @store(Fact);
    # a fact with no binding (_django_model is None) is *inferred* — it has no
    # storage and is derived by rules. _subject_col/_object_col map the fact's
    # positions onto the bound model's columns; _source_where optionally restricts
    # which rows are facts; _readonly forbids store/retract.
    _django_model: ClassVar[type[models.Model] | None] = None
    _subject_col: ClassVar[str] = "subject"
    _object_col: ClassVar[str] = "object"
    _source_where: ClassVar[Any] = None
    _readonly: ClassVar[bool] = False

    def __init_subclass__(cls, **kwargs):
        """Apply the dataclass decorator. Storage is bound separately by @store.

        A fact bound with ``@store(<Fact>)`` is stored; an unbound fact is
        inferred (derived by rules, no storage). No model is generated.
        """
        super().__init_subclass__(**kwargs)
        cls = dataclass(unsafe_hash=True)(cls)

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
        self, other: Fact | list[Fact | FactConjunction] | FactConjunction
    ) -> list[Fact | FactConjunction]:
        """Implement | operator for disjunction (OR logic).

        ``other`` is any ``Fact`` (not just ``Self``): rule bodies compose
        different fact types, e.g. ``StaffOf(...) | (MemberOf(...) & Owns(...))``.
        """
        match other:
            case Fact():
                return [self, other]
            case list():
                return [self, *other]
            case tuple() | FactConjunction():
                return [self, other]
            case _:
                raise TypeError("Cannot use | operator between Fact and unsupported type.")

    def __and__(self, other: Fact | FactConjunction) -> FactConjunction:
        """Implement & operator for conjunction (AND logic).

        ``other`` is any ``Fact`` (not just ``Self``): a conjunction joins
        different fact types, e.g. ``MemberOf(u, c) & Owns(c, v)``.
        """
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
        self, other: list[Fact | FactConjunction] | FactConjunction
    ) -> list[Fact | FactConjunction]:
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


def store(fact_cls, *, subject="subject", object="object", where=None, readonly=False):
    """Bind a stored ``Fact`` to the explicit Django model that holds its rows.

    Decorate the storage model with the fact it stores::

        @store(WorksFor)
        class WorksForStorage(models.Model):
            subject = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="+")
            object = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="+")

            class Meta:
                constraints = [models.UniqueConstraint(fields=["subject", "object"], name="…")]

    ``subject``/``object`` map the fact's positions onto the model's columns
    (default ``"subject"``/``"object"``). ``where`` is an optional ``Q`` limiting
    which rows count as facts. ``readonly=True`` forbids ``store_facts`` /
    ``retract_facts`` — use it when the fact maps onto a table owned elsewhere.
    """
    def bind(model_cls):
        fact_cls._django_model = model_cls
        fact_cls._subject_col = subject
        fact_cls._object_col = object
        fact_cls._source_where = where
        fact_cls._readonly = readonly
        return model_cls

    return bind


def _col_value(column: str, value: Any) -> Any:
    """Value to write/filter for a mapped column: a pk for FK attnames, else the value."""
    return getattr(value, "pk", value) if column.endswith("_id") else value


def _require_writable_storage(fact_type: type) -> None:
    if fact_type._django_model is None:
        raise ValueError(
            f"{fact_type.__name__} has no storage; bind a model with @store({fact_type.__name__})."
        )
    if fact_type._readonly:
        raise ValueError(
            f"Cannot write {fact_type.__name__}: it is read-only "
            f"(its rows live in {fact_type._django_model.__name__})."
        )


def store_facts(*facts: Fact) -> None:
    """Store facts in the database."""
    if not facts:
        return

    storable_facts = list(facts)  # unbound (inferred) facts are caught per-type below

    if not storable_facts:
        return

    # Group facts by type for batch operations
    facts_by_type = {}
    for fact in storable_facts:
        fact_type = type(fact)
        if fact_type not in facts_by_type:
            facts_by_type[fact_type] = []
        facts_by_type[fact_type].append(fact)

    # Bulk create for each fact type, writing through the bound model's columns.
    for fact_type, fact_list in facts_by_type.items():
        _require_writable_storage(fact_type)
        django_model = fact_type._django_model
        subject_col, object_col = fact_type._subject_col, fact_type._object_col
        model_instances = [
            django_model(**{
                subject_col: _col_value(subject_col, fact.subject),
                object_col: _col_value(object_col, fact.object),
            })
            for fact in fact_list
        ]
        django_model.objects.bulk_create(model_instances, ignore_conflicts=True)


def retract_facts(*facts: Fact) -> None:
    """Remove facts from the database."""
    if not facts:
        return

    retractable_facts = list(facts)  # unbound (inferred) facts are caught per-type below

    if not retractable_facts:
        return

    # Group facts by type for batch operations
    facts_by_type = {}
    for fact in retractable_facts:
        fact_type = type(fact)
        if fact_type not in facts_by_type:
            facts_by_type[fact_type] = []
        facts_by_type[fact_type].append(fact)

    # Batch delete for each fact type, matching through the bound model's columns.
    for fact_type, fact_list in facts_by_type.items():
        _require_writable_storage(fact_type)
        django_model = fact_type._django_model
        subject_col, object_col = fact_type._subject_col, fact_type._object_col
        for fact in fact_list:
            django_model.objects.filter(**{
                subject_col: _col_value(subject_col, fact.subject),
                object_col: _col_value(object_col, fact.object),
            }).delete()


async def astore_facts(*facts: Fact) -> None:
    """Async counterpart of :func:`store_facts` (see it for semantics)."""
    await sync_to_async(store_facts, thread_sensitive=True)(*facts)


async def aretract_facts(*facts: Fact) -> None:
    """Async counterpart of :func:`retract_facts` (see it for semantics)."""
    await sync_to_async(retract_facts, thread_sensitive=True)(*facts)
