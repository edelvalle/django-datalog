"""
Query optimization system for django-datalog.

This module implements constraint propagation and selectivity-aware query planning
to dramatically improve query performance by:

1. Propagating constraints across variables with the same name
2. Estimating predicate selectivity using database statistics
3. Ordering query execution by selectivity (most selective first)
4. Leveraging intermediate results to constrain subsequent queries
"""

import time
from collections import defaultdict, deque
from contextlib import contextmanager
from dataclasses import dataclass
from functools import reduce
from statistics import mean
from typing import Any

from django.db.models import Q

from django_datalog.facts import Fact
from django_datalog.variables import Var


@dataclass
class PredicateStats:
    """Statistics about a predicate for query planning."""

    fact_type: type[Fact]
    selectivity: float  # 0.0 to 1.0 (lower = more selective)
    has_constraints: bool  # Does this pattern have WHERE clauses?
    constraint_variables: set[str]  # Which variables are constrained
    avg_execution_time: float = 0.0  # Average execution time for this pattern


@dataclass
class VariableConstraintInfo:
    """Information about constraints on a variable."""

    name: str
    constraints: list[Q]
    merged_constraint: Q | None = None


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

        print(">>", fact_patterns)
        for fact_pattern in fact_patterns:
            # Extract variables from subject and object
            print(">>>", fact_pattern)
            variables = self._extract_variables(fact_pattern)
            for var in variables:
                if var.where is not None:
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


