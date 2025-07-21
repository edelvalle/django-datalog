"""
Rule system for djdatalog - handles inference rules and rule evaluation.
"""

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from django_datalog.facts import Fact


@dataclass
class Rule:
    """Represents a datalog inference rule."""

    head: Fact
    body: list[Any]  # List of facts or nested lists (for OR conditions)

    def __repr__(self):
        return f"Rule({self.head} :- {self.body})"


# Global rule registry
_rules: list[Rule] = []


def rule(head: Fact, *body) -> None:
    """
    Define an inference rule.

    Args:
        head: The fact that can be inferred
        *body: Conditions that must be true (supports nested lists for OR conditions)

    Example:
        rule(
            GrandparentOf(Var("grandparent"), Var("grandchild")),
            ParentOf(Var("grandparent"), Var("parent")),
            ParentOf(Var("parent"), Var("grandchild"))
        )
    """
    new_rule = Rule(head=head, body=list(body))
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
    from django_datalog.query import Var

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
    from django_datalog.query import Var

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


@contextmanager
def rule_context(*rule_definitions):
    """
    Context manager for temporary rules that are only active within the context.

    Args:
        *rule_definitions: Optional rule definitions as tuples of (head, *body)

    Usage:
        # Context manager with rules defined inside
        with rule_context():
            rule(TeamMates(Var("emp1"), Var("emp2")),
                 MemberOf(Var("emp1"), Var("dept")),
                 MemberOf(Var("emp2"), Var("dept")))

            # Rules are active here
            teammates = query(TeamMates(Var("emp1"), Var("emp2")))

        # Rules are no longer active here

        # Context manager with rules passed as arguments
        with rule_context(
            (TeamMates(Var("emp1"), Var("emp2")),
             MemberOf(Var("emp1"), Var("dept")),
             MemberOf(Var("emp2"), Var("dept")))
        ):
            # Rules are active here
            teammates = query(TeamMates(Var("emp1"), Var("emp2")))
    """
    # Save the current global rules
    original_rules = _rules.copy()

    # Add any rules passed as arguments
    for rule_def in rule_definitions:
        if isinstance(rule_def, tuple | list) and len(rule_def) >= 2:
            head = rule_def[0]
            body = rule_def[1:]
            rule(head, *body)

    try:
        yield
    finally:
        # Restore the original global rules
        _rules.clear()
        _rules.extend(original_rules)
