"""
Fact system for djdatalog - handles fact definitions, storage, and retrieval.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any, ClassVar, dataclass_transform

from asgiref.sync import sync_to_async
from django.db import models


def _key(value: Any) -> Any:
    """Comparison/hash key for a position value: a model's pk, or the value itself."""
    return getattr(value, "pk", value)


def _column_of(fact_type: type, position: str) -> str:
    """DB column backing a fact position (default: the position's own name)."""
    return fact_type._columns.get(position, position)


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

    A fact is an N-ary relation: its *positions* are its annotated fields, in
    order. Binary facts declare ``subject``/``object``; an N-ary fact declares
    whatever it needs, e.g. ``user``/``rank``/``vessel``. A position may hold an
    entity (a Django model / FK) or an arbitrary value (a string, a choice, …).

    Decorated with ``@dataclass_transform`` so type checkers synthesize an
    ``__init__`` from each subclass's annotated fields, even though ``@dataclass``
    is applied dynamically in ``__init_subclass__``.
    """

    # Storage binding. Bind a fact to an explicit Django model with @store(Fact);
    # a fact with no binding (_django_model is None) is *inferred* — no storage,
    # derived by rules. _columns maps each position (field) onto the bound model's
    # column (default: same name); _source_where optionally restricts which rows
    # are facts; _readonly forbids store/retract.
    _django_model: ClassVar[type[models.Model] | None] = None
    _columns: ClassVar[dict[str, str]] = {}
    _source_where: ClassVar[Any] = None
    _readonly: ClassVar[bool] = False
    _positions: ClassVar[tuple[str, ...]] = ()  # ordered field names (the relation's positions)

    def __init_subclass__(cls, **kwargs):
        """Apply the dataclass decorator and record the relation's positions.

        A fact bound with ``@store(<Fact>)`` is stored; an unbound fact is
        inferred (derived by rules, no storage). No model is generated.
        """
        super().__init_subclass__(**kwargs)
        cls = dataclass(unsafe_hash=True)(cls)
        cls._positions = tuple(f.name for f in fields(cls))

    def __hash__(self):
        """Hashable over all positions (pk for models, the value otherwise)."""
        return hash((type(self), *(_key(getattr(self, p)) for p in self._positions)))

    def __eq__(self, other):
        """Equal iff same type and every position matches (by pk / value)."""
        if type(self) is not type(other):
            return False
        return all(_key(getattr(self, p)) == _key(getattr(other, p)) for p in self._positions)

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


def store(fact_cls, *, columns=None, where=None, readonly=False, **column_kwargs):
    """Bind a stored ``Fact`` to the explicit Django model that holds its rows.

    Decorate the storage model with the fact it stores::

        @store(WorksFor)
        class WorksForStorage(models.Model):
            subject = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="+")
            object = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="+")

            class Meta:
                constraints = [models.UniqueConstraint(fields=["subject", "object"], name="…")]

    Each fact position (its annotated fields) maps onto a model column of the
    same name by default. To map onto an existing table whose columns differ,
    pass ``columns={"subject": "employee", "object": "company"}`` (or the same
    as keyword arguments: ``subject="employee"``). ``where`` is an optional ``Q``
    limiting which rows count as facts. ``readonly=True`` forbids ``store_facts``
    / ``retract_facts`` — use it when the fact maps onto a table owned elsewhere.
    """
    mapping = {**(columns or {}), **column_kwargs}

    def bind(model_cls):
        fact_cls._django_model = model_cls
        fact_cls._columns = mapping
        fact_cls._source_where = where
        fact_cls._readonly = readonly
        return model_cls

    return bind


def _col_value(column: str, value: Any) -> Any:
    """Value to write/filter for a mapped column: a pk for FK attnames, else the value."""
    return getattr(value, "pk", value) if column.endswith("_id") else value


def _row_kwargs(fact: Fact) -> dict[str, Any]:
    """Map a fact's positions onto its bound model's columns for write/filter."""
    fact_type = type(fact)
    kwargs = {}
    for position in fact_type._positions:
        column = _column_of(fact_type, position)
        kwargs[column] = _col_value(column, getattr(fact, position))
    return kwargs


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
        model_instances = [django_model(**_row_kwargs(fact)) for fact in fact_list]
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
        for fact in fact_list:
            django_model.objects.filter(**_row_kwargs(fact)).delete()


async def astore_facts(*facts: Fact) -> None:
    """Async counterpart of :func:`store_facts` (see it for semantics)."""
    await sync_to_async(store_facts, thread_sensitive=True)(*facts)


async def aretract_facts(*facts: Fact) -> None:
    """Async counterpart of :func:`retract_facts` (see it for semantics)."""
    await sync_to_async(retract_facts, thread_sensitive=True)(*facts)
