"""
Query system for djdatalog - handles querying facts with inference and optimization.
"""

import uuid
from collections.abc import Iterator
from dataclasses import fields
from typing import Any

from asgiref.sync import sync_to_async
from django.db.models import Q

from .facts import Fact, _column_of
from .optimizer import optimize_query, time_fact_execution
from .rules import (
    Rule,
    _binding_key,
    _instantiate_fact,
    _iter_all_bindings_multi,
    apply_targeted_rules,
    get_rules,
)
from .variables import Var, has_variable_references, substitute_variables_in_q


def _is_binary(fact_type) -> bool:
    """True for a classic binary relation (subject/object positions)."""
    return fact_type._positions == ("subject", "object")


def _positions(fact) -> tuple[str, ...]:
    """Ordered position names of a fact or fact type."""
    return fact._positions


def _model_relation_field(django_model, column: str) -> str | None:
    """Return the relation field name to ``select_related`` for a column, or None.

    A column that names a concrete FK loads its related instance (so
    where-constraints and hydration see a real object). An attname (``…_id``) or
    a plain value column has no relation field and is read as a raw value.
    """
    try:
        field = django_model._meta.get_field(column)
    except Exception:
        return None
    # Only the relation's own field name loads instances; its attname
    # (e.g. "company_id") reads a raw pk and must stay a value column.
    if getattr(field, "is_relation", False) and field.concrete and field.name == column:
        return column
    return None


def query(*fact_patterns: Fact, hydrate: bool = True) -> Iterator[dict[str, Any]]:
    """
    Query facts from the database and apply inference rules with intelligent optimization.

    This function automatically:
    1. Propagates constraints across variables with the same name
    2. Orders query execution by selectivity (most selective predicates first)
    3. Leverages database indexes and query optimization
    4. Records performance timing for optimization analysis

    Args:
        *fact_patterns: One or more fact patterns to match as a conjunction
        hydrate: If True (default), returns full model instances. If False, returns PKs only.

    Yields:
        Dictionary mapping variable names to their values (models or PKs based on hydrate)

    Example:
        # Query with automatic optimization and performance tracking
        results = query(
            ColleaguesOf(Var("emp1"), Var("emp2", where=Q(department="Engineering"))),
            WorksFor(Var("emp1"), Var("company", where=Q(is_active=True))),
            WorksFor(Var("emp2"), Var("company"))
        )
        # Constraints are automatically propagated:
        # - emp2 gets Q(department="Engineering") in all predicates
        # - company gets Q(is_active=True) in all predicates
        # - Query execution is ordered by selectivity
        # - Performance timing is automatically recorded
    """
    # Apply query optimization (constraint propagation + execution planning)
    optimized_patterns = optimize_query(list(fact_patterns))

    # Get the conjunction results using query-specific fact loading
    pk_results = _satisfy_conjunction_with_targeted_facts(optimized_patterns, {})

    if hydrate:
        # Collect all results first to batch hydration
        pk_results_list = list(pk_results)
        # Hydrate PKs to model instances (use original patterns for type info)
        yield from _hydrate_results(pk_results_list, list(fact_patterns))
    else:
        # Return PKs directly without hydration
        yield from pk_results


async def aquery(*fact_patterns: Fact, hydrate: bool = True) -> list[dict[str, Any]]:
    """Async counterpart of :func:`query`.

    Runs the (synchronous) query engine in Django's thread-sensitive executor
    so it shares the ORM connection context, and returns the results as a
    list. Use it from async views/tasks::

        results = await aquery(WorksFor(emp, company))

    Args:
        *fact_patterns: One or more fact patterns to match as a conjunction.
        hydrate: If True (default), returns full model instances; if False, PKs.

    Returns:
        A list of dictionaries mapping variable names to their values.
    """
    return await sync_to_async(_query_to_list, thread_sensitive=True)(fact_patterns, hydrate)


def _query_to_list(fact_patterns: tuple[Fact, ...], hydrate: bool) -> list[dict[str, Any]]:
    """Materialize the query generator (runs inside the sync executor)."""
    return list(query(*fact_patterns, hydrate=hydrate))


def as_queryset(pattern: Fact, *, on: str = "object", model=None):
    """Return a composable Django ``QuerySet`` for one side of an inferred query.

    Resolves ``pattern`` through the datalog engine and returns
    ``model.objects.filter(pk__in=<ids>)`` for the values bound at position
    ``on`` (``"subject"`` or ``"object"``). The result is a lazy queryset the
    caller can compose with the ORM, e.g. accessible vessels for a user::

        Vessel.objects.filter(pk__in=...)  # via
        qs = as_queryset(CanAccessVessel(user, Var("v")), on="object")
        qs = qs.filter(active=True).order_by("name")

    ``on`` names a position of the fact (``"subject"``/``"object"`` for a binary
    relation, any field for an N-ary one). ``model`` defaults to the Django model
    declared for that position. The matching ids are materialized once (cheap for
    bound queries); the returned queryset itself is not evaluated until the
    caller uses it.
    """
    if on not in type(pattern)._positions:
        raise ValueError(
            f"`on` must be a position of {type(pattern).__name__} "
            f"{type(pattern)._positions}, got {on!r}"
        )

    if model is None:
        model = _position_model_type(type(pattern), on)
        if model is None:
            raise ValueError(
                f"Could not infer a model for {type(pattern).__name__}.{on}; "
                f"pass model=... explicitly."
            )

    position = getattr(pattern, on)
    if isinstance(position, Var):
        ids = {row[position.name] for row in query(pattern, hydrate=False)}
    else:
        # Position is already concrete - the id set is just that value.
        ids = {getattr(position, "pk", position)}

    return model.objects.filter(pk__in=ids)


