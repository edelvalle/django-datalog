"""
Tests for context-local rules in django_datalog.
Tests that rules defined within rule_context are only active within that context.
"""

from django.test import TestCase

from django_datalog.models import Fact, Var, get_rules, query, rule, rule_context, store_facts

from .models import (
    ColleaguesOf,
    Company,
    Department,
    Employee,
    MemberOf,
    Person,
    TeamMates,
    WorksFor,
)


class TestContextTeammates(Fact):
    """Test-specific fact that won't conflict with global rules."""

    subject: Employee | Var  # Employee 1
    object: Employee | Var  # Employee 2


class ContextRulesTests(TestCase):
    """Test context-local rules functionality."""

    def setUp(self):
        """Set up test data."""
        # Create companies
        self.active_company = Company.objects.create(
            name="ActiveCorp", is_active=True, founded_year=2010
        )
        self.inactive_company = Company.objects.create(
            name="InactiveCorp", is_active=False, founded_year=2015
        )

        # Create departments
        self.eng_dept = Department.objects.create(
            name="Engineering", company=self.active_company, budget=100000
        )
        self.hr_dept = Department.objects.create(
            name="HR", company=self.active_company, budget=50000
        )
        self.old_dept = Department.objects.create(
            name="Old Department", company=self.inactive_company, budget=25000
        )

        # Create people
        self.alice = Person.objects.create(name="Alice", age=30, married=True)
        self.bob = Person.objects.create(name="Bob", age=25, married=False)
        self.charlie = Person.objects.create(name="Charlie", age=65, retired=True)

        # Create employees
        self.alice_emp = Employee.objects.create(
            person=self.alice,
            company=self.active_company,
            department=self.eng_dept,
            is_manager=True,
            salary=90000,
        )
        self.bob_emp = Employee.objects.create(
            person=self.bob,
            company=self.active_company,
            department=self.eng_dept,
            is_manager=False,
            salary=70000,
        )
        self.charlie_emp = Employee.objects.create(
            person=self.charlie,
            company=self.inactive_company,
            department=self.old_dept,
            is_manager=False,
            salary=50000,
        )

        # Create basic facts
        store_facts(
            WorksFor(subject=self.alice_emp, object=self.active_company),
            WorksFor(subject=self.bob_emp, object=self.active_company),
            WorksFor(subject=self.charlie_emp, object=self.inactive_company),
            MemberOf(subject=self.alice_emp, object=self.eng_dept),
            MemberOf(subject=self.bob_emp, object=self.eng_dept),
            MemberOf(subject=self.charlie_emp, object=self.old_dept),
        )

    def test_context_rules_are_isolated(self):
        """Test that rules defined in context are not active outside context."""
        # Store initial rule count
        initial_rule_count = len(get_rules())

        # Outside context - no test teammates should be inferred
        # (TestContextTeammates has no global rules)
        teammates_outside = list(query(TestContextTeammates(Var("emp1"), Var("emp2"))))
        self.assertEqual(len(teammates_outside), 0)

        # Inside context - teammates should be inferred
        with rule_context():
            rule(
                TestContextTeammates(Var("emp1"), Var("emp2")),
                MemberOf(Var("emp1"), Var("dept")),
                MemberOf(Var("emp2"), Var("dept")),
            )

            # Rules should be active here
            teammates_inside = list(query(TestContextTeammates(Var("emp1"), Var("emp2"))))
            self.assertGreater(len(teammates_inside), 0)

            # Should find Alice and Bob as teammates
            teammate_names = set()
            for result in teammates_inside:
                emp1_name = result["emp1"].person.name if result["emp1"].person else "Unknown"
                emp2_name = result["emp2"].person.name if result["emp2"].person else "Unknown"
                teammate_names.add(emp1_name)
                teammate_names.add(emp2_name)

            self.assertIn("Alice", teammate_names)
            self.assertIn("Bob", teammate_names)

        # Outside context again - no test teammates should be inferred
        teammates_after = list(query(TestContextTeammates(Var("emp1"), Var("emp2"))))
        self.assertEqual(len(teammates_after), 0)

        # Rule count should be back to original
        final_rule_count = len(get_rules())
        self.assertEqual(initial_rule_count, final_rule_count)

    def test_context_rules_with_arguments(self):
        """Test context manager with rules passed as arguments."""
        with rule_context(
            # Rule passed as tuple: (head, body1, body2, ...)
            (
                ColleaguesOf(Var("emp1"), Var("emp2")),
                WorksFor(Var("emp1"), Var("company")),
                WorksFor(Var("emp2"), Var("company")),
            )
        ):
            colleagues = list(query(ColleaguesOf(Var("emp1"), Var("emp2"))))

            # Should find Alice and Bob as colleagues (same company)
            colleague_names = set()
            for result in colleagues:
                emp1_name = result["emp1"].person.name if result["emp1"].person else "Unknown"
                emp2_name = result["emp2"].person.name if result["emp2"].person else "Unknown"
                colleague_names.add(emp1_name)
                colleague_names.add(emp2_name)

            self.assertIn("Alice", colleague_names)
            self.assertIn("Bob", colleague_names)

            # Charlie works at a different company, so shouldn't be colleagues with Alice/Bob
            alice_charlie_colleagues = any(
                (
                    result["emp1"].person
                    and result["emp1"].person.name == "Alice"
                    and result["emp2"].person
                    and result["emp2"].person.name == "Charlie"
                )
                or (
                    result["emp1"].person
                    and result["emp1"].person.name == "Charlie"
                    and result["emp2"].person
                    and result["emp2"].person.name == "Alice"
                )
                for result in colleagues
            )
            self.assertFalse(alice_charlie_colleagues)

    def test_multiple_context_rules(self):
        """Test multiple rules in the same context."""
        with rule_context():
            # Rule 1: Teammates based on department
            rule(
                TeamMates(Var("emp1"), Var("emp2")),
                MemberOf(Var("emp1"), Var("dept")),
                MemberOf(Var("emp2"), Var("dept")),
            )

            # Rule 2: Colleagues based on company
            rule(
                ColleaguesOf(Var("emp1"), Var("emp2")),
                WorksFor(Var("emp1"), Var("company")),
                WorksFor(Var("emp2"), Var("company")),
            )

            # Both rules should be active
            teammates = list(query(TeamMates(Var("emp1"), Var("emp2"))))
            colleagues = list(query(ColleaguesOf(Var("emp1"), Var("emp2"))))

            self.assertGreater(len(teammates), 0)
            self.assertGreater(len(colleagues), 0)

    def test_nested_rule_contexts(self):
        """Test nested rule contexts."""
        with rule_context():
            # Outer context rule
            rule(
                ColleaguesOf(Var("emp1"), Var("emp2")),
                WorksFor(Var("emp1"), Var("company")),
                WorksFor(Var("emp2"), Var("company")),
            )

            # Should have colleagues here
            colleagues_outer = list(query(ColleaguesOf(Var("emp1"), Var("emp2"))))
            test_teammates_outer = list(query(TestContextTeammates(Var("emp1"), Var("emp2"))))

            self.assertGreater(len(colleagues_outer), 0)
            self.assertEqual(len(test_teammates_outer), 0)  # No test teammate rule yet

            with rule_context():
                # Inner context rule
                rule(
                    TestContextTeammates(Var("emp1"), Var("emp2")),
                    MemberOf(Var("emp1"), Var("dept")),
                    MemberOf(Var("emp2"), Var("dept")),
                )

                # Should have both colleagues (from outer) and test teammates (from inner)
                colleagues_inner = list(query(ColleaguesOf(Var("emp1"), Var("emp2"))))
                test_teammates_inner = list(query(TestContextTeammates(Var("emp1"), Var("emp2"))))

                self.assertGreater(len(colleagues_inner), 0)
                self.assertGreater(len(test_teammates_inner), 0)

            # Back to outer context - should still have colleagues but not test teammates
            colleagues_back = list(query(ColleaguesOf(Var("emp1"), Var("emp2"))))
            test_teammates_back = list(query(TestContextTeammates(Var("emp1"), Var("emp2"))))

            self.assertGreater(len(colleagues_back), 0)
            self.assertEqual(len(test_teammates_back), 0)

    def test_context_preserves_global_rules(self):
        """Test that context doesn't interfere with existing global rules."""
        # Note: ColleaguesOf rule already exists globally, so we don't need to add it

        # Should work before context (global rule is active)
        colleagues_before = list(query(ColleaguesOf(Var("emp1"), Var("emp2"))))
        self.assertGreater(len(colleagues_before), 0)

        # Test teammates should not exist (no global rule for TestContextTeammates)
        test_teammates_before = list(query(TestContextTeammates(Var("emp1"), Var("emp2"))))
        self.assertEqual(len(test_teammates_before), 0)

        with rule_context():
            # Add temporary rule for test teammates
            rule(
                TestContextTeammates(Var("emp1"), Var("emp2")),
                MemberOf(Var("emp1"), Var("dept")),
                MemberOf(Var("emp2"), Var("dept")),
            )

            # Both global colleagues and context test teammates should work
            colleagues_inside = list(query(ColleaguesOf(Var("emp1"), Var("emp2"))))
            test_teammates_inside = list(query(TestContextTeammates(Var("emp1"), Var("emp2"))))

            self.assertGreater(len(colleagues_inside), 0)
            self.assertGreater(len(test_teammates_inside), 0)

        # Global rule should still work after context, temporary rule should be gone
        colleagues_after = list(query(ColleaguesOf(Var("emp1"), Var("emp2"))))
        test_teammates_after = list(query(TestContextTeammates(Var("emp1"), Var("emp2"))))

        self.assertGreater(len(colleagues_after), 0)
        self.assertEqual(len(test_teammates_after), 0)  # Temporary rule should be gone
