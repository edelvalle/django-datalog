"""
Rule system for djdatalog - handles inference rules and rule evaluation.
"""

from dataclasses import dataclass
from typing import Any

from djdatalog.facts import Fact


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


def clear_rules() -> None:
    """Clear all registered rules (useful for testing)."""
    global _rules
    _rules = []


def apply_rules(base_facts: set[Fact]) -> set[Fact]:
    """
    Apply inference rules to derive new facts from base facts.
    
    Args:
        base_facts: Set of known facts
        
    Returns:
        Set of all facts (base + inferred)
    """
    all_facts = base_facts.copy()
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
                    all_facts.add(new_fact)
                    changed = True
    
    return all_facts


def _apply_single_rule(rule_obj: Rule, known_facts: set[Fact]) -> set[Fact]:
    """Apply a single rule to known facts to derive new facts."""
    # This is a simplified implementation
    # A full implementation would need proper unification and backtracking
    return set()  # For now, return empty set