async def aas_queryset(pattern: Fact, *, on: str = "object", model=None):
    """Async counterpart of :func:`as_queryset` (builds the queryset off-thread)."""
    return await sync_to_async(as_queryset, thread_sensitive=True)(pattern, on=on, model=model)


_MISSING = object()


def first(*fact_patterns: Fact, hydrate: bool = True) -> dict[str, Any] | None:
    """Return the first result of a query, or ``None`` — stopping at the match.

    ``query`` is lazy, so this consumes it only up to the first binding: once a
    match is found derivation stops and the remaining results are never
    computed. Use it when one answer is enough::

        row = first(WorksFor(alice, Var("company")))
    """
    pk_result = next(iter(query(*fact_patterns, hydrate=False)), None)
    if pk_result is None:
        return None
    if not hydrate:
        return pk_result
    # Hydrate only the one result we kept (not the whole set).
    return next(iter(_hydrate_results([pk_result], list(fact_patterns))), pk_result)


def exists(*fact_patterns: Fact) -> bool:
    """Return ``True`` as soon as the query has at least one result.

    The common access-check shape — ``if exists(CanAccessVessel(user, vessel)):
    ...`` — without building model instances (``hydrate=False``) or computing
    any result beyond the first.
    """
    return next(iter(query(*fact_patterns, hydrate=False)), _MISSING) is not _MISSING


async def afirst(*fact_patterns: Fact, hydrate: bool = True) -> dict[str, Any] | None:
    """Async counterpart of :func:`first`."""
    return await sync_to_async(_first_to_value, thread_sensitive=True)(fact_patterns, hydrate)


async def aexists(*fact_patterns: Fact) -> bool:
    """Async counterpart of :func:`exists`."""
    return await sync_to_async(exists, thread_sensitive=True)(*fact_patterns)


def _first_to_value(fact_patterns: tuple[Fact, ...], hydrate: bool) -> dict[str, Any] | None:
    """Run :func:`first` inside the sync executor (helper for :func:`afirst`)."""
    return first(*fact_patterns, hydrate=hydrate)


def _freedom_score(condition: Fact, bindings: dict[str, Any]) -> float:
    """How much freedom a condition still has given the current bindings.

    Lower means fewer open positions, so solve it first. A fixed position — a
    concrete value, or a variable already bound by an earlier condition — adds 0.
    A free variable adds 1.0; a free variable carrying a literal ``where`` adds
    only 0.5, since it narrows in the DB. This counts *open* positions rather
    than summing bound points, so a high-arity condition does not jump the queue
    just because it has more bound positions: WorksFor(alice, Var) and
    Crew(alice, master, Var) both have one open position, so they rank together.
    """
    freedom = 0.0
    for position in condition._positions:
        value = getattr(condition, position)
        if not isinstance(value, Var) or value.name in bindings:
            continue  # fixed position: no freedom
        freedom += 0.5 if value.where is not None else 1.0
    return freedom


def _satisfy_conjunction_with_targeted_facts(conditions, bindings, original_conditions=None) -> Iterator[dict[str, Any]]:
    """Satisfy a conjunction using targeted fact loading - only load facts relevant to the query."""
    if original_conditions is None:
        original_conditions = conditions[:]

    # Check if we can optimize this query with automatic ORM conversion
    # PERFORMANCE NOTE: Auto-converts to pure Django ORM when possible (up to 92% query reduction)
    # SECURITY: Uses Django ORM exclusively - NO SQL injection risk
    if not bindings:
        try:
            yield from _try_automatic_orm_conversion(original_conditions)
            return
        except (NotImplementedError, ValueError, TypeError, AttributeError):
            # Fall back to original approach if ORM conversion fails
            # Common reasons: complex patterns, missing models, unsupported constraints
            pass

    if not conditions:
        # All conditions satisfied - now validate cross-variable constraints
        if _validate_cross_variable_constraints(original_conditions, bindings):
            yield bindings
        return

    # Solve the least-free condition next. The engine reloads each later
    # condition once per binding of the earlier ones (bound variables are not
    # pushed into the DB, only filtered in Python), so putting a low-fan-out
    # condition first keeps the broad relations from being reloaded many times.
    # AND is commutative, so reordering never changes the result set.
    def rank(i):  # fewest open positions first; ties keep original order (stable)
        return (_freedom_score(conditions[i], bindings), i)

    index = min(range(len(conditions)), key=rank)
    condition = conditions[index]
    remaining = conditions[:index] + conditions[index + 1:]

    # Get facts relevant to this specific condition (stored + inferred), lazily
    # so a consumer that stops early (exists/first) short-circuits derivation.
    relevant_facts = _iter_facts_for_pattern(condition)


    # Query against the targeted fact set (skip cross-variable constraint checking during unification)
    for result in _query_against_facts(condition, relevant_facts, bindings, skip_cross_var_constraints=True):
        new_bindings = _unify_bindings(bindings, result)
        if new_bindings is not None:
            yield from _satisfy_conjunction_with_targeted_facts(remaining, new_bindings, original_conditions)


def _get_facts_for_pattern(
    pattern: Fact,
    _resolving: frozenset | None = None,
    _memo: dict | None = None,
) -> list[Fact]:
    """Eager list of facts (stored + inferred) for a pattern.

    Callers that need the full extension (fact-base building) use this; the
    lazy, short-circuitable form is :func:`_iter_facts_for_pattern`.
    """
    return list(_iter_facts_for_pattern(pattern, _resolving, _memo))