class QueryPlanner:
    """
    Memory-safe intelligent query planner that learns from execution times to optimize performance.

    The planner works by:
    1. Analyzing each fact pattern to estimate selectivity (how many results it will return)
    2. Recording actual execution times for each pattern type
    3. Combining selectivity and timing data to calculate execution priority
    4. Reordering patterns to execute most selective and fastest patterns first
    5. Learning from each execution to improve future planning decisions

    Memory optimizations:
    - execution_times uses bounded deques (max 100 entries per pattern)
    - selectivity_cache uses LRU eviction (max 500 entries)
    - Automatic cleanup prevents unbounded memory growth
    """

    def __init__(self, max_timing_samples: int = 100, max_cache_size: int = 500):
        self.selectivity_cache = {}  # LRU cache for selectivity estimates
        self.cache_access_order = deque()  # Track access order for LRU eviction
        self.variable_solutions = {}  # Track known variable solutions for optimization
        # Bounded timing history
        self.execution_times = defaultdict(lambda: deque(maxlen=max_timing_samples))
        self.max_cache_size = max_cache_size

    def plan_query_execution(self, fact_patterns: list[Fact]) -> list[Fact]:
        """
        Plan optimal execution order for fact patterns based on selectivity and historical timing.

        This is the main planning method that determines which patterns should execute first.
        It combines constraint analysis with historical execution times to optimize performance.

        Args:
            fact_patterns: List of fact patterns to execute (e.g., [WorksFor(...), MemberOf(...)])

        Returns:
            Reordered list optimized for performance (most selective/fastest patterns first)

        Example:
            Input:  [WorksFor(unconstrained), WorksFor(manager_constraint)]
            Output: [WorksFor(manager_constraint), WorksFor(unconstrained)]
            # Manager constraint executes first because it's more selective
        """
        # Step 1: Analyze each pattern to create statistics (selectivity + timing data)
        pattern_stats = []
        for i, pattern in enumerate(fact_patterns):
            stats = self._estimate_pattern_selectivity(pattern)
            pattern_stats.append((stats, i, pattern))

        # Step 2: Sort by execution priority (lower score = higher priority = executes first)
        # This combines selectivity estimates with historical timing data
        pattern_stats.sort(key=lambda x: self._calculate_execution_priority(x[0]))

        # Step 3: Return reordered patterns (most selective and fastest patterns first)
        return [pattern for stats, i, pattern in pattern_stats]

    def _estimate_pattern_selectivity(self, pattern: Fact) -> PredicateStats:
        """
        Analyze a fact pattern to estimate its selectivity and retrieve timing data.

        Selectivity = how many results this pattern will return:
        - 0.0 = very selective
        - 1.0 = full scan
        This combines constraint analysis with historical execution times.

        Args:
            pattern: Fact pattern like WorksFor(Var("emp", where=Q(is_manager=True)),
                     Var("company"))

        Returns:
            PredicateStats with selectivity, constraints info, and average execution time

        Examples:
            WorksFor(unconstrained) → selectivity=1.0, avg_time=0.005s
            WorksFor(manager constraint) → selectivity=0.1, avg_time=0.001s
        """
        fact_type = type(pattern)
        cache_key = str(pattern)

        # Check cache first to avoid recalculating same patterns
        if cache_key in self.selectivity_cache:
            # Update LRU access order
            self._update_cache_access(cache_key)
            return self.selectivity_cache[cache_key]

        # Step 1: Analyze constraints to determine base selectivity
        constraint_variables = set()
        has_constraints = False
        selectivity = 1.0  # Default: no constraints = low selectivity (full scan)

        variables = self._extract_variables(pattern)
        for var in variables:
            if var.where is not None:  # This variable has a WHERE clause constraint
                has_constraints = True
                constraint_variables.add(var.name)

        # Step 2: Calculate selectivity based on constraint presence
        if has_constraints:
            # More constraints = more selective (fewer results)
            # Example: 1 constraint = 0.1, 2 constraints = 0.01, etc.
            num_constraints = len(constraint_variables)
            # Rough heuristic: each constraint is 10x more selective
            selectivity = 0.1**num_constraints
        else:
            selectivity = 1.0  # No constraints = full table scan

        # Step 3: Include historical execution time data from previous runs
        pattern_key = self._pattern_to_key(pattern)  # Convert to tracking key
        times = self.execution_times[pattern_key]  # Get historical times for this pattern
        avg_time = mean(times) if times else 0.0  # Calculate average or default to 0

        # Step 4: Create statistics object combining all information
        stats = PredicateStats(
            fact_type=fact_type,
            selectivity=selectivity,
            has_constraints=has_constraints,
            constraint_variables=constraint_variables,
            avg_execution_time=avg_time,
        )

        # Step 5: Cache the result for future use with LRU eviction
        self._add_to_cache(cache_key, stats)
        return stats

    def _calculate_execution_priority(self, stats: PredicateStats) -> float:
        """
        Calculate execution priority score combining selectivity and timing data.

        Lower score = higher priority = executes first
        This is the core algorithm that decides execution order.

        The calculation combines:
        1. Base selectivity (fewer results = better)
        2. Constraint bonuses (constrained queries are usually faster)
        3. Historical timing data (patterns that were slow get penalized)
        4. Variable solution sizes (if known from previous executions)

        Args:
            stats: PredicateStats containing selectivity and timing information

        Returns:
            Priority score (float). Lower values mean higher execution priority.

        Examples:
            Unconstrained pattern: selectivity=1.0 → priority=1.0 (low priority, executes last)
            Manager constraint: selectivity=0.1, fast=0.001s → priority=0.05
            (high priority, executes first)
        """
        # Start with base selectivity (lower = more selective = better)
        base_score = stats.selectivity

        # Apply priority boosts for better patterns:

        # Boost 1: Constrained patterns get 50% priority boost
        if stats.has_constraints:
            base_score *= 0.5  # Cut score in half = higher priority

        # Boost 2: Very selective patterns get 90% priority boost
        if stats.selectivity < 0.1:
            base_score *= 0.1  # Cut score by 90% = much higher priority

        # Boost 3: Consider known variable solution sizes (advanced optimization)
        for var_name in stats.constraint_variables:
            if var_name in self.variable_solutions:
                solution_count = len(self.variable_solutions[var_name])
                # Fewer solutions = higher priority (less work to do)
                base_score *= solution_count / 1000.0

        # Penalty: Factor in actual execution time - penalize historically slow patterns
        if stats.avg_execution_time > 0:
            # Convert timing to penalty factor (slow queries get lower priority)
            time_penalty = min(stats.avg_execution_time / 0.1, 2.0)  # Cap penalty at 2x
            base_score *= 1.0 + time_penalty  # Increase score = lower priority

        return base_score

    def record_execution_timing(self, pattern: Fact, execution_time: float):
        """
        Record actual execution time for a fact pattern - this is the learning mechanism!

        This is called automatically after each query execution via the timing context manager.
        The recorded timing data feeds back into future query planning decisions.

        Args:
            pattern: The fact pattern that was executed (e.g., WorksFor(Var("emp"), Var("company")))
            execution_time: Time in seconds that the pattern took to execute (e.g., 0.005)

        The learning process:
        1. Convert pattern to tracking key (e.g., "WorksFor" or
           "WorksFor(subject:Q(is_manager=True))")
        2. Store execution time in historical data
        3. Invalidate cache so future estimates use the new timing data
        4. Next query planning will factor in this timing information
        """
        # Step 1: Convert pattern to unique tracking key
        pattern_key = self._pattern_to_key(pattern)

        # Step 2: Store the execution time for this pattern type (bounded deque auto-evicts old entries)  # noqa: E501
        self.execution_times[pattern_key].append(execution_time)

        # Step 3: Invalidate relevant cache entries so they get recalculated with new timing data
        # This ensures that future selectivity estimates include the new timing information
        cache_keys_to_clear = [k for k in self.selectivity_cache.keys() if pattern_key in k]
        for key in cache_keys_to_clear:
            self._remove_from_cache(key)

    def _pattern_to_key(self, pattern: Fact) -> str:
        """
        Convert a fact pattern to a unique string key for tracking timing data.

        Different constraint patterns need separate tracking because they have different
        performance characteristics. This key generation ensures we track them separately.

        Args:
            pattern: Fact pattern to convert to key

        Returns:
            Unique string key for this pattern type

        Examples:
            WorksFor(Var("emp"), Var("company")) → "WorksFor"
            WorksFor(Var("emp", Q(is_manager=True)), Var("company")) →
            "WorksFor(subject:Q(is_manager=True))"
            WorksFor(Var("emp"), Var("company", Q(is_active=True))) →
            "WorksFor(object:Q(is_active=True))"
        """
        # Start with fact type name (e.g., "WorksFor", "MemberOf")
        fact_type_name = type(pattern).__name__

        # Add constraint information to differentiate patterns with different WHERE clauses
        constraints = []
        if isinstance(pattern.subject, Var) and pattern.subject.where:
            constraints.append(f"subject:{str(pattern.subject.where)}")
        if isinstance(pattern.object, Var) and pattern.object.where:
            constraints.append(f"object:{str(pattern.object.where)}")

        # Create final key: either just fact name or fact name with constraints
        if constraints:
            return f"{fact_type_name}({','.join(constraints)})"
        else:
            return fact_type_name

    def get_timing_stats(self) -> dict[str, dict[str, float]]:
        """Get timing statistics for all tracked patterns."""
        stats = {}
        for pattern_key, times in self.execution_times.items():
            if times:
                stats[pattern_key] = {
                    "count": len(times),
                    "avg_time": mean(times),
                    "min_time": min(times),
                    "max_time": max(times),
                    "total_time": sum(times),
                    "max_samples": times.maxlen,  # Show the bounded size
                }
        return stats

    def _add_to_cache(self, key: str, value: PredicateStats):
        """Add entry to LRU cache with automatic eviction if needed."""
        # Remove if already exists (to update position)
        if key in self.selectivity_cache:
            self._remove_from_cache(key)

        # Evict least recently used if at capacity
        while len(self.selectivity_cache) >= self.max_cache_size:
            if self.cache_access_order:
                lru_key = self.cache_access_order.popleft()
                if lru_key in self.selectivity_cache:
                    del self.selectivity_cache[lru_key]

        # Add new entry
        self.selectivity_cache[key] = value
        self.cache_access_order.append(key)

    def _update_cache_access(self, key: str):
        """Update access order for LRU tracking."""
        # Remove from current position and add to end
        try:
            self.cache_access_order.remove(key)
        except ValueError:
            pass  # Key not in order queue, will be added below
        self.cache_access_order.append(key)

    def _remove_from_cache(self, key: str):
        """Remove entry from LRU cache."""
        if key in self.selectivity_cache:
            del self.selectivity_cache[key]
            try:
                self.cache_access_order.remove(key)
            except ValueError:
                pass  # Key not in order queue

    def get_cache_info(self) -> dict[str, int | float]:
        """Get cache statistics for monitoring."""
        return {
            "cache_size": len(self.selectivity_cache),
            "max_cache_size": self.max_cache_size,
            "cache_utilization": len(self.selectivity_cache) / self.max_cache_size,
        }

    def _extract_variables(self, fact_pattern: Fact) -> list[Var]:
        """Extract all Var instances from a fact pattern."""
        variables = []

        if isinstance(fact_pattern.subject, Var):
            variables.append(fact_pattern.subject)
        if isinstance(fact_pattern.object, Var):
            variables.append(fact_pattern.object)

        return variables


