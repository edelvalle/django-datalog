"""
Basic functionality tests for django_datalog without database dependencies.
"""

from typing import Any
from unittest.mock import Mock

from django.test import TestCase

from django_datalog.models import Fact, Var, _fact_to_django_query


class _PairFact(Fact):
    """Minimal binary fact used to exercise position-driven query helpers."""

    subject: Any
    object: Any


class BasicFunctionalityTests(TestCase):
    """Test basic django_datalog functionality."""

    def test_var_creation(self):
        """Test that variables can be created."""
        var = Var("test_var")

        self.assertEqual(var.name, "test_var")
        self.assertIsNone(var.where)

    def test_var_with_constraint(self):
        """Test that variables can be created with constraints."""
        from django.db.models import Q

        constraint = Q(active=True)
        var = Var("test_var", where=constraint)

        self.assertEqual(var.name, "test_var")
        self.assertEqual(var.where, constraint)

    def test_fact_to_django_query_with_concrete_values(self):
        """Test _fact_to_django_query with concrete values."""
        # Create a fact with concrete (non-Var) positions
        mock_fact = _PairFact(subject=Mock(), object=Mock())

        query_params, q_objects = _fact_to_django_query(mock_fact)

        # Should have both subject and object in query params
        self.assertEqual(query_params["subject"], mock_fact.subject)
        self.assertEqual(query_params["object"], mock_fact.object)
        self.assertEqual(len(q_objects), 0)  # No Q objects

    def test_fact_to_django_query_with_variables(self):
        """Test _fact_to_django_query with variables."""
        subject_var = Var("subject")
        object_var = Var("object")

        # Create a fact with variable positions
        mock_fact = _PairFact(subject=subject_var, object=object_var)

        query_params, q_objects = _fact_to_django_query(mock_fact)

        # Should have no query params (all variables)
        self.assertEqual(len(query_params), 0)
        self.assertEqual(len(q_objects), 0)  # No Q objects

    def test_fact_to_django_query_with_constrained_variables(self):
        """Test _fact_to_django_query with constrained variables."""
        from django.db.models import Q

        subject_constraint = Q(active=True)
        object_constraint = Q(archived=False)

        subject_var = Var("subject", where=subject_constraint)
        object_var = Var("object", where=object_constraint)

        # Create a fact with variable positions
        mock_fact = _PairFact(subject=subject_var, object=object_var)

        query_params, q_objects = _fact_to_django_query(mock_fact)

        # Should have no direct query params
        self.assertEqual(len(query_params), 0)

        # Should have 2 Q objects (one for each constrained variable)
        self.assertEqual(len(q_objects), 2)

    def test_fact_to_django_query_mixed(self):
        """Test _fact_to_django_query with mix of concrete and variable values."""
        from django.db.models import Q

        subject = Mock()  # Concrete value
        object_var = Var("object", where=Q(active=True))  # Variable with constraint

        # Create a fact mixing a concrete subject and a variable object
        mock_fact = _PairFact(subject=subject, object=object_var)

        query_params, q_objects = _fact_to_django_query(mock_fact)

        # Should have subject in query params
        self.assertEqual(query_params["subject"], subject)
        self.assertNotIn("object", query_params)

        # Should have 1 Q object for the constrained variable
        self.assertEqual(len(q_objects), 1)

    def test_var_repr(self):
        """Test Var string representations."""
        # Simple var
        simple_var = Var("test")
        self.assertEqual(repr(simple_var), "Var('test')")

        # Var with constraint
        from django.db.models import Q

        constraint = Q(active=True)
        constrained_var = Var("test", where=constraint)
        repr_str = repr(constrained_var)

        self.assertIn("Var('test'", repr_str)
        self.assertIn("where=", repr_str)