def _iter_facts_for_pattern(
    pattern: Fact,
    _resolving: frozenset | None = None,
    _memo: dict | None = None,
):
    """Lazily yield facts (stored, then inferred) matching ``pattern``'s type.

    ``_resolving`` holds the inferred fact types currently being resolved so
    recursive rules terminate; ``_memo`` caches each inferred type's extension
    for one top-level query.

    For a non-recursive relation the inferred facts are produced lazily
    (goal-directed rule specialization + a streaming join), so a consumer that
    stops after the first result — ``exists``/``first`` — never forces the whole
    extension. A recursive relation falls back to the eager fixpoint, because a
    transitive closure cannot be short-circuited.
    """
    if _resolving is None:
        _resolving = frozenset()
    if _memo is None:
        _memo = {}

    # 1. Stored facts first.
    yield from _load_stored_facts_for_pattern(pattern)

    # 2. Rules that can generate this fact type.
    relevant_rules = [r for r in get_rules() if type(r.head) is type(pattern)]
    if not relevant_rules:
        return

    resolving = _resolving | {type(pattern)}
    relation_recursive = any(
        any(type(condition) in resolving for condition in rule.body) for rule in relevant_rules
    )
    if relation_recursive:
        yield from _apply_rules_with_hidden_variables(relevant_rules, pattern, _resolving, _memo)
    else:
        yield from _iter_inferred_lazy(relevant_rules, pattern, _resolving, _memo)


def _iter_inferred_lazy(
    rules, target_pattern: Fact, _resolving: frozenset = frozenset(), _memo: dict | None = None
):
    """Lazily derive facts for a non-recursive relation (streaming counterpart
    of :func:`_apply_rules_with_hidden_variables`).

    Builds the same targeted fact base and applies the same goal-directed rule
    specialization, but enumerates each rule's body bindings through a streaming
    join and yields matching head facts as they are found (deduped by pk), so
    the derivation stops as soon as the consumer does.
    """
    if _memo is None:
        _memo = {}
    targeted_facts = _build_targeted_fact_base_for_rules(rules, target_pattern, _resolving, _memo)
    eval_rules = (
        [_specialize_rule(rule, target_pattern) for rule in rules]
        if _target_has_concrete_position(target_pattern)
        else rules
    )
    target_type = type(target_pattern)
    seen: set = set()
    for rule in eval_rules:
        sources = [targeted_facts] * len(rule.body)
        for binding in _iter_all_bindings_multi(rule.body, sources):
            try:
                fact = _instantiate_fact(rule.head, binding)
            except Exception:
                continue
            if fact is None or type(fact) is not target_type:
                continue
            key = (target_type, *(_binding_key(getattr(fact, p)) for p in fact._positions))
            if key not in seen:
                seen.add(key)
                yield fact


def _load_stored_facts_for_pattern(pattern: Fact) -> list[Fact]:
    """Load stored facts from the bound model that match a specific fact pattern."""
    try:
        fact_class = type(pattern)

        # Inferred (unbound) facts have no storage to load from.
        if fact_class._django_model is None:
            return []

        django_model = fact_class._django_model

        query_params, q_objects = _fact_to_django_query(pattern)
        queryset = django_model.objects.all()
        # A fact mapped onto an existing table may restrict which rows are facts.
        if fact_class._source_where is not None:
            queryset = queryset.filter(fact_class._source_where)
        queryset = queryset.filter(**query_params)
        for q_obj in q_objects:
            queryset = queryset.filter(q_obj)

        # Per position: an FK column loads its related instance (so
        # where-constraints and hydration see a real object); a value column or
        # an attname (…_id) reads the raw value. Facts unify by pk, so either
        # form is sound.
        relation_positions = {}  # position -> relation field to select_related
        value_positions = {}  # position -> raw column name
        for position in fact_class._positions:
            column = _column_of(fact_class, position)
            relation_field = _model_relation_field(django_model, column)
            if relation_field is not None:
                relation_positions[position] = relation_field
            else:
                value_positions[position] = column

        if relation_positions:
            queryset = queryset.select_related(*relation_positions.values())
            facts = []
            for instance in queryset:
                values = {p: getattr(instance, f) for p, f in relation_positions.items()}
                values.update({p: getattr(instance, c) for p, c in value_positions.items()})
                facts.append(fact_class(**values))
            return facts

        columns = {p: _column_of(fact_class, p) for p in fact_class._positions}
        return [
            fact_class(**{p: row[c] for p, c in columns.items()})
            for row in queryset.values(*columns.values())
        ]

    except (AttributeError, Exception):
        # If the fact has no bound model or the query fails, return empty.
        return []


def _specialize_rule(rule: Rule, target_pattern: Fact) -> Rule:
    """Bind a rule's head (and body) to the query's concrete positions.

    Turns ``Colleague(a, b) :- WorksFor(a, c) & WorksFor(b, c)`` queried as
    ``Colleague(alice, Var)`` into ``Colleague(alice, b) :- WorksFor(alice, c)
    & WorksFor(b, c)``. Evaluation then derives only the answer rows
    (``Colleague(alice, *)``) instead of the whole relation, so a bound query
    costs O(answer) rather than O(neighbourhood²).
    """
    head_sub = _unify_head_with_target(rule.head, target_pattern)
    new_head = _apply_head_sub_to_condition(rule.head, head_sub)
    new_body = [_apply_head_sub_to_condition(condition, head_sub) for condition in rule.body]
    return Rule(head=new_head, body=new_body)


