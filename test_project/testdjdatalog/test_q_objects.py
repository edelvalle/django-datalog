"""
Tests for Q object constraints in django_datalog queries.
"""

from django.db.models import Q
from django.test import TestCase

from django_datalog.models import Var, _prefix_q_object


class QObjectTests(TestCase):
    """Test Q object constraint functionality."""

    def test_simple_q_object_prefixing(self):
        """Test that simple Q objects are prefixed correctly."""
        simple_q = Q(archived=False)
        prefixed_q = _prefix_q_object(simple_q, "object")

        # Check that the field was prefixed
        self.assertEqual(len(prefixed_q.children), 1)
        field_name, value = prefixed_q.children[0]
        self.assertEqual(field_name, "object__archived")
        self.assertEqual(value, False)

    def test_complex_q_object_and(self):
        """Test Q object with AND operations."""
        complex_q = Q(archived=False) & Q(name__icontains="test")
        prefixed_complex = _prefix_q_object(complex_q, "subject")

        # Should have 2 children for the AND operation
        self.assertEqual(len(prefixed_complex.children), 2)

        # Check first condition
        field1, value1 = prefixed_complex.children[0]
        self.assertEqual(field1, "subject__archived")
        self.assertEqual(value1, False)

        # Check second condition
        field2, value2 = prefixed_complex.children[1]
        self.assertEqual(field2, "subject__name__icontains")
        self.assertEqual(value2, "test")

    def test_complex_q_object_or(self):
        """Test Q object with OR operations."""
        nested_q = Q(archived=False) | Q(name="special")
        prefixed_nested = _prefix_q_object(nested_q, "object")

        # Check connector is preserved
        self.assertEqual(prefixed_nested.connector, Q.OR)

        # Check both conditions are prefixed
        self.assertEqual(len(prefixed_nested.children), 2)
        field1, value1 = prefixed_nested.children[0]
        field2, value2 = prefixed_nested.children[1]

        self.assertEqual(field1, "object__archived")
        self.assertEqual(value1, False)
        self.assertEqual(field2, "object__name")
        self.assertEqual(value2, "special")

    def test_var_with_where_clause(self):
        """Test that Var with where clause is created correctly."""
        q_constraint = Q(archived=False)
        vessel_var = Var("vessel", where=q_constraint)

        # Check the Var has the constraint
        self.assertEqual(vessel_var.name, "vessel")
        self.assertIsNotNone(vessel_var.where)
        self.assertEqual(vessel_var.where, q_constraint)

    def test_var_without_constraint(self):
        """Test Var without constraint."""
        simple_var = Var("vessel")

        self.assertEqual(simple_var.name, "vessel")
        self.assertIsNone(simple_var.where)

    def test_var_repr_with_constraint(self):
        """Test Var string representation with constraint."""
        q_constraint = Q(archived=False)
        vessel_var = Var("vessel", where=q_constraint)

        repr_str = repr(vessel_var)
        self.assertIn("vessel", repr_str)
        self.assertIn("where=", repr_str)

    def test_var_repr_without_constraint(self):
        """Test Var string representation without constraint."""
        simple_var = Var("vessel")

        repr_str = repr(simple_var)
        self.assertIn("vessel", repr_str)
        self.assertNotIn("where=", repr_str)

    def test_nested_q_objects(self):
        """Test deeply nested Q objects."""
        nested = (Q(archived=False) & Q(active=True)) | Q(special=True)
        prefixed = _prefix_q_object(nested, "test")

        # Should preserve the overall OR structure
        self.assertEqual(prefixed.connector, Q.OR)
        self.assertEqual(len(prefixed.children), 2)

        # First child should be the AND group
        and_child = prefixed.children[0]
        if hasattr(and_child, "connector"):
            self.assertEqual(and_child.connector, Q.AND)

        # Check that all fields are properly prefixed
        # This is a more complex test that verifies recursive prefixing works
        def check_all_fields_prefixed(q_obj, expected_prefix):
            for child in q_obj.children:
                if isinstance(child, tuple):
                    field_name, _ = child
                    self.assertTrue(field_name.startswith(f"{expected_prefix}__"))
                elif hasattr(child, "children"):
                    check_all_fields_prefixed(child, expected_prefix)

        check_all_fields_prefixed(prefixed, "test")
