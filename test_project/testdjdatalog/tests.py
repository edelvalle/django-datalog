"""
Django tests for django_datalog functionality using real Django models and database.
"""

from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.db.models import Q
from django.test import TransactionTestCase

from django_datalog.models import Var, query, store_facts

from .models import Company, Department, Employee, MemberOf, Project, WorksFor


class DjdatalogIntegrationTest(TransactionTestCase):
    """Test django_datalog with real Django models and database operations."""

    def setUp(self):
        """Set up test data."""

        # Create users
        self.alice = User.objects.create_user("alice", "alice@test.com", "password")
        self.bob = User.objects.create_user("bob", "bob@test.com", "password")

        # Create company
        self.tech_corp = Company.objects.create(
            name="Tech Corp", founded_year=2010, is_active=True, city="San Francisco"
        )

        # Create department
        self.engineering = Department.objects.create(
            name="Engineering", company=self.tech_corp, budget=Decimal("1000000.00")
        )

        # Create employees
        self.emp_alice = Employee.objects.create(
            user=self.alice,
            company=self.tech_corp,
            department=self.engineering,
            salary=Decimal("120000.00"),
            hire_date=date(2020, 1, 15),
            is_manager=True,
        )

        self.emp_bob = Employee.objects.create(
            user=self.bob,
            company=self.tech_corp,
            department=self.engineering,
            salary=Decimal("100000.00"),
            hire_date=date(2021, 3, 1),
            is_manager=False,
        )

        # Create project
        self.web_app = Project.objects.create(
            name="Web Application",
            company=self.tech_corp,
            start_date=date(2024, 1, 1),
            is_completed=False,
        )

    def test_basic_fact_storage_and_query(self):
        """Test basic fact storage and querying."""
        # Store facts
        store_facts(
            WorksFor(subject=self.emp_alice, object=self.tech_corp),
            WorksFor(subject=self.emp_bob, object=self.tech_corp),
            MemberOf(subject=self.emp_alice, object=self.engineering),
            MemberOf(subject=self.emp_bob, object=self.engineering),
        )

        # Query who works for Tech Corp
        tech_corp_employees = list(query(WorksFor(Var("employee"), self.tech_corp)))
        self.assertEqual(len(tech_corp_employees), 2)

        employee_names = {result["employee"].user.username for result in tech_corp_employees}
        self.assertIn("alice", employee_names)
        self.assertIn("bob", employee_names)

    def test_q_object_constraints(self):
        """Test Q object constraints with real Django models."""
        # Store facts
        store_facts(
            WorksFor(subject=self.emp_alice, object=self.tech_corp),
            WorksFor(subject=self.emp_bob, object=self.tech_corp),
        )

        # Query for managers only
        managers = list(query(WorksFor(Var("employee", where=Q(is_manager=True)), self.tech_corp)))

        self.assertEqual(len(managers), 1)  # Only Alice is a manager
        self.assertEqual(managers[0]["employee"], self.emp_alice)

    def test_hydration_control(self):
        """Test hydration parameter with real models."""
        store_facts(WorksFor(subject=self.emp_alice, object=self.tech_corp))

        # Test with hydration (default)
        hydrated_results = list(query(WorksFor(Var("employee"), self.tech_corp), hydrate=True))
        self.assertEqual(len(hydrated_results), 1)
        self.assertIsInstance(hydrated_results[0]["employee"], Employee)

        # Test without hydration
        pk_results = list(query(WorksFor(Var("employee"), self.tech_corp), hydrate=False))
        self.assertEqual(len(pk_results), 1)
        self.assertIsInstance(pk_results[0]["employee"], int)  # Should be PK

    def test_django_orm_integration(self):
        """Test that django_datalog works alongside normal Django ORM."""
        # Store facts
        store_facts(
            WorksFor(subject=self.emp_alice, object=self.tech_corp),
            MemberOf(subject=self.emp_alice, object=self.engineering),
        )

        # Combine django_datalog query with Django ORM
        fact_results = list(query(WorksFor(Var("employee"), self.tech_corp)))
        employee_from_fact = fact_results[0]["employee"]

        # Use Django ORM on the result
        self.assertEqual(employee_from_fact.user.username, "alice")
        self.assertEqual(employee_from_fact.department.name, "Engineering")
        self.assertTrue(employee_from_fact.is_manager)

    def test_performance_with_multiple_facts(self):
        """Test performance doesn't degrade with multiple facts."""
        # Store many facts
        facts_to_store = []
        for emp in [self.emp_alice, self.emp_bob]:
            facts_to_store.extend(
                [
                    WorksFor(subject=emp, object=self.tech_corp),
                    MemberOf(subject=emp, object=self.engineering),
                ]
            )

        store_facts(*facts_to_store)

        # Query should be efficient - limit database queries
        with self.assertNumQueries(16):  # Current performance (before PK hydration optimization)
            results = list(query(WorksFor(Var("employee"), self.tech_corp)))
            # Access related data to test for N+1 issues
            for result in results:
                _ = result["employee"].user.username
                _ = result["employee"].department.name


class SimpleEndToEndTest(TransactionTestCase):
    """Simple end-to-end test to verify the full pipeline works."""

    def test_full_pipeline(self):
        """Test the complete django_datalog pipeline with Django."""
        # 1. Create Django models
        user = User.objects.create_user("testuser", "test@example.com", "password")
        company = Company.objects.create(
            name="Test Co", founded_year=2020, is_active=True, city="Test City"
        )
        employee = Employee.objects.create(
            user=user,
            company=company,
            salary=Decimal("75000.00"),
            hire_date=date(2024, 1, 1),
        )

        # 2. Store facts
        store_facts(WorksFor(subject=employee, object=company))

        # 3. Query facts
        results = list(query(WorksFor(Var("emp"), company)))

        # 4. Verify results
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["emp"], employee)
        self.assertEqual(results[0]["emp"].user.username, "testuser")

        print("✅ Full django_datalog pipeline test passed!")


if __name__ == "__main__":
    # Allow running tests directly
    import django
    from django.conf import settings
    from django.test.utils import get_runner

    django.setup()
    TestRunner = get_runner(settings)
    test_runner = TestRunner()
    failures = test_runner.run_tests(["testdjdatalog"])

    if failures:
        exit(1)
