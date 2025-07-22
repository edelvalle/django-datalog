"""
Test disjunctive (OR) rules functionality.

This demonstrates the new rule syntax where:
- Lists represent disjunctive alternatives (OR)
- Tuples represent conjunctions (AND)

Examples:
  # Simple disjunctive rule
  rule(
      HasAccess(Var("user"), Var("resource")),
      [
          IsOwner(Var("user"), Var("resource")),      # OR
          IsAdmin(Var("user"))                        # OR
      ]
  )

  # Mixed disjunctive and conjunctive rule
  rule(
      HasAccess(Var("user"), Var("vessel")),
      [
          ShoreStaffOf(Var("user"), Var("vessel")),   # OR
          KaikoStaffOf(Var("user"), Var("vessel")),   # OR
          CrewOf(Var("user"), Var("vessel")),         # OR
          (                                           # OR (conjunction)
              MemberOf(Var("user"), Var("company")),  # AND
              Owns(Var("company"), Var("vessel")),    # AND
          ),
      ]
  )
"""

from dataclasses import dataclass

from django.test import TestCase

from django_datalog.models import Fact, Var, query, rule, rule_context, store_facts
from testdjdatalog.models import IsAdmin, IsManager, ManagerOf, MemberOf, ParentOf, Person, WorksFor


@dataclass
class HasAuthority(Fact, inferred=True):
    """Person has authority over another person (inferred-only)."""
    subject: Person | Var
    object: Person | Var


@dataclass
class CanEdit(Fact, inferred=True):
    """Person can edit another person's data (inferred-only)."""
    subject: Person | Var
    object: Person | Var


class DisjunctiveRulesTests(TestCase):
    """Test disjunctive rule functionality with the new syntax."""

    def setUp(self):
        """Set up test data."""
        # Create test people
        self.alice = Person.objects.create(name="Alice")
        self.bob = Person.objects.create(name="Bob")
        self.charlie = Person.objects.create(name="Charlie")
        self.diana = Person.objects.create(name="Diana")


    @rule_context
    def test_simple_disjunctive_rule(self):
        """Test a simple disjunctive rule with two alternatives."""
        # Rule: HasAuthority(user, target) :- IsManager(user, target) OR IsAdmin(user, target)
        rule(
            HasAuthority(Var("user"), Var("target")),
            [
                IsManager(Var("user"), Var("target")),  # Alternative 1: Manager relationship
                IsAdmin(Var("user"), Var("target"))     # Alternative 2: Admin relationship
            ]
        )

        # Store base facts
        store_facts(
            IsManager(subject=self.alice, object=self.bob),    # Alice manages Bob
            IsAdmin(subject=self.charlie, object=self.diana)   # Charlie is admin of Diana
        )

        # Query inferred facts
        results = list(query(HasAuthority(Var("user"), Var("target"))))

        # Should have 2 HasAuthority facts from both alternatives
        self.assertEqual(len(results), 2)

        user_target_pairs = {(r["user"], r["target"]) for r in results}
        expected_pairs = {(self.alice, self.bob), (self.charlie, self.diana)}
        self.assertEqual(user_target_pairs, expected_pairs)

    @rule_context
    def test_conjunctive_alternative_in_disjunctive_rule(self):
        """Test disjunctive rule with one alternative being a conjunction."""
        # Rule: CanEdit(user, target) :-
        #   IsAdmin(user, target) OR
        #   [IsManager(user, target) AND ParentOf(user, target)]
        rule(
            CanEdit(Var("user"), Var("target")),
            [
                IsAdmin(Var("user"), Var("target")),               # Alternative 1: Admin
                (                                                  # Alternative 2: Manager AND Parent
                    IsManager(Var("user"), Var("target")),
                    ParentOf(Var("user"), Var("target"))
                )
            ]
        )

        # Store base facts
        store_facts(
            IsAdmin(subject=self.alice, object=self.bob),      # Alice is admin of Bob
            IsManager(subject=self.charlie, object=self.diana), # Charlie manages Diana
            ParentOf(subject=self.charlie, object=self.diana)  # Charlie is parent of Diana
        )

        # Query inferred facts
        results = list(query(CanEdit(Var("user"), Var("target"))))

        # Should have 2 CanEdit facts:
        # - Alice->Bob (admin)
        # - Charlie->Diana (manager AND parent)
        self.assertEqual(len(results), 2)

        user_target_pairs = {(r["user"], r["target"]) for r in results}
        expected_pairs = {
            (self.alice, self.bob),      # From IsAdmin
            (self.charlie, self.diana)   # From IsManager AND ParentOf
        }
        self.assertEqual(user_target_pairs, expected_pairs)

    @rule_context
    def test_multiple_conjunctions_in_disjunctive_rule(self):
        """Test disjunctive rule with multiple conjunctive alternatives."""
        # Rule: HasAuthority(user, target) :-
        #   [IsManager(user, target) AND IsAdmin(user, target)] OR
        #   [ParentOf(user, target) AND IsManager(user, other)]
        rule(
            HasAuthority(Var("user"), Var("target")),
            [
                (                                                  # Alternative 1
                    IsManager(Var("user"), Var("target")),
                    IsAdmin(Var("user"), Var("target"))
                ),
                (                                                  # Alternative 2
                    ParentOf(Var("user"), Var("target")),
                    IsManager(Var("user"), Var("other"))  # User must be manager of someone
                )
            ]
        )

        # Store base facts
        store_facts(
            IsManager(subject=self.alice, object=self.bob),    # Alice manages Bob
            IsAdmin(subject=self.alice, object=self.bob),      # Alice is admin of Bob
            ParentOf(subject=self.charlie, object=self.diana), # Charlie is parent of Diana
            IsManager(subject=self.charlie, object=self.alice) # Charlie manages Alice
        )

        # Query inferred facts
        results = list(query(HasAuthority(Var("user"), Var("target"))))

        # Should have 2 HasAuthority facts:
        # - Alice->Bob (manager AND admin)
        # - Charlie->Diana (parent AND manager of someone)
        self.assertEqual(len(results), 2)

        user_target_pairs = {(r["user"], r["target"]) for r in results}
        expected_pairs = {
            (self.alice, self.bob),      # Manager AND Admin
            (self.charlie, self.diana)   # Parent AND Manager of other
        }
        self.assertEqual(user_target_pairs, expected_pairs)