def _apply_rules_with_hidden_variables(
    rules, target_pattern: Fact, _resolving: frozenset = frozenset(), _memo: dict | None = None
) -> list[Fact]:
    """Apply rules using hidden variables to avoid bulk loading - reuse existing rule system."""
    if _memo is None:
        _memo = {}
    # Create a targeted fact base by loading only facts needed for these specific rules
    targeted_facts = _build_targeted_fact_base_for_rules(rules, target_pattern, _resolving, _memo)

    # Specialize the rules to the query's bound positions so derivation is
    # goal-directed: only answer rows are produced, not the whole relation.
    # This is only sound when the relation is NOT recursive - specializing a
    # recursive relation's base case to the bound value starves the recursive
    # case of the intermediate facts it needs. If any rule for this head is
    # recursive, evaluate them all generically (the closure is still correct;
    # goal-directed recursion is a separate, harder optimization).
    resolving = _resolving | {type(target_pattern)}
    relation_is_recursive = any(
        any(type(condition) in resolving for condition in rule.body) for rule in rules
    )
    if _target_has_concrete_position(target_pattern) and not relation_is_recursive:
        eval_rules = [_specialize_rule(rule, target_pattern) for rule in rules]
    else:
        eval_rules = rules

    # Apply existing rule system to the targeted fact base
    inferred_facts = apply_targeted_rules(eval_rules, targeted_facts)

    # Filter to only return facts of the target pattern type
    target_type = type(target_pattern)
    return [fact for fact in inferred_facts if type(fact) is target_type]


def _free_inferred_pattern(fact_type: type) -> Fact:
    """Build an all-variable pattern for an inferred fact type (its full extension)."""
    return fact_type(**{position: Var(f"_{position}") for position in fact_type._positions})


def _target_has_concrete_position(pattern: Fact) -> bool:
    """True if the query pins any position to a concrete value."""
    return any(not isinstance(getattr(pattern, p), Var) for p in pattern._positions)


def _unify_head_with_target(head: Fact, target: Fact) -> dict[str, Any]:
    """Map rule-head variable names to the target pattern's value at that position."""
    substitution = {}
    for position in head._positions:
        head_value = getattr(head, position)
        if isinstance(head_value, Var):
            substitution[head_value.name] = getattr(target, position)
    return substitution


def _apply_head_sub_to_condition(condition: Fact, head_sub: dict[str, Any]) -> Fact:
    """Rewrite a body condition's head variables to the target's values."""

    def build(pos):
        if isinstance(pos, Var):
            return head_sub.get(pos.name, pos)
        return pos

    return type(condition)(
        **{p: build(getattr(condition, p)) for p in condition._positions}
    )


def _canonicalize_position(pos, head_sub: dict[str, Any]):
    """Resolve a condition position to ('const', value) or ('var', name, where).

    Head variables are rewritten to the target's value (a concrete value pins
    the position; a target variable keeps it free under that variable's name).
    """
    if isinstance(pos, Var):
        mapped = head_sub.get(pos.name, pos)
        if isinstance(mapped, Var):
            return ("var", mapped.name, pos.where)
        return ("const", mapped)
    return ("const", pos)


def _bound_score(condition: Fact, head_sub: dict[str, Any], env: dict[str, set]) -> int:
    """How many of this condition's positions are already bound (const or in env)."""
    score = 0
    for position in condition._positions:
        canon = _canonicalize_position(getattr(condition, position), head_sub)
        if canon[0] == "const" or (canon[0] == "var" and canon[1] in env):
            score += 1
    return score


def _sip_load_pattern(condition: Fact, head_sub: dict[str, Any], env: dict[str, set]) -> Fact:
    """Build a stored-fact load pattern with head substitution + `pk__in` pushdown."""

    def build(pos):
        canon = _canonicalize_position(pos, head_sub)
        if canon[0] == "const":
            return canon[1]
        _, name, where = canon
        constraint = where
        if name in env:
            in_q = Q(pk__in=list(env[name]))
            constraint = in_q if constraint is None else (constraint & in_q)
        return Var(name, where=constraint)

    return type(condition)(
        **{p: build(getattr(condition, p)) for p in condition._positions}
    )


def _gather_env(
    condition: Fact, rows: list[Fact], head_sub: dict[str, Any], env: dict[str, set]
) -> None:
    """Record the pk values each join variable took, intersecting with prior candidates."""
    for attr in condition._positions:
        canon = _canonicalize_position(getattr(condition, attr), head_sub)
        if canon[0] != "var":
            continue
        name = canon[1]
        values = {_binding_key(getattr(r, attr)) for r in rows}
        env[name] = values if name not in env else (env[name] & values)


