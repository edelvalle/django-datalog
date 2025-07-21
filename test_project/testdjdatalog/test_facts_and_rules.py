"""
Tests for django_datalog facts and rules using real Django models.
"""

from django.db.models import Q
from django.test import TestCase

from django_datalog.models import Var, query, retract_facts, store_facts

from .models import (
    Company,
    GrandparentOf,
    ParentOf,
    Person,
    PersonColleaguesOf,
    PersonWorksFor,
    SiblingOf,
)


class FactsAndRulesTests(TestCase):
    """Test fact storage/retrieval and rule inference."""

    def setUp(self):
        """Set up test data."""
        # Create people
        self.john = Person.objects.create(name="John", age=65, city="New York", married=True)
        self.alice = Person.objects.create(name="Alice", age=40, city="New York", married=True)
        self.bob = Person.objects.create(name="Bob", age=18, city="Boston", married=False)
        self.charlie = Person.objects.create(name="Charlie", age=10, city="New York", married=False)

        # Create company
        self.company = Company.objects.create(name="ACME Corp", active=True)

    def test_basic_fact_storage_and_retrieval(self):
        """Test storing and retrieving facts."""
        # Store parent relationships
        store_facts(
            ParentOf(subject=self.john, object=self.alice),  # John -> Alice
            ParentOf(subject=self.alice, object=self.bob),  # Alice -> Bob
            ParentOf(subject=self.alice, object=self.charlie),  # Alice -> Charlie
        )

        # Query Alice's children
        alice_children = list(query(ParentOf(self.alice, Var("child"))))
        self.assertEqual(len(alice_children), 2)

        child_names = {result["child"].name for result in alice_children}
        self.assertEqual(child_names, {"Bob", "Charlie"})

    def test_fact_constraints_with_q_objects(self):
        """Test fact queries with Q object constraints."""
        # Store facts
        store_facts(
            PersonWorksFor(subject=self.alice, object=self.company),
            PersonWorksFor(subject=self.bob, object=self.company),
        )

        # Query for people in New York who work at the company
        ny_workers = list(
            query(PersonWorksFor(Var("person", where=Q(city="New York")), self.company))
        )

        self.assertEqual(len(ny_workers), 1)  # Only Alice
        self.assertEqual(ny_workers[0]["person"].name, "Alice")

    def test_grandparent_inference_rule(self):
        """Test inference rules work correctly."""
        # Rules are automatically loaded from rules.py
        # Store parent relationships
        store_facts(
            ParentOf(subject=self.john, object=self.alice),  # John -> Alice
            ParentOf(subject=self.alice, object=self.bob),  # Alice -> Bob
            ParentOf(subject=self.alice, object=self.charlie),  # Alice -> Charlie
        )

        # Query for John's grandchildren (should be inferred)
        john_grandchildren = list(query(GrandparentOf(self.john, Var("grandchild"))))
        self.assertEqual(len(john_grandchildren), 2)

        grandchild_names = {result["grandchild"].name for result in john_grandchildren}
        self.assertEqual(grandchild_names, {"Bob", "Charlie"})

    def test_sibling_inference_rule(self):
        """Test sibling inference rule."""
        # Rules are automatically loaded from rules.py
        # Store parent relationships
        store_facts(
            ParentOf(subject=self.alice, object=self.bob),  # Alice -> Bob
            ParentOf(subject=self.alice, object=self.charlie),  # Alice -> Charlie
        )

        # Query for Bob's siblings
        bob_siblings = list(query(SiblingOf(self.bob, Var("sibling"))))

        # Should include Charlie and Bob himself (rule doesn't exclude self)
        self.assertEqual(len(bob_siblings), 2)
        sibling_names = {result["sibling"].name for result in bob_siblings}
        self.assertEqual(sibling_names, {"Bob", "Charlie"})

    def test_colleagues_inference_rule(self):
        """Test colleagues inference rule."""
        # Rules are automatically loaded from rules.py
        # Store work relationships
        store_facts(
            PersonWorksFor(subject=self.alice, object=self.company),
            PersonWorksFor(subject=self.bob, object=self.company),
        )

        # Query for Alice's colleagues
        alice_colleagues = list(query(PersonColleaguesOf(self.alice, Var("colleague"))))

        # Should include Bob and Alice herself
        self.assertEqual(len(alice_colleagues), 2)
        colleague_names = {result["colleague"].name for result in alice_colleagues}
        self.assertEqual(colleague_names, {"Alice", "Bob"})

    def test_fact_retraction(self):
        """Test that facts can be retracted."""
        # Store a fact
        store_facts(ParentOf(subject=self.john, object=self.alice))

        # Verify it exists
        results = list(query(ParentOf(self.john, Var("child"))))
        self.assertEqual(len(results), 1)

        # Retract the fact
        retract_facts(ParentOf(subject=self.john, object=self.alice))

        # Verify it's gone
        results = list(query(ParentOf(self.john, Var("child"))))
        self.assertEqual(len(results), 0)

    def test_complex_constraints_with_rules(self):
        """Test complex Q constraints work with inference rules."""
        # Rules are automatically loaded from rules.py
        # Store relationships
        store_facts(
            ParentOf(subject=self.john, object=self.alice),
            ParentOf(subject=self.alice, object=self.bob),
            ParentOf(subject=self.alice, object=self.charlie),
        )

        # Query for John's adult grandchildren
        adult_grandchildren = list(
            query(GrandparentOf(self.john, Var("grandchild", where=Q(age__gte=18))))
        )

        self.assertEqual(len(adult_grandchildren), 1)  # Only Bob (age 18)
        self.assertEqual(adult_grandchildren[0]["grandchild"].name, "Bob")
