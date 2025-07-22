"""
Test inferred facts functionality - facts that are computed via rules only.
"""

from dataclasses import dataclass

from django.test import TestCase
from testdjdatalog.models import Person, PersonWorksFor

from django_datalog.models import Fact, Var, query, rule, store_facts


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

    def test_vessel_access_pattern_with_disjunctive_rules(self):
        """Test the vessel access pattern using the new disjunctive rule syntax."""

        @dataclass
        class VesselShoreStaff(Fact):
            subject: Person | Var
            object: Person | Var  # Using Person as vessel for simplicity

        @dataclass
        class VesselCrew(Fact):
            subject: Person | Var
            object: Person | Var

        @dataclass
        class CompanyMember(Fact):
            subject: Person | Var
            object: Person | Var  # Person as company

        @dataclass
        class CompanyOwns(Fact):
            subject: Person | Var  # Company
            object: Person | Var  # Vessel

        # Define the vessel access rule with multiple alternatives:
        # HasDirectAccess(user, vessel) :-
        #   VesselShoreStaff(user, vessel) OR
        #   VesselCrew(user, vessel) OR
        #   [CompanyMember(user, company) AND CompanyOwns(company, vessel)]
        rule(
            HasDirectAccess(Var("user"), Var("vessel")),
            VesselShoreStaff(Var("user"), Var("vessel"))  # Alternative 1: Direct shore staff
            | VesselCrew(Var("user"), Var("vessel"))  # Alternative 2: Direct crew
            | (
                CompanyMember(Var("user"), Var("company"))  # Alternative 3: Company membership
                & CompanyOwns(Var("company"), Var("vessel"))
            ),
        )

        # Store base facts
        store_facts(
            VesselShoreStaff(subject=self.alice, object=self.bob),  # Alice is shore staff of Bob
            VesselCrew(subject=self.charlie, object=self.bob),  # Charlie is crew of Bob
            CompanyMember(
                subject=self.alice, object=self.charlie
            ),  # Alice is member of Charlie's company
            CompanyOwns(subject=self.charlie, object=self.alice),  # Charlie's company owns Alice
        )

        # Query inferred facts
        results = list(query(HasDirectAccess(Var("user"), Var("vessel"))))

        # Should have 3 HasDirectAccess facts:
        # - Alice->Bob (shore staff)
        # - Charlie->Bob (crew)
        # - Alice->Alice (company member with access to owned vessel)
        self.assertEqual(len(results), 3)

        user_vessel_pairs = {(r["user"], r["vessel"]) for r in results}
        expected_pairs = {
            (self.alice, self.bob),  # Shore staff
            (self.charlie, self.bob),  # Crew
            (self.alice, self.alice),  # Company member
        }
        self.assertEqual(user_vessel_pairs, expected_pairs)

    def test_basic_query_without_rules(self):
        """Test that inferred facts return empty when no rules are defined."""
        # Query inferred facts without any rules
        results = list(query(HasDirectAccess(Var("user"), Var("target"))))

        # Should have no results since no rules are defined
        self.assertEqual(len(results), 0)
