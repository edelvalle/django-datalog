"""
Rule system for djdatalog - handles inference rules and rule evaluation.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from django_datalog.facts import Fact, FactConjunction
from django_datalog.optimizer import ConstraintPropagator
from django_datalog.variables import Var


@dataclass
class Rule:
    """Represents a datalog inference rule."""

    head: Fact
    body: list[Any]  # List of facts or nested lists (for OR conditions)

    def __repr__(self):
        return f"Rule({self.head} :- {self.body})"


# Global rule registry
_rules: list[Rule] = []


def rule(head: Fact, body: Fact | list[Fact | FactConjunction] | FactConjunction) -> None:
    """
    Define inference rules with automatic constraint propagation and support for | and & operators.

    Args:
        head: The fact that can be inferred (must be marked with inferred=True)
        body: The rule body. Can be:
              - A single Fact (one condition)
              - A tuple[Fact, ...] (conjunctive conditions - AND)
              - A list[Fact | tuple[Fact, ...]] (disjunctive alternatives - OR)

    Raises:
        TypeError: If the head fact is not marked with inferred=True

    Examples:
        # Single fact condition
        rule(HasAccess(Var("user"), Var("resource")), IsOwner(Var("user"), Var("resource")))

        # Conjunctive conditions (AND) using tuple
        rule(
            HasAccess(Var("user"), Var("resource")),
            (MemberOf(Var("user"), Var("company")), Owns(Var("company"), Var("resource")))
        )

        # Disjunctive alternatives (OR) using list
        rule(
            HasAccess(Var("user"), Var("resource")),
            [
                IsOwner(Var("user"), Var("resource")),                    # Alternative 1
                IsAdmin(Var("user"), Var("resource")),                    # Alternative 2
                (  # Alternative 3 (conjunction)
                    MemberOf(Var("user"), Var("team")),
                    TeamOwns(Var("team"), Var("resource"))
                )
            ]
        )

        # Using operators (generates the same structures as above):
        rule(
            HasAccess(Var("user"), Var("resource")),
            IsOwner(Var("user"), Var("resource")) | IsAdmin(Var("user"), Var("resource"))
        )

        rule(
            HasAccess(Var("user"), Var("resource")),
            MemberOf(Var("user"), Var("company")) & Owns(Var("company"), Var("resource"))
        )
    """
    # Verify that the head fact is marked as inferred=True
    if not getattr(type(head), "_is_inferred", False):
        raise TypeError(
            f"Rule head fact {type(head).__name__} must be marked with inferred=True. "
            f"Only inferred facts can be the head of inference rules."
        )
    match body:
        case Fact():
            # Single fact - create one rule with one condition
            _create_single_rule(head, [body])

        case FactConjunction() | tuple():
            # FactConjunction or tuple represents conjunction (AND)
            # - create one rule with multiple conditions
            _create_single_rule(head, list(body))

        case list():
            # List represents disjunction (OR) - create separate rules for each alternative
            for alternative in body:
                match alternative:
                    case Fact():
                        # Single fact alternative
                        _create_single_rule(head, [alternative])
                    case FactConjunction() | tuple():
                        # FactConjunction or tuple alternative (conjunction within disjunction)
                        _create_single_rule(head, list(alternative))
                    case _:
                        # Handle other types gracefully - treat as single fact
                        _create_single_rule(head, [alternative])
        case _:
            # Handle other types gracefully - treat as single fact
            _create_single_rule(head, [body])


def _create_single_rule(head: Fact, body: list[Fact]) -> None:
    """Create a single Rule object with constraint propagation."""
    # Apply constraint propagation for this specific rule
    propagator = ConstraintPropagator()

    # Combine head and body for constraint analysis
    all_patterns = [head] + body

    # Propagate constraints across variables with the same name
    optimized_patterns = propagator.propagate_constraints(all_patterns)

    # Split back into head and body
    optimized_head = optimized_patterns[0]
    optimized_body = optimized_patterns[1:]

    # Create and register the rule
    new_rule = Rule(head=optimized_head, body=optimized_body)
    _rules.append(new_rule)


def get_rules() -> list[Rule]:
    """Get all registered rules."""
    return _rules.copy()


def apply_rules(base_facts: list[Fact]) -> list[Fact]:
    """Apply all registered inference rules to derive new facts (base + inferred)."""
    return _seminaive_fixpoint(_rules, base_facts)


def apply_targeted_rules(target_rules: list, base_facts: list[Fact]) -> list[Fact]:
    """Apply only the given rules to derive new facts (base + inferred)."""
    return _seminaive_fixpoint(target_rules, base_facts)


def _seminaive_fixpoint(rule_list: list, base_facts: list[Fact]) -> list[Fact]:
    """Semi-naïve fixpoint evaluation.

    Each round joins only against the facts derived in the previous round (the
    "delta"), so a rule fires on genuinely new information rather than
    re-deriving the whole extension every iteration. The loop ends when a round
    produces nothing new; there is no iteration cap, so transitive closures of
    any depth are computed to completion (the domain is finite, so it always
    terminates).
    """
    all_facts = list(base_facts)
    seen = set(all_facts)  # O(1) membership; facts are hashable by type + pks
    delta = list(base_facts)  # round 0: every base fact is "new"

    while delta:
        round_new: list[Fact] = []
        round_seen: set = set()
        for rule_obj in rule_list:
            for fact in _apply_rule_delta(rule_obj, all_facts, delta):
                if fact not in seen and fact not in round_seen:
                    round_seen.add(fact)
                    round_new.append(fact)
        all_facts.extend(round_new)
        seen.update(round_new)
        delta = round_new

    return all_facts


def _apply_rule_delta(rule_obj: Rule, all_facts: list[Fact], delta: list[Fact]) -> list[Fact]:
    """Derive facts from a rule where at least one body condition matches the delta.

    For each body position i, the join uses `delta` for condition i and
    `all_facts` for the rest; the union over all i is exactly the derivations
    that consume at least one newly-derived fact. Duplicates within this call
    are removed; membership against previously-known facts is the caller's job.
    """
    body = rule_obj.body
    new_facts = []
    local_seen: set = set()

    for i in range(len(body)):
        sources = [all_facts] * len(body)
        sources[i] = delta
        for bindings in _find_all_bindings_multi(body, sources):
            try:
                new_fact = _instantiate_fact(rule_obj.head, bindings)
            except Exception:
                continue
            if new_fact is not None and new_fact not in local_seen:
                local_seen.add(new_fact)
                new_facts.append(new_fact)

    return new_facts


def _find_all_bindings(conditions: list[Any], known_facts: list[Fact]) -> list[dict[str, Any]]:
    """Find all variable bindings satisfying all conditions against one fact set."""
    return _find_all_bindings_multi(conditions, [known_facts] * len(conditions))


def _find_all_bindings_multi(
    conditions: list[Any], sources: list[list[Fact]]
) -> list[dict[str, Any]]:
    """Find all bindings satisfying the conditions, condition i drawn from sources[i].

    Conditions are joined left-to-right with a hash join on the variables they
    share, so an N-condition body over M facts costs O(M + matches) per join
    instead of the O(M^N) nested-loop product.
    """
    if not conditions:
        return [{}]  # Empty binding for empty conditions

    result = _find_bindings_for_condition(conditions[0], sources[0])
    for i in range(1, len(conditions)):
        if not result:
            break  # nothing left to extend
        result = _join_bindings(result, _find_bindings_for_condition(conditions[i], sources[i]))
    return result


def _binding_key(value: Any) -> Any:
    """Hashable, equality-consistent key for a bound value (pk for models)."""
    return getattr(value, "pk", value)


def _join_bindings(
    left: list[dict[str, Any]], right: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Relational join of two binding lists on the variables they share."""
    if not left or not right:
        return []

    shared = [k for k in left[0] if k in right[0]]
    if not shared:
        # Disjoint variables: cartesian product (no conflicts possible).
        return [{**lb, **rb} for lb in left for rb in right]

    # Hash join: index the right side by its shared-variable values.
    index: dict[tuple, list[dict[str, Any]]] = {}
    for rb in right:
        index.setdefault(tuple(_binding_key(rb[k]) for k in shared), []).append(rb)

    joined = []
    for lb in left:
        for rb in index.get(tuple(_binding_key(lb[k]) for k in shared), ()):
            joined.append({**lb, **rb})
    return joined