def _build_targeted_fact_base_for_rules(
    rules, target_pattern: Fact, _resolving: frozenset = frozenset(), _memo: dict | None = None
) -> list[Fact]:
    """Build a targeted fact base for the rules that derive ``target_pattern``.

    - Inferred body conditions are resolved *transitively* (their stored facts
      plus their own rules) so inference chains across rule levels; a condition
      whose type is already being resolved is left to the fixpoint (recursion).
    - When the query pins a position (a concrete subject/object), stored body
      conditions are loaded with sideways-information-passing: bound positions
      are pushed into the DB filter and join-variable values gathered from one
      condition constrain (`pk__in`) the next, so the base stays proportional to
      the query's neighbourhood instead of the whole relation.
    """
    if _memo is None:
        _memo = {}
    target_type = type(target_pattern)
    resolving = _resolving | {target_type}
    use_sip = _target_has_concrete_position(target_pattern)

    targeted_facts = []

    for rule in rules:
        head_sub = _unify_head_with_target(rule.head, target_pattern) if use_sip else {}
        # Pushing the query's head bindings into a recursive rule's body is
        # unsound: the fixpoint re-instantiates the head with intermediate
        # values, so its conditions must see the full relation. Only push
        # bindings (SIP / goal-directed sub-resolution) into non-recursive rules.
        rule_is_recursive = any(type(c) in resolving for c in rule.body)
        pushdown = use_sip and not rule_is_recursive

        # 1) Inferred conditions: resolve transitively. When the rule is bound,
        # resolve the *substituted* condition (goal-directed) so chained
        # inference stays proportional to the query; otherwise resolve the full
        # extension once and memoize it by type.
        for condition in rule.body:
            condition_type = type(condition)
            if condition_type._django_model is not None:
                continue  # stored condition - handled below, not derived
            if condition_type in resolving:
                continue  # recursive reference - grown by the fixpoint
            sub_condition = _apply_head_sub_to_condition(condition, head_sub)
            if pushdown and _target_has_concrete_position(sub_condition):
                targeted_facts.extend(_get_facts_for_pattern(sub_condition, resolving, _memo))
            else:
                if condition_type not in _memo:
                    _memo[condition_type] = _get_facts_for_pattern(
                        _free_inferred_pattern(condition_type), resolving, _memo
                    )
                targeted_facts.extend(_memo[condition_type])

        # 2) Stored conditions (those bound to a model).
        stored = [c for c in rule.body if type(c)._django_model is not None]
        if pushdown:
            env: dict[str, set] = {}
            remaining = stored[:]
            while remaining:
                # Load the most-bound condition next so bindings propagate outward.
                remaining.sort(key=lambda c: _bound_score(c, head_sub, env), reverse=True)
                condition = remaining.pop(0)
                try:
                    rows = _load_stored_facts_for_pattern(
                        _sip_load_pattern(condition, head_sub, env)
                    )
                except Exception:
                    rows = _load_stored_facts_for_pattern(
                        _create_targeted_condition(condition, target_pattern)
                    )
                targeted_facts.extend(rows)
                _gather_env(condition, rows, head_sub, env)
        else:
            for condition in stored:
                targeted_condition = _create_targeted_condition(condition, target_pattern)
                targeted_facts.extend(_load_stored_facts_for_pattern(targeted_condition))

    # Remove duplicates
    seen = set()
    unique_facts = []
    for fact in targeted_facts:
        fact_key = (type(fact), *(_binding_key(getattr(fact, p)) for p in fact._positions))
        if fact_key not in seen:
            seen.add(fact_key)
            unique_facts.append(fact)

    return unique_facts


def _create_targeted_condition(condition: Fact, target_pattern: Fact) -> Fact:
    """Create a targeted version of a rule condition with hidden variables for unbound vars."""
    condition_class = type(condition)

    # For a variable that does not appear in the target pattern, substitute a
    # unique hidden variable so the existing system treats it as unconstrained.
    values = {}
    for position in condition._positions:
        value = getattr(condition, position)
        if isinstance(value, Var) and not _variable_in_pattern(value.name, target_pattern):
            value = Var(f"hidden_{uuid.uuid4().hex[:8]}")
        values[position] = value

    return condition_class(**values)


def _variable_in_pattern(var_name: str, pattern: Fact) -> bool:
    """Check if a variable name appears in a fact pattern."""
    for position in pattern._positions:
        value = getattr(pattern, position)
        if isinstance(value, Var) and value.name == var_name:
            return True
    return False


def _position_model_type(fact_type, position: str):
    """Django model type declared for a fact position, or None for a value position."""
    field = next((f for f in fields(fact_type) if f.name == position), None)
    if field is None:
        raise ValueError(f"Fact type {fact_type} has no position {position!r}")
    return _extract_model_type_from_annotation(field.type)


def _extract_model_type_from_annotation(type_annotation):
    """Extract Django model type from type annotation like 'Person | Var'."""
    if hasattr(type_annotation, "__args__"):
        # Handle Union types (Person | Var)
        for arg_type in type_annotation.__args__:
            if hasattr(arg_type, "_meta") and hasattr(arg_type._meta, "app_label"):
                # This looks like a Django model
                return arg_type
    elif hasattr(type_annotation, "_meta") and hasattr(type_annotation._meta, "app_label"):
        # Direct Django model reference
        return type_annotation

    return None


def _query_against_facts(pattern: Fact, facts: list[Fact], existing_bindings: dict[str, Any] = None, skip_cross_var_constraints: bool = False) -> Iterator[dict[str, Any]]:
    """Query a pattern against a set of in-memory facts with timing feedback."""
    if existing_bindings is None:
        existing_bindings = {}

    with time_fact_execution(pattern):
        pattern_type = type(pattern)
        # Yield matches as they are found (not collect-then-yield) so a consumer
        # that stops early stops iterating `facts` — which, when `facts` is the
        # lazy _iter_facts_for_pattern generator, short-circuits derivation.
        for fact in facts:
            if type(fact) is pattern_type:
                substitution = _unify_fact_pattern(
                    pattern, fact, existing_bindings, skip_cross_var_constraints
                )
                if substitution is not None:
                    yield substitution


def _unify_fact_pattern(pattern: Fact, concrete_fact: Fact, existing_bindings: dict[str, Any] = None, skip_cross_var_constraints: bool = False) -> dict[str, Any] | None:
    """Unify a fact pattern (with variables) against a concrete fact.

    Iterates over every position of the relation (subject/object for a binary
    fact, arbitrary fields for an N-ary one). A concrete position must match by
    pk; a variable position binds to the concrete value and, when it carries a
    ``where`` constraint, that constraint must hold.
    """
    if existing_bindings is None:
        existing_bindings = {}

    substitution = {}

    for position in pattern._positions:
        pattern_value = getattr(pattern, position)
        concrete_value = getattr(concrete_fact, position)

        if not isinstance(pattern_value, Var):
            if _binding_key(pattern_value) != _binding_key(concrete_value):
                return None  # Concrete position does not match (compare by pk)
            continue

        # Variable position: check its constraint, then bind.
        if pattern_value.where is not None:
            if skip_cross_var_constraints and has_variable_references(pattern_value.where):
                pass  # Defer cross-variable constraints to a later validation pass
            else:
                combined_bindings = {**existing_bindings, **substitution}
                if not _check_q_constraint_with_bindings(
                    concrete_value, pattern_value.where, combined_bindings
                ):
                    return None  # Value does not meet the constraint

        var_name = pattern_value.name
        value = concrete_value.pk if hasattr(concrete_value, "pk") else concrete_value
        if var_name in substitution and substitution[var_name] != value:
            return None  # Conflicting binding for the same variable
        substitution[var_name] = value

    return substitution


