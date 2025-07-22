"""
Test rule validation functionality.
"""

from dataclasses import dataclass

from django.test import TestCase

from django_datalog.facts import Fact
from django_datalog.models import Var, rule
from testdjdatalog.models import Person, ParentOf


@dataclass
class TestInferredFact(Fact, inferred=True):
    """A fact that is marked as inferred (should work as rule head)."""
    subject: Person | Var
    object: Person | Var


class RuleValidationTests(TestCase):
    """Test rule validation functionality."""

    def test_inferred_fact_as_rule_head_works(self):
        """Test that inferred facts can be used as rule heads."""
        # This should work without raising an exception
        rule(
            TestInferredFact(Var("person1"), Var("person2")),
            ParentOf(Var("parent"), Var("person1"))
        )
        # If we get here, the test passed

    def test_storable_fact_as_rule_head_fails(self):
        """Test that storable facts cannot be used as rule heads."""
        # This should raise a TypeError
        with self.assertRaises(TypeError) as context:
            rule(
                ParentOf(Var("person1"), Var("person2")),  # ParentOf is storable, not inferred
                ParentOf(Var("parent"), Var("person1"))
            )
        
        # Check that the error message is correct
        self.assertIn("must be marked with inferred=True", str(context.exception))
        self.assertIn("ParentOf", str(context.exception))