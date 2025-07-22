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
    """
    Apply inference rules to derive new facts from base facts.

    Args:
        base_facts: Set of known facts

    Returns:
        Set of all facts (base + inferred)
    """
    all_facts = base_facts[:]
    changed = True
    max_iterations = 100  # Prevent infinite loops
    iterations = 0

    while changed and iterations < max_iterations:
        changed = False
        iterations += 1

        for rule_obj in _rules:
            # Try to apply this rule
            new_facts = _apply_single_rule(rule_obj, all_facts)
            for new_fact in new_facts:
                if new_fact not in all_facts:
                    all_facts.append(new_fact)
                    changed = True

    return all_facts


def apply_targeted_rules(target_rules: list, base_facts: list[Fact]) -> list[Fact]:
    """
    Apply only specific rules to derive new facts from base facts.

    Args:
        target_rules: List of specific rules to apply
        base_facts: Set of known facts

    Returns:
        Set of all facts (base + inferred from target rules only)
    """
    all_facts = base_facts[:]
    changed = True
    max_iterations = 100  # Prevent infinite loops
    iterations = 0

    while changed and iterations < max_iterations:
        changed = False
        iterations += 1

        for rule_obj in target_rules:
            # Try to apply this rule
            new_facts = _apply_single_rule(rule_obj, all_facts)
            for new_fact in new_facts:
                if new_fact not in all_facts:
                    all_facts.append(new_fact)
                    changed = True

    return all_facts


def _apply_single_rule(rule_obj: Rule, known_facts: list[Fact]) -> list[Fact]:
    """Apply a single rule to known facts to derive new facts."""
    new_facts = []

    # known_facts is already a list
    fact_list = known_facts

    # Try to find all possible variable bindings that satisfy the rule body
    bindings_list = _find_all_bindings(rule_obj.body, fact_list)

    # For each valid binding, instantiate the rule head to create a new fact
    for bindings in bindings_list:
        try:
            new_fact = _instantiate_fact(rule_obj.head, bindings)
            if new_fact and new_fact not in known_facts and new_fact not in new_facts:
                new_facts.append(new_fact)
        except Exception:
            # Skip invalid instantiations
            continue

    return new_facts


def _find_all_bindings(conditions: list[Any], known_facts: list[Fact]) -> list[dict[str, Any]]:
    """Find all variable bindings that satisfy all conditions."""
    if not conditions:
        return [{}]  # Empty binding for empty conditions

    all_bindings = []

    # Start with the first condition
    first_condition = conditions[0]
    remaining_conditions = conditions[1:]

    # Find all bindings for the first condition
    first_bindings = _find_bindings_for_condition(first_condition, known_facts)

    # For each binding of the first condition, try to extend it with remaining conditions
    for binding in first_bindings:
        if remaining_conditions:
            # Recursively find bindings for remaining conditions
            extended_bindings = _find_all_bindings(remaining_conditions, known_facts)
            for ext_binding in extended_bindings:
                # Merge bindings, checking for conflicts
                merged = _merge_bindings(binding, ext_binding)
                if merged is not None:
                    all_bindings.append(merged)
        else:
            # No more conditions, this binding is complete
            all_bindings.append(binding)

    return all_bindings


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


def _merge_bindings(binding1: dict[str, Any], binding2: dict[str, Any]) -> dict[str, Any] | None:
    """Merge two variable bindings, checking for conflicts."""
    merged = binding1.copy()

    for var_name, value in binding2.items():
        if var_name in merged:
            if merged[var_name] != value:
                return None  # Conflict - same variable bound to different values
        else:
            merged[var_name] = value

    return merged


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