def _validate_cross_variable_constraints(conditions: list[Fact], bindings: dict[str, Any]) -> bool:
    """Validate all cross-variable constraints after full conjunction is satisfied."""
    # Collect all (condition, position) pairs carrying a cross-variable constraint.
    constrained_positions = []
    for condition in conditions:
        for position in condition._positions:
            value = getattr(condition, position)
            if isinstance(value, Var) and value.where and has_variable_references(value.where):
                constrained_positions.append((condition, position))

    # If no cross-variable constraints, validation passes
    if not constrained_positions:
        return True

    for pattern, position in constrained_positions:
        var = getattr(pattern, position)
        if var.name in bindings:
            model_type = _extract_model_type_from_annotation(
                pattern.__dataclass_fields__[position].type
            )
            # Get the model instance from bindings (might need hydration)
            model_instance = _get_model_instance_from_binding(bindings[var.name], model_type)
            if not _check_q_constraint_with_bindings(model_instance, var.where, bindings):
                return False

    return True


def _get_model_instance_from_binding(binding_value, model_type):
    """Get model instance from binding value, handling both PKs and model instances."""
    if hasattr(binding_value, 'pk'):
        # Already a model instance
        return binding_value
    else:
        # This is a PK - hydrate to model instance
        if model_type:
            try:
                return model_type.objects.get(pk=binding_value)
            except (model_type.DoesNotExist, Exception):
                # If hydration fails, return the PK value
                return binding_value
        else:
            # No model type info - return the PK value
            return binding_value


def _check_q_constraint(model_instance, q_constraint) -> bool:
    """Check if a model instance satisfies a Q constraint."""
    return _check_q_constraint_with_bindings(model_instance, q_constraint, {})


def _check_q_constraint_with_bindings(model_instance, q_constraint, bindings: dict[str, Any]) -> bool:
    """Check if a model instance satisfies a Q constraint, substituting variables from bindings."""
    try:
        # If constraint has variable references, substitute them first
        if has_variable_references(q_constraint):
            # Convert PK values back to model instances for constraint checking
            model_bindings = {}
            for var_name, pk_value in bindings.items():
                # Try to get the model instance from the pk
                try:
                    if hasattr(pk_value, 'pk'):
                        # Already a model instance
                        model_bindings[var_name] = pk_value
                    else:
                        # This is a PK value - we need to find the appropriate model
                        # For now, we'll use the PK value directly and let Django handle it
                        # This works because Django can use PKs directly in filters
                        model_bindings[var_name] = pk_value
                except Exception:
                    # If we can't resolve the variable, constraint fails
                    return False

            # Substitute variables in the constraint
            resolved_constraint = substitute_variables_in_q(q_constraint, model_bindings)

            # Check if any variables remain unresolved
            if has_variable_references(resolved_constraint):
                # Can't evaluate constraint yet - variables still unbound
                return True  # Defer constraint checking
        else:
            resolved_constraint = q_constraint

        # Convert the Q constraint to a filter and check if the instance matches
        queryset = model_instance.__class__.objects.filter(resolved_constraint)
        # Check if this specific instance matches the constraint
        result = queryset.filter(pk=model_instance.pk).exists()

        return result
    except Exception:
        # If there's any error with the constraint check, assume it fails
        return False


def _satisfy_conjunction(conditions, bindings) -> Iterator[dict[str, Any]]:
    """Satisfy a conjunction of conditions with the given variable bindings."""
    if not conditions:
        yield bindings
        return

    # Take the first condition
    condition, *remaining = conditions

    # Generate all possible solutions for this condition
    for result in _query_single_fact(condition):
        # Try to unify with existing bindings
        new_bindings = _unify_bindings(bindings, result)
        if new_bindings is not None:
            # Recursively solve remaining conditions
            yield from _satisfy_conjunction(remaining, new_bindings)


def _query_single_fact(fact_pattern: Fact) -> Iterator[dict[str, Any]]:
    """Query a single fact pattern from the database with timing feedback."""
    with time_fact_execution(fact_pattern):
        fact_class = type(fact_pattern)

        # Handle inferred (unbound) facts - they must be computed via rules
        if fact_class._django_model is None:
            # For inferred facts, get all facts (stored + inferred) and query against them
            relevant_facts = _get_facts_for_pattern(fact_pattern)
            yield from _query_against_facts(fact_pattern, relevant_facts)
            return

        # Handle stored facts - query database directly
        django_model = fact_class._django_model

        # Convert fact pattern to Django query
        query_params, q_objects = _fact_to_django_query(fact_pattern)

        # Build the queryset with both filter params and Q objects
        queryset = django_model.objects.filter(**query_params)
        for q_obj in q_objects:
            queryset = queryset.filter(q_obj)

        # Query the database with values() to get PKs
        columns = [_column_of(fact_class, p) for p in fact_class._positions]
        for values_dict in queryset.values(*columns):
            substitution = _django_result_to_substitution(fact_pattern, values_dict)
            yield substitution


