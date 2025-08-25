"""
Tests for adaptive query planning with timing feedback in django-datalog.
"""

from django.db.models import Q
from django.test import TestCase

from django_datalog.models import (
    Var,
    get_optimizer_timing_stats,
    query,
    reset_optimizer_cache,
    store_facts,
)
# QueryPlanner was removed in optimizer simplification - these tests are no longer applicable

from .models import Company, Department, Employee, MemberOf, Person, WorksFor


# NOTE: These tests are disabled because QueryPlanner was removed in optimizer simplification
# The advanced query analyzer now handles all optimization through AST-based analysis

# class TestAdaptiveQueryPlanning(TestCase):
#     """Test that the query planner learns from execution times."""
# 
#     def setUp(self):
        """Set up test data."""
        reset_optimizer_cache()

        # Create test data with different characteristics for timing tests
        self.active_company = Company.objects.create(name="ActiveCorp", is_active=True)
        self.inactive_company = Company.objects.create(name="InactiveCorp", is_active=False)

        self.eng_dept = Department.objects.create(name="Engineering", company=self.active_company)
        self.sales_dept = Department.objects.create(name="Sales", company=self.active_company)

        # Create many employees to make timing differences more measurable
        for i in range(20):
            person = Person.objects.create(name=f"Person{i}", age=25 + i)

            # Most employees in engineering (less selective)
            dept = self.eng_dept if i < 15 else self.sales_dept
            company = self.active_company if i < 18 else self.inactive_company

            emp = Employee.objects.create(
                person=person,
                company=company,
                department=dept,
                is_manager=(i == 0),  # Only one manager (very selective)
                salary=50000 + i * 1000,
            )

            store_facts(
                WorksFor(subject=emp, object=company),
                MemberOf(subject=emp, object=dept),
            )

    def test_timing_feedback_affects_planning(self):
        """Test that recorded timing affects future query planning."""
        planner = QueryPlanner()

        # Create two patterns - one that should be slower, one faster
        slow_pattern = WorksFor(Var("emp"), Var("company"))  # No constraints, should be slow
        fast_pattern = WorksFor(
            Var("emp", where=Q(is_manager=True)), Var("company")
        )  # Very selective

        # Record artificial timing data to simulate slow vs fast patterns
        planner.record_execution_timing(slow_pattern, 0.1)  # 100ms - slow
        planner.record_execution_timing(slow_pattern, 0.12)
        planner.record_execution_timing(slow_pattern, 0.11)

        planner.record_execution_timing(fast_pattern, 0.01)  # 10ms - fast
        planner.record_execution_timing(fast_pattern, 0.012)
        planner.record_execution_timing(fast_pattern, 0.008)

        # Plan execution order - fast pattern should come first
        patterns = [slow_pattern, fast_pattern]
        planned = planner.plan_query_execution(patterns)

        # The fast pattern (with manager constraint) should be planned first
        first_pattern = planned[0]
        self.assertTrue(
            isinstance(first_pattern.subject, Var)
            and first_pattern.subject.where is not None
            and "is_manager" in str(first_pattern.subject.where)
        )

    def test_query_execution_records_timings(self):
        """Test that actual query execution records timing feedback."""
        # Clear any existing timing stats
        reset_optimizer_cache()

        # Execute queries - this should record timing data automatically
        results1 = list(query(WorksFor(Var("emp"), self.active_company)))
        self.assertGreater(len(results1), 0)

        results2 = list(query(WorksFor(Var("emp", where=Q(is_manager=True)), Var("company"))))
        self.assertGreater(len(results2), 0)

        # Check that timing data was recorded
        timing_stats = get_optimizer_timing_stats()
        self.assertGreater(len(timing_stats), 0)

        # Should have stats for WorksFor patterns
        found_works_for = False
        for pattern_key, stats in timing_stats.items():
            if "WorksFor" in pattern_key:
                found_works_for = True
                self.assertGreater(stats["count"], 0)
                self.assertGreater(stats["avg_time"], 0)
                break

        self.assertTrue(found_works_for, "Expected timing stats for WorksFor patterns")

    def test_pattern_differentiation_by_constraints(self):
        """Test that patterns with different constraints are tracked separately."""
        planner = QueryPlanner()

        # Create patterns with different constraints
        unconstrained = WorksFor(Var("emp"), Var("company"))
        manager_constrained = WorksFor(Var("emp", where=Q(is_manager=True)), Var("company"))
        active_company_constrained = WorksFor(Var("emp"), Var("company", where=Q(is_active=True)))

        # Record different timings for each
        planner.record_execution_timing(unconstrained, 0.05)
        planner.record_execution_timing(manager_constrained, 0.01)
        planner.record_execution_timing(active_company_constrained, 0.03)

        # Check that they're tracked separately
        stats = planner.get_timing_stats()

        # Should have different keys for different constraint patterns
        pattern_keys = list(stats.keys())
        self.assertGreater(
            len(pattern_keys), 1, "Different constraint patterns should have separate timing keys"
        )

        # Verify timing differences are preserved
        for key, timing_stats in stats.items():
            if "is_manager" in key:
                self.assertLess(timing_stats["avg_time"], 0.02)  # Manager constraint should be fast
            elif "is_active" in key:
                self.assertGreater(
                    timing_stats["avg_time"], 0.02
                )  # Active company constraint slower
                self.assertLess(timing_stats["avg_time"], 0.04)

    def test_timing_data_updates_estimates(self):
        """Test that timing data affects future selectivity estimates."""
        planner = QueryPlanner()

        pattern = WorksFor(Var("emp", where=Q(is_manager=True)), Var("company"))

        # Record timing data
        planner.record_execution_timing(pattern, 0.05)

        # Get estimation with timing data
        stats = planner._estimate_pattern_selectivity(pattern)
        self.assertGreater(stats.avg_execution_time, 0)

    def test_execution_priority_with_timing_data(self):
        """Test that execution priority calculation includes timing data."""
        planner = QueryPlanner()

        # Create two patterns with same selectivity but different timing
        fast_pattern = WorksFor(Var("emp", where=Q(is_manager=True)), Var("company"))
        slow_pattern = MemberOf(Var("emp", where=Q(is_manager=True)), Var("dept"))

        # Record timing data
        planner.record_execution_timing(fast_pattern, 0.01)  # Fast
        planner.record_execution_timing(slow_pattern, 0.1)  # Slow

        # Get stats and calculate priorities
        fast_stats = planner._estimate_pattern_selectivity(fast_pattern)
        slow_stats = planner._estimate_pattern_selectivity(slow_pattern)

        fast_priority = planner._calculate_execution_priority(fast_stats)
        slow_priority = planner._calculate_execution_priority(slow_stats)

        # Lower priority score means higher priority - fast should have lower score
        self.assertLess(
            fast_priority, slow_priority, "Faster patterns should have higher execution priority"
        )


