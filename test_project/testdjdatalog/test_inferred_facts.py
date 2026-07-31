"""
Test inferred facts functionality - facts that are computed via rules only.
"""

from dataclasses import dataclass

from django.test import TestCase

from django_datalog.models import Fact, Term, Var, query, rule, store_facts
from testdjdatalog.models import Person, PersonWorksFor


@dataclass
class HasDirectAccess(Fact):
    """Person has direct access to a company (inferred-only fact)."""

    subject: Term[Person]
    object: Term[Person]  # Using Person for simplicity in tests


class InferredFactsTests(TestCase):
    """Test inferred facts functionality."""

    def setUp(self):
        """Set up test data."""
        self.alice = Person.objects.create(name="Alice")
        self.bob = Person.objects.create(name="Bob")
        self.charlie = Person.objects.create(name="Charlie")

    def test_inferred_fact_has_no_storage(self):
        """An inferred (unbound) fact has no storage model; a stored one does."""
        self.assertIsNone(HasDirectAccess._django_model)
        self.assertIsNotNone(PersonWorksFor._django_model)

    def test_cannot_store_inferred_facts(self):
        """An unbound (inferred) fact cannot be stored."""
        with self.assertRaises(ValueError) as cm:
            store_facts(HasDirectAccess(subject=self.alice, object=self.bob))

        self.assertIn("has no storage", str(cm.exception))

    def test_inferred_facts_computed_via_rules(self):
        """Test that inferred facts are computed via inference rules."""
        # Rule: HasDirectAccess(child, parent) if parent->child
        from testdjdatalog.models import ParentOf

        rule(
            HasDirectAccess(Var[Person]("child"), Var[Person]("parent")),
            ParentOf(
                Var[Person]("parent"), Var[Person]("child")
            ),  # If parent->child, then child has access to parent
        )

        # Store base facts using existing fact type
        store_facts(
            ParentOf(subject=self.alice, object=self.bob),
            ParentOf(subject=self.bob, object=self.charlie),
        )

        # Query inferred facts
        results = list(query(HasDirectAccess(Var[Person]("user"), Var[Person]("target"))))

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
        results = list(query(HasDirectAccess(Var[Person]("user"), Var[Person]("target"))))

        # Should have no results since no rules are defined
        self.assertEqual(len(results), 0)
