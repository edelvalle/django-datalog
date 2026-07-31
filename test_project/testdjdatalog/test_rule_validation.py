"""
Test rule validation functionality.
"""

from dataclasses import dataclass

from django.test import TestCase

from django_datalog.facts import Fact
from django_datalog.models import Term, Var, rule
from testdjdatalog.models import ParentOf, Person


@dataclass
class TestInferredFact(Fact):
    """An inferred (unbound) fact — valid as a rule head."""

    subject: Term[Person]
    object: Term[Person]


class RuleValidationTests(TestCase):
    """Test rule validation functionality."""

    def test_inferred_fact_as_rule_head_works(self):
        """Test that inferred facts can be used as rule heads."""
        # This should work without raising an exception
        rule(
            TestInferredFact(Var[Person]("person1"), Var[Person]("person2")),
            ParentOf(Var[Person]("parent"), Var[Person]("person1")),
        )
        # If we get here, the test passed

    def test_storable_fact_as_rule_head_fails(self):
        """Test that storable facts cannot be used as rule heads."""
        # This should raise a TypeError
        with self.assertRaises(TypeError) as context:
            rule(
                ParentOf(
                    Var[Person]("person1"), Var[Person]("person2")
                ),  # ParentOf is storable, not inferred
                ParentOf(Var[Person]("parent"), Var[Person]("person1")),
            )

        # Check that the error message is correct
        self.assertIn("stored fact", str(context.exception))
        self.assertIn("ParentOf", str(context.exception))
