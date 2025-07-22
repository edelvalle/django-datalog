"""
Test the new operator syntax for Facts: | for OR, & for AND.
"""

from dataclasses import dataclass

from django.test import TestCase

from django_datalog.models import Fact, Var, query, rule, store_facts
from testdjdatalog.models import Person


@dataclass
class IsOwner(Fact, inferred=True):
    """Owner relationship for operator tests."""

    subject: Person | Var
    object: Person | Var  # Using Person as resource for simplicity


@dataclass
class IsAdmin(Fact, inferred=True):
    """Admin relationship for operator tests."""

    subject: Person | Var
    object: Person | Var


@dataclass
class MemberOf(Fact, inferred=True):
    """Team membership for operator tests."""

    subject: Person | Var
    object: Person | Var  # Person as team


@dataclass
class TeamOwns(Fact, inferred=True):
    """Team ownership for operator tests."""

    subject: Person | Var  # Team
    object: Person | Var  # Resource


@dataclass
class HasAccess(Fact, inferred=True):
    """User has access to a resource (inferred fact for operator tests)."""

    subject: Person | Var
    object: Person | Var


class OperatorSyntaxTests(TestCase):
    """Test the new | and & operator syntax."""

    def setUp(self):
        """Set up test data."""
        self.alice = Person.objects.create(name="Alice")
        self.bob = Person.objects.create(name="Bob")
        self.charlie = Person.objects.create(name="Charlie")
        self.document = Person.objects.create(name="Document")  # Using Person as resource
        self.team = Person.objects.create(name="Team")

    def test_basic_or_operator(self):
        """Test Fact1 | Fact2 creates [Fact1, Fact2]."""
        fact1 = IsOwner(self.alice, self.document)
        fact2 = IsAdmin(self.alice, self.document)

        result = fact1 | fact2

        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], fact1)
        self.assertEqual(result[1], fact2)

    def test_basic_and_operator(self):
        """Test Fact1 & Fact2 creates (Fact1, Fact2)."""
        fact1 = MemberOf(self.alice, self.team)
        fact2 = TeamOwns(self.team, self.document)

        result = fact1 & fact2

        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], fact1)
        self.assertEqual(result[1], fact2)

    def test_list_or_fact(self):
        """Test [Fact1, Fact2] | Fact3 creates [Fact1, Fact2, Fact3]."""
        fact1 = IsOwner(self.alice, self.document)
        fact2 = IsAdmin(self.bob, self.document)
        fact3 = IsAdmin(self.charlie, self.document)

        fact_list = [fact1, fact2]
        result = fact_list | fact3

        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0], fact1)
        self.assertEqual(result[1], fact2)
        self.assertEqual(result[2], fact3)

    def test_tuple_or_fact(self):
        """Test (Fact1, Fact2) | Fact3 creates [(Fact1, Fact2), Fact3]."""
        fact1 = MemberOf(self.alice, self.team)
        fact2 = TeamOwns(self.team, self.document)
        fact3 = IsOwner(self.alice, self.document)

        fact_tuple = (fact1, fact2)
        result = fact_tuple | fact3

        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], fact_tuple)
        self.assertEqual(result[1], fact3)

    def test_tuple_and_fact(self):
        """Test (Fact1, Fact2) & Fact3 creates (Fact1, Fact2, Fact3)."""
        fact1 = MemberOf(self.alice, self.team)
        fact2 = TeamOwns(self.team, self.document)
        fact3 = IsOwner(self.alice, self.document)

        fact_tuple = (fact1, fact2)
        result = fact_tuple & fact3

        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0], fact1)
        self.assertEqual(result[1], fact2)
        self.assertEqual(result[2], fact3)

    def test_list_and_fact_raises_error(self):
        """Test [Fact1, Fact2] & Fact3 raises TypeError."""
        fact1 = IsOwner(self.alice, self.document)
        fact2 = IsAdmin(self.bob, self.document)
        fact3 = IsAdmin(self.charlie, self.document)

        fact_list = [fact1, fact2]

        with self.assertRaises(TypeError) as cm:
            fact_list & fact3

        self.assertIn("Cannot use & operator", str(cm.exception))
        self.assertIn("Lists represent disjunction", str(cm.exception))

    def test_operators_in_rules(self):
        """Test using operators in actual rules."""
        # Import from models.py since we need storable Facts
        from testdjdatalog.models import ParentOf

        # Rule using | operator: HasAccess if person is parent OR grandparent
        rule(
            HasAccess(Var("user"), Var("resource")),
            ParentOf(Var("user"), Var("resource")) | ParentOf(Var("resource"), Var("user")),
        )

        # Rule using & operator: HasAccess if both are people (using ParentOf in both directions)
        # This is a bit contrived but shows the & operator working
        rule(
            HasAccess(Var("user"), Var("resource")),
            ParentOf(Var("user"), Var("intermediate"))
            & ParentOf(Var("intermediate"), Var("resource")),
        )

        # Store facts using Person as both parent and child for simplicity
        store_facts(
            ParentOf(subject=self.alice, object=self.document),  # Alice parent of document
            ParentOf(subject=self.document, object=self.bob),  # Document parent of Bob
            ParentOf(subject=self.charlie, object=self.alice),  # Charlie parent of Alice
            ParentOf(subject=self.alice, object=self.bob),  # Alice parent of Bob
        )

        # Query for access
        results = list(query(HasAccess(Var("user"), Var("resource"))))

        # Should have access facts inferred:
        # - Alice->document (parent)
        # - Bob->document (document is parent of Bob, so Bob has access to document)
        # - Charlie->Bob (Charlie->Alice->Bob, grandparent relation)
        self.assertGreaterEqual(len(results), 2)  # At least parent and grandparent relations
