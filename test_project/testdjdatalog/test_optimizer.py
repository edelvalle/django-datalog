"""
Tests for the simplified django-datalog query optimizer.
Tests constraint propagation functionality.
"""

from django.db.models import Q
from django.test import TestCase

from django_datalog.models import Var, query, store_facts
from django_datalog.optimizer import (
    ConstraintPropagator,
    optimize_query,
    reset_optimizer_cache,
)

from .models import (
    ColleaguesOf,
    Company,
    Department,
    Employee,
    MemberOf,
    Person,
    TeamMates,
    WorksFor,
)


class TestConstraintPropagation(TestCase):
    """Test constraint propagation across variables with the same name."""

    def setUp(self):
        """Set up test data."""
        self.propagator = ConstraintPropagator()

    def test_single_constraint_propagation(self):
        """Test that a single constraint propagates to all instances of a variable."""
        # Create fact patterns with one constrained variable
        patterns = [
            WorksFor(Var("emp", where=Q(is_manager=True)), Var("company")),
            MemberOf(Var("emp"), Var("dept")),  # Should get the constraint
            TeamMates(Var("emp"), Var("other")),  # Should get the constraint
        ]

        # Apply constraint propagation
        result = self.propagator.propagate_constraints(patterns)

        # All instances of "emp" should have the constraint
        self.assertIsNotNone(result[0].subject.where)
        self.assertIsNotNone(result[1].subject.where)
        self.assertIsNotNone(result[2].subject.where)

        # Check that the constraint is correct
        expected_constraint = Q(is_manager=True)
        self.assertEqual(str(result[0].subject.where), str(expected_constraint))
        self.assertEqual(str(result[1].subject.where), str(expected_constraint))
        self.assertEqual(str(result[2].subject.where), str(expected_constraint))

    def test_multiple_constraints_anded_together(self):
        """Test that multiple constraints on the same variable are ANDed."""
        patterns = [
            WorksFor(Var("emp", where=Q(is_manager=True)), Var("company")),
            MemberOf(Var("emp", where=Q(department="Engineering")), Var("dept")),
        ]

        result = self.propagator.propagate_constraints(patterns)

        # Both patterns should have the combined constraint
        expected_constraint = Q(is_manager=True) & Q(department="Engineering")

        # Check first pattern
        self.assertIsNotNone(result[0].subject.where)
        result_constraint = result[0].subject.where
        self.assertTrue(self._constraints_equivalent(result_constraint, expected_constraint))

        # Check second pattern
        self.assertIsNotNone(result[1].subject.where)
        result_constraint = result[1].subject.where
        self.assertTrue(self._constraints_equivalent(result_constraint, expected_constraint))

    def test_different_variables_keep_separate_constraints(self):
        """Test that different variables maintain their own constraints."""
        patterns = [
            WorksFor(Var("emp1", where=Q(is_manager=True)), Var("company")),
            WorksFor(Var("emp2", where=Q(department="Engineering")), Var("company")),
            TeamMates(Var("emp1"), Var("emp2")),
        ]

        result = self.propagator.propagate_constraints(patterns)

        # emp1 should only have is_manager constraint
        emp1_constraint = result[2].subject.where
        self.assertEqual(str(emp1_constraint), str(Q(is_manager=True)))

        # emp2 should only have department constraint
        emp2_constraint = result[2].object.where
        self.assertEqual(str(emp2_constraint), str(Q(department="Engineering")))

    def test_no_constraints_unchanged(self):
        """Test that patterns without constraints remain unchanged."""
        patterns = [
            WorksFor(Var("emp"), Var("company")),
            MemberOf(Var("emp"), Var("dept")),
        ]

        result = self.propagator.propagate_constraints(patterns)

        # All variables should remain unconstrained
        self.assertIsNone(result[0].subject.where)
        self.assertIsNone(result[0].object.where)
        self.assertIsNone(result[1].subject.where)
        self.assertIsNone(result[1].object.where)

    def test_constraint_propagation_across_subject_and_object(self):
        """Test constraint propagation when same variable appears as subject and object."""
        patterns = [
            WorksFor(Var("person", where=Q(age__gte=18)), Var("company")),
            ColleaguesOf(Var("other"), Var("person")),  # person as object
        ]

        result = self.propagator.propagate_constraints(patterns)

        # Both subject and object instances of "person" should have constraint
        self.assertIsNotNone(result[0].subject.where)
        self.assertIsNotNone(result[1].object.where)

        expected_constraint = Q(age__gte=18)
        self.assertEqual(str(result[0].subject.where), str(expected_constraint))
        self.assertEqual(str(result[1].object.where), str(expected_constraint))

    def _constraints_equivalent(self, constraint1: Q, constraint2: Q) -> bool:
        """Helper method to check if two Q objects are functionally equivalent."""
        # Simple string comparison for basic cases
        # In a real implementation, this would need more sophisticated comparison
        return str(constraint1) == str(constraint2)


