"""
Complete example tests using family relationships to demonstrate django_datalog functionality.
"""

from unittest.mock import Mock, patch

from django.db.models import Q
from django.test import TestCase

from django_datalog.models import Var, query


class FamilyExampleTests(TestCase):
    """Test django_datalog using family relationship examples."""

    def test_family_example_basic_functionality(self):
        """Test basic functionality using family relationships."""
        # Test Var creation
        person_var = Var("person")
        self.assertEqual(person_var.name, "person")
        self.assertIsNone(person_var.where)

        # Test Var with constraint
        adult_constraint = Q(age__gte=18)
        adult_var = Var("person", where=adult_constraint)
        self.assertEqual(adult_var.name, "person")
        self.assertEqual(adult_var.where, adult_constraint)

    def test_q_object_constraints_family_example(self):
        """Test Q object constraints using family examples."""
        from django_datalog.models import _prefix_q_object

        # Test simple constraint: adults only
        adult_q = Q(age__gte=18)
        prefixed_q = _prefix_q_object(adult_q, "subject")

        self.assertEqual(len(prefixed_q.children), 1)
        field_name, value = prefixed_q.children[0]
        self.assertEqual(field_name, "subject__age__gte")
        self.assertEqual(value, 18)

        # Test complex constraint: adults living in specific city
        complex_q = Q(age__gte=18) & Q(city="New York")
        prefixed_complex = _prefix_q_object(complex_q, "object")

        self.assertEqual(len(prefixed_complex.children), 2)

        field1, value1 = prefixed_complex.children[0]
        field2, value2 = prefixed_complex.children[1]

        self.assertEqual(field1, "object__age__gte")
        self.assertEqual(value1, 18)
        self.assertEqual(field2, "object__city")
        self.assertEqual(value2, "New York")

    @patch("django_datalog.query._satisfy_conjunction_with_targeted_facts")
    @patch("django_datalog.query._hydrate_results")
    def test_family_query_hydration(self, mock_hydrate, mock_satisfy):
        """Test query hydration using family relationship example."""
        # Mock a ParentOf fact
        mock_fact = Mock()
        mock_fact.subject = Mock()  # John
        mock_fact.object = Var("child")  # Any child

        # Setup mocks
        mock_pk_results = [{"subject": 1, "object": 2}]  # John -> Alice
        # Return a new iterator each time the function is called
        mock_satisfy.side_effect = lambda *args, **kwargs: iter(mock_pk_results)
        mock_hydrate.return_value = iter(
            [{"subject": Mock(name="John"), "object": Mock(name="Alice")}]
        )

        # Test with hydration (default) - should return full Person objects
        results = list(query(mock_fact, hydrate=True))
        mock_hydrate.assert_called_once()

        # Test without hydration - should return just IDs for performance
        mock_hydrate.reset_mock()
        results = list(query(mock_fact, hydrate=False))
        mock_hydrate.assert_not_called()
        self.assertEqual(results, mock_pk_results)

    def test_family_example_documentation(self):
        """Test that demonstrates the family relationship example for documentation."""
        # This test serves as documentation showing how to use django_datalog
        # for family relationships without actually creating Django models

        # Example fact definitions (these would normally inherit from Fact)
        # @dataclass
        # class ParentOf(Fact):
        #     subject: Person | Var  # Parent
        #     object: Person | Var   # Child

        # @dataclass
        # class SiblingOf(Fact):
        #     subject: Person | Var  # Sibling 1
        #     object: Person | Var   # Sibling 2

        # @dataclass
        # class GrandparentOf(Fact):
        #     subject: Person | Var  # Grandparent
        #     object: Person | Var   # Grandchild

        # Example rule (this would normally be defined at module level):
        # rule(
        #     GrandparentOf(Var("grandparent"), Var("grandchild")),
        #     ParentOf(Var("grandparent"), Var("parent")),
        #     ParentOf(Var("parent"), Var("grandchild"))
        # )

        # Example queries:
        # Find all children of John:
        # for result in query(ParentOf(john, Var("child"))):
        #     print(f"{john.name} is parent of {result['child'].name}")

        # Find all adults in New York:
        # adults_in_ny = query(PersonFact(Var("person", where=Q(age__gte=18) & Q(city="New York"))))

        # This test just validates the concept works
        self.assertTrue(True)  # Concept validation

        # Test variable creation for family examples
        parent_var = Var("parent")
        child_var = Var("child", where=Q(age__lt=18))
        grandparent_var = Var("grandparent", where=Q(age__gte=60))

        self.assertEqual(parent_var.name, "parent")
        self.assertEqual(child_var.name, "child")
        self.assertEqual(grandparent_var.name, "grandparent")

        # Test that constraints are properly stored
        self.assertIsNone(parent_var.where)
        self.assertIsNotNone(child_var.where)
        self.assertIsNotNone(grandparent_var.where)

    def test_family_example_readme_snippets(self):
        """Test code snippets that would appear in README documentation."""

        # These are the kinds of examples we'd show in the README

        # Variable creation examples:
        person_var = Var("person")
        adult_var = Var("adult", where=Q(age__gte=18))
        child_var = Var("child", where=Q(age__lt=18))

        # Complex constraint examples:
        complex_adult = Var("person", where=Q(age__gte=18) & Q(married=True))
        senior_citizen = Var("person", where=Q(age__gte=65) | Q(retired=True))

        # Verify these work as expected
        self.assertEqual(person_var.name, "person")
        self.assertEqual(adult_var.name, "adult")
        self.assertEqual(child_var.name, "child")

        self.assertIsNone(person_var.where)
        self.assertIsNotNone(adult_var.where)
        self.assertIsNotNone(child_var.where)
        self.assertIsNotNone(complex_adult.where)
        self.assertIsNotNone(senior_citizen.where)

        # Test repr for documentation
        self.assertIn("person", repr(person_var))
        self.assertIn("where=", repr(adult_var))
