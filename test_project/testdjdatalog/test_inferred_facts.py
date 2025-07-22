"""
Test inferred facts functionality - facts that are computed via rules only.
"""

from dataclasses import dataclass

from django.test import TestCase

from django_datalog.models import Fact, Var, query, rule, store_facts
from testdjdatalog.models import Person, PersonWorksFor


@dataclass
class HasDirectAccess(Fact, inferred=True):
    """Person has direct access to a company (inferred-only fact)."""

    subject: Person | Var
    object: Person | Var  # Using Person for simplicity in tests


class InferredFactsTests(TestCase):
    """Test inferred facts functionality."""

    def setUp(self):
        """Set up test data."""
        self.alice = Person.objects.create(name="Alice")
        self.bob = Person.objects.create(name="Bob")
        self.charlie = Person.objects.create(name="Charlie")

    def test_inferred_fact_no_django_model(self):
        """Test that inferred facts don't get Django models."""
        self.assertTrue(HasDirectAccess._is_inferred)
        self.assertIsNone(HasDirectAccess._django_model)

        self.assertFalse(PersonWorksFor._is_inferred)
        self.assertIsNotNone(PersonWorksFor._django_model)

    def test_cannot_store_inferred_facts(self):
        """Test that inferred facts cannot be stored."""
        with self.assertRaises(ValueError) as cm:
            store_facts(HasDirectAccess(subject=self.alice, object=self.bob))

        self.assertIn("Cannot store inferred fact", str(cm.exception))
        self.assertIn("computed automatically from rules", str(cm.exception))

    def test_inferred_facts_computed_via_rules(self):
        """Test that inferred facts are computed via inference rules."""
        # Rule: HasDirectAccess(child, parent) if parent->child
        from testdjdatalog.models import ParentOf

        rule(
            HasDirectAccess(Var("child"), Var("parent")),
            ParentOf(
                Var("parent"), Var("child")
            ),  # If parent->child, then child has access to parent
        )

        # Store base facts using existing fact type
        store_facts(
            ParentOf(subject=self.alice, object=self.bob),
            ParentOf(subject=self.bob, object=self.charlie),
        )

        # Query inferred facts
        results = list(query(HasDirectAccess(Var("user"), Var("target"))))

        # Should have 2 HasDirectAccess facts inferred from ParentOf facts
        self.assertEqual(len(results), 2)

        user_target_pairs = {(r["user"], r["target"]) for r in results}
        expected_pairs = {
            (self.bob, self.alice),
            (self.charlie, self.bob),
        }  # Child has access to parent
        self.assertEqual(user_target_pairs, expected_pairs)

    def test_basic_query_without_rules(self):
        """Test that inferred facts return empty when no rules are defined."""
        # Query inferred facts without any rules
        results = list(query(HasDirectAccess(Var("user"), Var("target"))))

        # Should have no results since no rules are defined
        self.assertEqual(len(results), 0)