class TestOptimizerPublicAPI(TestCase):
    """Test the public optimize_query function."""

    def test_optimize_query_function(self):
        """Test the public optimize_query function."""
        patterns = [
            WorksFor(Var("emp", where=Q(department="Engineering")), Var("company")),
            MemberOf(Var("emp"), Var("dept")),
        ]

        optimized = optimize_query(patterns)

        # Both patterns should have the department constraint
        self.assertIsNotNone(optimized[0].subject.where)
        self.assertIsNotNone(optimized[1].subject.where)

    def test_reset_optimizer_cache(self):
        """Test that reset_optimizer_cache works (backwards compatibility)."""
        # This should not raise an error
        reset_optimizer_cache()


class TestOptimizerIntegration(TestCase):
    """Test optimizer integration with the query system."""

    def setUp(self):
        """Set up test data."""
        # Create companies
        self.active_company = Company.objects.create(name="ActiveCorp", is_active=True)
        self.inactive_company = Company.objects.create(name="InactiveCorp", is_active=False)

        # Create departments
        self.eng_dept = Department.objects.create(name="Engineering", company=self.active_company)
        self.old_dept = Department.objects.create(name="OldDept", company=self.inactive_company)

        # Create people and employees
        self.alice = Person.objects.create(name="Alice", age=30)
        self.bob = Person.objects.create(name="Bob", age=25)
        self.charlie = Person.objects.create(name="Charlie", age=65)

        self.alice_emp = Employee.objects.create(
            person=self.alice,
            company=self.active_company,
            department=self.eng_dept,
            is_manager=True,
        )
        self.bob_emp = Employee.objects.create(
            person=self.bob, company=self.active_company, department=self.eng_dept, is_manager=False
        )
        self.charlie_emp = Employee.objects.create(
            person=self.charlie,
            company=self.inactive_company,
            department=self.old_dept,
            is_manager=False,
        )

        # Store facts
        store_facts(
            WorksFor(subject=self.alice_emp, object=self.active_company),
            WorksFor(subject=self.bob_emp, object=self.active_company),
            WorksFor(subject=self.charlie_emp, object=self.inactive_company),
            MemberOf(subject=self.alice_emp, object=self.eng_dept),
            MemberOf(subject=self.bob_emp, object=self.eng_dept),
            MemberOf(subject=self.charlie_emp, object=self.old_dept),
        )

    def test_query_with_constraint_propagation(self):
        """Test that queries automatically propagate constraints."""
        # Query with constraint on one predicate
        results = list(
            query(
                WorksFor(Var("emp1"), Var("company", where=Q(is_active=True))),
                WorksFor(Var("emp2"), Var("company")),  # Should inherit the constraint
            )
        )

        # Should only find employees at active companies
        for result in results:
            # Both employees should work for active companies due to constraint propagation
            emp1_company = result["company"]
            self.assertTrue(emp1_company.is_active)