"""
Query optimization system for django-datalog.

This module implements constraint propagation across variables with the same name.
Advanced query optimization and execution planning is handled by the query_analyzer module.
"""

from collections import defaultdict
from functools import reduce
from typing import Any

from django.db.models import Q

from django_datalog.facts import Fact
from django_datalog.variables import Var, has_variable_references


class ConstraintPropagator:
    """Handles constraint propagation across variables with the same name."""

    def propagate_constraints(self, fact_patterns: list[Fact]) -> list[Fact]:
        """
        Propagate constraints across variables with the same name in fact patterns.

        Args:
            fact_patterns: List of fact patterns that may contain constrained variables

        Returns:
            List of fact patterns with constraints propagated across same-name variables
        """
        # Step 1: Collect all constraints by variable name
        variable_constraints = self._collect_constraints_by_variable(fact_patterns)

        # Step 2: Merge constraints for each variable (AND them together)
        merged_constraints = self._merge_variable_constraints(variable_constraints)

        # Step 3: Apply merged constraints to all instances of each variable
        return self._apply_merged_constraints(fact_patterns, merged_constraints)

    def _collect_constraints_by_variable(self, fact_patterns: list[Fact]) -> dict[str, list[Q]]:
        """Collect all constraints for each variable name."""
        constraints_by_var = defaultdict(list)

        for fact_pattern in fact_patterns:
            # Extract variables from subject and object
            variables = self._extract_variables(fact_pattern)
            for var in variables:
                if var.where is not None:
                    # Skip constraints that reference other variables - they need special handling
                    if not has_variable_references(var.where):
                        constraints_by_var[var.name].append(var.where)

        return dict(constraints_by_var)

    def _merge_variable_constraints(self, constraints_by_var: dict[str, list[Q]]) -> dict[str, Q]:
        """Merge multiple constraints for the same variable using AND logic."""
        merged_constraints = {}

        for var_name, constraints in constraints_by_var.items():
            if len(constraints) == 1:
                merged_constraints[var_name] = constraints[0]
            elif len(constraints) > 1:
                # AND all constraints together
                merged_constraints[var_name] = reduce(lambda a, b: a & b, constraints)

        return merged_constraints

    def _apply_merged_constraints(
        self, fact_patterns: list[Fact], merged_constraints: dict[str, Q]
    ) -> list[Fact]:
        """Apply merged constraints to all variables with the same name."""
        new_patterns = []

        for pattern in fact_patterns:
            new_pattern = self._update_pattern_constraints(pattern, merged_constraints)
            new_patterns.append(new_pattern)

        return new_patterns

    def _update_pattern_constraints(self, pattern: Fact, merged_constraints: dict[str, Q]) -> Fact:
        """Update a single pattern with merged constraints."""
        # Create a new pattern with updated variables
        updated_subject = self._update_variable_constraint(pattern.subject, merged_constraints)
        updated_object = self._update_variable_constraint(pattern.object, merged_constraints)

        # Create new fact instance with updated variables
        pattern_class = type(pattern)
        return pattern_class(subject=updated_subject, object=updated_object)

    def _update_variable_constraint(self, field: Any, merged_constraints: dict[str, Q]):
        """Update a single field (subject or object) with merged constraints."""
        if isinstance(field, Var) and field.name in merged_constraints:
            # Create new Var with merged constraint
            return Var(field.name, where=merged_constraints[field.name])
        return field

    def _extract_variables(self, fact_pattern: Fact) -> list[Var]:
        """Extract all Var instances from a fact pattern."""
        variables = []

        if isinstance(fact_pattern.subject, Var):
            variables.append(fact_pattern.subject)
        if isinstance(fact_pattern.object, Var):
            variables.append(fact_pattern.object)

        return variables


# Global constraint propagator instance
_constraint_propagator = ConstraintPropagator()


def optimize_query(fact_patterns: list[Fact]) -> list[Fact]:
    """
    Optimize query by propagating constraints across same-named variables.
    
    Args:
        fact_patterns: List of fact patterns to optimize

    Returns:
        Fact patterns with constraints propagated across same-name variables
    """
    return _constraint_propagator.propagate_constraints(fact_patterns)


def reset_optimizer_cache():
    """Reset query optimizer cache (for backwards compatibility)."""
    # No-op since we removed the complex caching system
    pass


# Backwards compatibility - these functions are no longer used but kept for existing code
def record_fact_timing(pattern: Fact, execution_time: float):
    """No-op for backwards compatibility."""
    pass


def get_optimizer_timing_stats() -> dict[str, dict[str, float]]:
    """Return empty stats for backwards compatibility."""
    return {}


def time_fact_execution(pattern: Fact):
    """No-op context manager for backwards compatibility."""
    from contextlib import nullcontext
    return nullcontext()