def _find_bindings_for_condition(condition: Any, known_facts: list[Fact]) -> list[dict[str, Any]]:
    """Find all variable bindings that match a single condition against known facts."""
    bindings_list = []

    # Check each known fact to see if it matches the condition
    for fact in known_facts:
        if type(fact) is type(condition):  # Same fact type
            binding = _unify_facts(condition, fact)
            if binding is not None:
                bindings_list.append(binding)

    return bindings_list


def _unify_facts(pattern_fact: Fact, concrete_fact: Fact) -> dict[str, Any] | None:
    """Unify a pattern fact (with variables) against a concrete fact."""
    bindings = {}

    # Check subject
    if isinstance(pattern_fact.subject, Var):
        bindings[pattern_fact.subject.name] = concrete_fact.subject
    elif pattern_fact.subject != concrete_fact.subject:
        return None  # Subjects don't match

    # Check object
    if isinstance(pattern_fact.object, Var):
        var_name = pattern_fact.object.name
        # Check for conflicting bindings
        if var_name in bindings and bindings[var_name] != concrete_fact.object:
            return None
        bindings[var_name] = concrete_fact.object
    elif pattern_fact.object != concrete_fact.object:
        return None  # Objects don't match

    return bindings


def _instantiate_fact(pattern_fact: Fact, bindings: dict[str, Any]) -> Fact | None:
    """Create a concrete fact by substituting variables with their bindings."""
    # Substitute subject
    if isinstance(pattern_fact.subject, Var):
        if pattern_fact.subject.name not in bindings:
            return None  # Unbound variable
        subject = bindings[pattern_fact.subject.name]
    else:
        subject = pattern_fact.subject

    # Substitute object
    if isinstance(pattern_fact.object, Var):
        if pattern_fact.object.name not in bindings:
            return None  # Unbound variable
        obj = bindings[pattern_fact.object.name]
    else:
        obj = pattern_fact.object

    # Create new fact instance of the same type
    fact_class = type(pattern_fact)
    return fact_class(subject=subject, object=obj)


def rule_context(func=None):
    """
    Context manager/decorator for temporary rules that are only active within the context.

    Usage as context manager:
        with rule_context():
            rule(TeamMates(Var("emp1"), Var("emp2")),
                 (MemberOf(Var("emp1"), Var("dept")),
                  MemberOf(Var("emp2"), Var("dept"))))

            # Rules are active here
            teammates = query(TeamMates(Var("emp1"), Var("emp2")))

        # Rules are no longer active here

    Usage as decorator:
        @rule_context
        def test_some_rule(self):
            rule(TeamMates(Var("emp1"), Var("emp2")),
                 (MemberOf(Var("emp1"), Var("dept")),
                  MemberOf(Var("emp2"), Var("dept"))))

            # Test logic here...
    """
    from functools import wraps

    @contextmanager
    def _context():
        # Save the current global rules
        original_rules = _rules.copy()
        try:
            yield
        finally:
            # Restore the original global rules
            _rules.clear()
            _rules.extend(original_rules)

    if func is None:
        # Called as context manager: rule_context()
        return _context()
    else:
        # Called as decorator: @rule_context
        @wraps(func)
        def wrapper(*args, **kwargs):
            with _context():
                return func(*args, **kwargs)

        return wrapper