def _fact_to_django_query(fact: Fact) -> tuple[dict[str, Any], list[Any]]:
    """
    Convert a fact to Django query parameters and Q objects.

    Returns:
        tuple: (query_params, q_objects) where q_objects are constraints for Vars
    """
    fact_class = type(fact)

    query_params = {}
    q_objects = []

    for name in fact_class._positions:
        position = getattr(fact, name)
        # For a fact mapped onto an existing table this is its real column
        # (e.g. "employee_id"); for dedicated storage it is the position name.
        column = _column_of(fact_class, name)
        if not isinstance(position, Var):
            # Concrete position filters on the column; a mapped FK attname
            # (…_id) takes the pk, a plain FK field takes the instance.
            query_params[column] = _col_filter_value(column, position)
        elif position.where is not None and not has_variable_references(position.where):
            # Prefix the Var's constraint onto the relation behind the column.
            q_objects.append(_prefix_q_object(position.where, _relation_prefix(column)))

    return query_params, q_objects


def _col_filter_value(column: str, value: Any) -> Any:
    """Value to filter a concrete position by.

    Dedicated storage keeps the FK field (``subject``/``object``) → filter by the
    instance (unchanged behavior). A column-mapped fact filters a raw pk column
    (``id``/``employee_id``) → filter by the pk.
    """
    return value if column in ("subject", "object") else getattr(value, "pk", value)


def _relation_prefix(column: str) -> str:
    """Relation name for prefixing a Var's ``where`` onto a column.

    A mapped FK attname like ``employee_id`` reaches the related model through
    ``employee__…``, so strip a trailing ``_id``; other columns are used as is.
    """
    return column[:-3] if column.endswith("_id") else column


def _prefix_q_object(q_obj, prefix: str):
    """Prefix all field lookups in a Q object with the given prefix."""
    if hasattr(q_obj, "children"):
        # Q object with children (AND/OR operations)
        new_q = Q()
        new_q.connector = q_obj.connector
        new_q.negated = q_obj.negated

        for child in q_obj.children:
            if isinstance(child, tuple):
                # This is a field lookup: (field_name, value)
                field_name, value = child
                new_field_name = f"{prefix}__{field_name}"
                new_q.children.append((new_field_name, value))
            else:
                # This is another Q object - recurse
                new_q.children.append(_prefix_q_object(child, prefix))
        return new_q
    else:
        # Simple Q object - create a new one with prefixed fields
        new_q = Q()
        new_q.connector = q_obj.connector
        new_q.negated = q_obj.negated
        for child in q_obj.children:
            if isinstance(child, tuple):
                field_name, value = child
                new_field_name = f"{prefix}__{field_name}"
                new_q.children.append((new_field_name, value))
        return new_q


def _django_result_to_substitution(fact: Fact, values_dict: dict) -> dict[str, Any]:
    """Convert Django query result to variable substitution."""
    fact_class = type(fact)
    substitution = {}
    for name in fact_class._positions:
        position = getattr(fact, name)
        if isinstance(position, Var):
            # values_dict holds the column value (a pk for FK columns)
            substitution[position.name] = values_dict[_column_of(fact_class, name)]
    return substitution


def _has_cross_variable_constraints(conditions: list[Fact]) -> bool:
    """Check if any conditions have cross-variable constraints."""
    for condition in conditions:
        for position in condition._positions:
            value = getattr(condition, position)
            if isinstance(value, Var) and value.where and has_variable_references(value.where):
                return True
    return False


def _try_automatic_orm_conversion(conditions: list[Fact]) -> Iterator[dict[str, Any]]:
    """Try to automatically convert django-datalog query to optimized Django ORM.

    PERFORMANCE IMPACT: Can achieve significant query reduction through advanced analysis
    SECURITY STATUS: ✅ SECURE - Uses Django ORM exclusively

    Uses advanced AST analysis and execution planning to handle complex patterns.
    Falls back to original approach only when analysis fails completely.
    """

    # Only handle stored facts (bound to a model).
    for condition in conditions:
        fact_class = type(condition)
        if fact_class._django_model is None:
            raise NotImplementedError("ORM conversion only supports stored facts")
        # The advanced analyzer assumes a binary relation with literal
        # subject/object fields; N-ary or column-mapped facts go through the
        # column-aware loader instead.
        if not _is_binary(fact_class) or fact_class._columns:
            raise NotImplementedError("ORM conversion only supports binary, non-mapped facts")
        # The advanced analyzer models variable positions only; it does not
        # apply a concrete (non-Var) subject/object as a filter. Defer such
        # patterns to the fallback loader, which filters concrete values
        # correctly, to avoid returning unfiltered rows.
        if not isinstance(condition.subject, Var) or not isinstance(condition.object, Var):
            raise NotImplementedError("ORM conversion only supports variable positions")

    # Try advanced AST-based analysis first
    try:
        from .query_analyzer import build_advanced_orm_query

        advanced_queryset = build_advanced_orm_query(conditions)
        if advanced_queryset is not None:
            # Execute advanced query and convert results
            yield from _execute_advanced_orm_query(advanced_queryset, conditions)
            return
    except Exception:
        # Advanced analysis failed, try simple approach
        pass

    # All ORM optimizations failed, use original approach
    raise NotImplementedError("Advanced analysis could not optimize this query pattern")