class QueryOptimizer:
    """Main query optimizer that combines constraint propagation and query planning."""

    def __init__(self):
        self.constraint_propagator = ConstraintPropagator()
        self.query_planner = QueryPlanner()

    def optimize_query(self, fact_patterns: list[Fact]) -> list[Fact]:
        """
        Optimize a query by propagating constraints and planning execution order.

        Args:
            fact_patterns: Original fact patterns from user query

        Returns:
            Optimized fact patterns with constraints propagated and ordered by selectivity
        """
        # Step 1: Propagate constraints across variables with same names
        patterns_with_propagated_constraints = self.constraint_propagator.propagate_constraints(
            fact_patterns
        )

        # Step 2: Plan optimal execution order based on selectivity
        optimized_patterns = self.query_planner.plan_query_execution(
            patterns_with_propagated_constraints
        )

        return optimized_patterns

    def record_pattern_timing(self, pattern: Fact, execution_time: float):
        """Record execution timing for a fact pattern to improve future planning."""
        self.query_planner.record_execution_timing(pattern, execution_time)

    def get_planner_stats(self) -> dict[str, dict[str, float]]:
        """Get timing statistics from the query planner."""
        return self.query_planner.get_timing_stats()

    def reset_cache(self):
        """Reset optimizer caches (useful for testing)."""
        self.query_planner.selectivity_cache.clear()
        self.query_planner.cache_access_order.clear()
        self.query_planner.variable_solutions.clear()
        self.query_planner.execution_times.clear()


# Global optimizer instance
_query_optimizer = QueryOptimizer()


def optimize_query(fact_patterns: list[Fact]) -> list[Fact]:
    """
    Public API for query optimization.

    Args:
        fact_patterns: List of fact patterns to optimize

    Returns:
        Optimized fact patterns
    """
    return _query_optimizer.optimize_query(fact_patterns)


def reset_optimizer_cache():
    """Reset query optimizer cache (useful for testing)."""
    _query_optimizer.reset_cache()


def record_fact_timing(pattern: Fact, execution_time: float):
    """Record execution timing for a fact pattern to improve future query planning."""
    _query_optimizer.record_pattern_timing(pattern, execution_time)


@contextmanager
def time_fact_execution(pattern: Fact):
    """
    Context manager to time execution of a fact pattern.

    Usage:
        with time_fact_execution(pattern):
            # execute query for pattern
            results = do_query()
    """
    start_time = time.time()
    try:
        yield
    finally:
        execution_time = time.time() - start_time
        _query_optimizer.record_pattern_timing(pattern, execution_time)


def get_optimizer_timing_stats() -> dict[str, dict[str, float]]:
    """Get timing statistics from the global optimizer."""
    return _query_optimizer.get_planner_stats()