class TestTimingIntegration(TestCase):
    """Test integration between query execution and timing feedback."""

    def setUp(self):
        """Set up test data."""
        reset_optimizer_cache()

        self.company = Company.objects.create(name="TestCorp", is_active=True)
        self.dept = Department.objects.create(name="Engineering", company=self.company)

        # Create some employees
        for i in range(10):
            person = Person.objects.create(name=f"Person{i}", age=25 + i)
            emp = Employee.objects.create(
                person=person,
                company=self.company,
                department=self.dept,
                is_manager=(i == 0),
                salary=50000 + i * 1000,
            )
            store_facts(
                WorksFor(subject=emp, object=self.company),
                MemberOf(subject=emp, object=self.dept),
            )

    def test_multiple_query_executions_improve_planning(self):
        """Test that multiple query executions improve future planning."""
        # Execute the same query multiple times to build timing data
        for _ in range(3):
            list(query(WorksFor(Var("emp"), self.company)))
            list(query(WorksFor(Var("emp", where=Q(is_manager=True)), self.company)))

        # Check that timing data accumulated
        timing_stats = get_optimizer_timing_stats()

        found_constrained = False
        found_unconstrained = False

        for pattern_key, stats in timing_stats.items():
            if "WorksFor" in pattern_key:
                if "is_manager" in pattern_key:
                    found_constrained = True
                    self.assertGreaterEqual(stats["count"], 3)
                else:
                    found_unconstrained = True
                    self.assertGreaterEqual(stats["count"], 3)

        self.assertTrue(found_constrained, "Expected timing data for constrained WorksFor")
        self.assertTrue(found_unconstrained, "Expected timing data for unconstrained WorksFor")

    def test_timing_data_persistence_across_queries(self):
        """Test that timing data persists and accumulates across different queries."""
        # Execute different types of queries
        list(query(WorksFor(Var("emp"), Var("company"))))
        list(query(MemberOf(Var("emp"), Var("dept"))))
        list(query(WorksFor(Var("emp", where=Q(salary__gte=55000)), Var("company"))))

        timing_stats = get_optimizer_timing_stats()

        # Should have timing data for multiple pattern types
        pattern_types = set()
        for pattern_key in timing_stats.keys():
            if "WorksFor" in pattern_key:
                pattern_types.add("WorksFor")
            elif "MemberOf" in pattern_key:
                pattern_types.add("MemberOf")

        self.assertGreaterEqual(
            len(pattern_types), 2, "Expected timing data for multiple fact types"
        )