def _execute_advanced_orm_query(queryset, conditions: list[Fact]) -> Iterator[dict[str, Any]]:
    """Execute the advanced ORM query and convert results back to django-datalog format."""

    # The advanced analyzer returns instances from the primary fact storage model
    # We need to reconstruct the full variable bindings by looking up related facts

    for primary_instance in queryset:
        # The primary instance gives us some variables
        # We need to find the values for all variables across all conditions

        result = {}

        # Extract variables from the primary instance
        for condition in conditions:
            fact_storage_model = type(condition)._django_model

            if isinstance(primary_instance, fact_storage_model):
                # This is the primary fact - extract its variables
                if isinstance(condition.subject, Var):
                    var_name = condition.subject.name
                    result[var_name] = primary_instance.subject.pk

                if isinstance(condition.object, Var):
                    var_name = condition.object.name
                    result[var_name] = primary_instance.object.pk

                break  # Found the primary fact

        # Use annotations from the optimized query to get all variable values
        # The advanced analyzer has added subquery annotations for all non-primary facts

        for condition in conditions:
            fact_storage_model = type(condition)._django_model

            # Skip the primary fact (already processed)
            if isinstance(primary_instance, fact_storage_model):
                continue

            # For other facts, use the annotation added by _add_result_annotations
            if isinstance(condition.object, Var):
                var_name = condition.object.name
                if var_name not in result:
                    # Look for the annotation with this fact's data
                    annotation_name = f'{fact_storage_model._meta.model_name}_object_id'
                    if hasattr(primary_instance, annotation_name):
                        annotated_value = getattr(primary_instance, annotation_name)
                        if annotated_value is not None:
                            result[var_name] = annotated_value

        # Check if we found all expected variables
        expected_vars = set()
        for condition in conditions:
            if isinstance(condition.subject, Var):
                expected_vars.add(condition.subject.name)
            if isinstance(condition.object, Var):
                expected_vars.add(condition.object.name)

        if set(result.keys()) == expected_vars:
            yield result


def _execute_simple_orm_optimization(conditions: list[Fact]) -> Iterator[dict[str, Any]]:
    """Execute simple ORM optimization for basic patterns only."""

    # This handles only the simplest cases - single fact patterns with basic constraints
    if len(conditions) != 1:
        raise NotImplementedError("Only single-fact patterns supported")

    condition = conditions[0]
    fact_class = type(condition)
    django_model = fact_class._django_model

    # Convert the fact to a Django query
    query_params, q_objects = _fact_to_django_query(condition)

    # Build and execute the query
    queryset = django_model.objects.filter(**query_params)
    for q_obj in q_objects:
        queryset = queryset.filter(q_obj)

    # Convert results back to django-datalog format (PKs)
    for instance in queryset.values('subject', 'object'):
        result = {}
        if isinstance(condition.subject, Var):
            result[condition.subject.name] = instance['subject']
        if isinstance(condition.object, Var):
            result[condition.object.name] = instance['object']
        yield result












def _map_variable_to_field(var_name: str) -> str:
    """Map variable names to Django model field names.

    This is a dynamic mapping that uses the variable name directly.
    No hardcoded mappings - let Django ORM handle field resolution.
    """
    return var_name


def _is_simple_cross_variable_constraint(q_obj) -> bool:
    """Check if this is a simple cross-variable constraint like Q(company=Var('company'))."""
    if not hasattr(q_obj, 'children') or len(q_obj.children) != 1:
        return False

    child = q_obj.children[0]
    if not isinstance(child, tuple) or len(child) != 2:
        return False

    field_name, value = child
    return isinstance(value, Var)


def _extract_simple_cross_variable_constraint(q_obj) -> tuple[str, str]:
    """Extract field name and variable name from simple cross-variable constraint."""
    child = q_obj.children[0]
    field_name, value = child
    return field_name, value.name


def _unify_bindings(existing: dict, new: dict) -> dict[str, Any] | None:
    """Try to unify two sets of variable bindings."""
    result = existing.copy()
    for var, value in new.items():
        if var in result:
            if result[var] != value:
                return None  # Conflict
        else:
            result[var] = value
    return result


def _hydrate_results(pk_results: list[dict], fact_patterns: list[Fact]) -> Iterator[dict[str, Any]]:
    """Hydrate PK results to full model instances."""
    if not pk_results:
        return

    # Collect all PKs that need hydration by variable name and model type
    var_to_model_type = {}
    pks_to_hydrate = {}

    # First pass: discover what models each variable represents. Only positions
    # typed as a Django model hydrate; value positions (a rank, a string) stay
    # as their raw value.
    for fact_pattern in fact_patterns:
        for field_name in type(fact_pattern)._positions:
            field_val = getattr(fact_pattern, field_name)
            if isinstance(field_val, Var):
                var_name = field_val.name
                # Extract model type from fact pattern using the helper function
                model_type = _extract_model_type_from_annotation(
                    fact_pattern.__dataclass_fields__[field_name].type
                )
                if model_type and var_name not in var_to_model_type:
                    var_to_model_type[var_name] = model_type
                    pks_to_hydrate[var_name] = set()

    # Second pass: collect all PKs for each variable
    for result in pk_results:
        for var_name, pk in result.items():
            if var_name in pks_to_hydrate:
                pks_to_hydrate[var_name].add(pk)

    # Batch load models by type
    model_cache = {}
    for var_name, model_type in var_to_model_type.items():
        if var_name in pks_to_hydrate:
            pk_list = list(pks_to_hydrate[var_name])
            models = model_type.objects.in_bulk(pk_list)
            model_cache[var_name] = models

    # Hydrate results
    for result in pk_results:
        hydrated_result = {}
        for var_name, pk in result.items():
            if var_name in model_cache and pk in model_cache[var_name]:
                hydrated_result[var_name] = model_cache[var_name][pk]
            else:
                hydrated_result[var_name] = pk  # Keep as PK if can't hydrate
        yield hydrated_result
