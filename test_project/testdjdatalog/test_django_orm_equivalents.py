"""
Test Django ORM equivalents of cross-variable constraint queries.

This demonstrates how to write the same queries using pure Django ORM
instead of the django-datalog cross-variable constraint syntax.

NOTE: The comprehensive documentation for Django ORM equivalents has been 
moved to docs/django_orm_equivalents.md for easier reference.
"""

from django.db import connection
from django.db.models import Exists, OuterRef, Q
from django.test import TestCase
from django.test.utils import override_settings

from django_datalog.models import Var, query, store_facts

from .models import (
    Company,
    Department,
    Employee,
    MemberOf,
    Project,
    WorksFor,
    WorksOn,
)


class DjangoOrmEquivalentsTest(TestCase):
    """Test Django ORM equivalents of cross-variable constraint queries."""

    def setUp(self):
        """Set up test data."""
        # Create companies
        self.tech_corp = Company.objects.create(name="TechCorp", is_active=True)
        self.old_corp = Company.objects.create(name="OldCorp", is_active=False)

        # Create departments
        self.eng_dept = Department.objects.create(
            name="Engineering",
            company=self.tech_corp,
            budget=100000
        )
        self.sales_dept = Department.objects.create(
            name="Sales",
            company=self.tech_corp,
            budget=50000
        )
        self.old_dept = Department.objects.create(
            name="Legacy",
            company=self.old_corp,
            budget=25000
        )

        # Create employees
        self.alice = Employee.objects.create(
            company=self.tech_corp,
            department=self.eng_dept,
            salary=80000,
            is_manager=True
        )
        self.bob = Employee.objects.create(
            company=self.tech_corp,
            department=self.eng_dept,
            salary=70000,
            is_manager=False
        )
        self.charlie = Employee.objects.create(
            company=self.tech_corp,
            department=self.sales_dept,
            salary=60000,
            is_manager=False
        )
        self.dave = Employee.objects.create(
            company=self.old_corp,
            department=self.old_dept,
            salary=40000,
            is_manager=False
        )

        # Create projects
        self.project_a = Project.objects.create(
            name="Project Alpha",
            company=self.tech_corp
        )
        self.project_b = Project.objects.create(
            name="Project Beta",
            company=self.old_corp
        )
        self.project_cross = Project.objects.create(
            name="Cross Project",
            company=self.old_corp
        )

        # Store facts
        store_facts(
            # Work relationships
            WorksFor(subject=self.alice, object=self.tech_corp),
            WorksFor(subject=self.bob, object=self.tech_corp),
            WorksFor(subject=self.charlie, object=self.tech_corp),
            WorksFor(subject=self.dave, object=self.old_corp),

            # Department memberships
            MemberOf(subject=self.alice, object=self.eng_dept),
            MemberOf(subject=self.bob, object=self.eng_dept),
            MemberOf(subject=self.charlie, object=self.sales_dept),
            MemberOf(subject=self.dave, object=self.old_dept),

            # Project assignments - including cross-company assignment
            WorksOn(subject=self.alice, object=self.project_a),      # Same company
            WorksOn(subject=self.bob, object=self.project_a),        # Same company
            WorksOn(subject=self.charlie, object=self.project_cross), # CROSS-COMPANY!
            WorksOn(subject=self.dave, object=self.project_b),       # Same company
        )

    def test_cross_variable_constraint_with_django_orm(self):
        """Compare django-datalog cross-variable constraint with pure Django ORM."""

        print("\n" + "="*70)
        print("CROSS-VARIABLE CONSTRAINT: DJANGO-DATALOG vs PURE DJANGO ORM")
        print("="*70)

        # Django-datalog version
        print("Django-datalog query:")
        print("query(")
        print("    WorksFor(Var('emp'), Var('company')),")
        print("    WorksOn(Var('emp'), Var('project', where=Q(company=Var('company'))))")
        print(")")

        datalog_results = list(query(
            WorksFor(Var("emp"), Var("company")),
            WorksOn(Var("emp"), Var("project", where=Q(company=Var("company"))))
        ))

        print(f"Results: {len(datalog_results)} employees")
        for result in datalog_results:
            emp = result['emp']
            company = result['company']
            project = result['project']
            print(f"  - {emp.user.username if emp.user else 'Employee'} works for {company.name} on {project.name}")

        print("\nEquivalent Django ORM query:")
        print("Employee.objects.filter(")
        print("    Exists(WorksFor.objects.filter(subject=OuterRef('pk'), object=OuterRef('company'))),")
        print("    Exists(WorksOn.objects.filter(")
        print("        subject=OuterRef('pk'),")
        print("        object__company=OuterRef('company')")
        print("    ))")
        print(")")

        # Pure Django ORM equivalent
        from .models import WorksForStorage, WorksOnStorage

        # Find employees who work for companies AND work on projects from those same companies
        orm_employees = Employee.objects.filter(
            # Must have a WorksFor relationship
            Exists(WorksForStorage.objects.filter(
                subject=OuterRef('pk')
            )),
            # Must work on projects from their company
            Exists(WorksOnStorage.objects.filter(
                subject=OuterRef('pk'),
                object__company=OuterRef('company')
            ))
        ).select_related('company')

        orm_results = list(orm_employees)
        print(f"Results: {len(orm_results)} employees")
        for emp in orm_results:
            print(f"  - {emp.user.username if emp.user else 'Employee'} works for {emp.company.name}")

        # Verify same results
        datalog_employees = {result['emp'] for result in datalog_results}
        orm_employees_set = set(orm_results)
        self.assertEqual(datalog_employees, orm_employees_set)
        self.assertEqual(len(datalog_results), len(orm_results))

    def test_complex_cross_variable_constraint_with_django_orm(self):
        """Compare complex cross-variable constraint with Django ORM."""

        print("\n" + "="*70)
        print("COMPLEX CROSS-VARIABLE CONSTRAINT: DJANGO-DATALOG vs DJANGO ORM")
        print("="*70)

        # Django-datalog version (this one falls back to original approach)
        print("Django-datalog query:")
        print("query(")
        print("    MemberOf(Var('emp'), Var('dept')),")
        print("    WorksFor(Var('emp'), Var('company', where=Q(is_active=True, department__in=[Var('dept')])))")
        print(")")

        datalog_results = list(query(
            MemberOf(Var("emp"), Var("dept")),
            WorksFor(Var("emp"), Var("company", where=Q(is_active=True, department__in=[Var("dept")])))
        ))

        print(f"Results: {len(datalog_results)} employees")

        print("\nEquivalent Django ORM query:")
        print("Employee.objects.filter(")
        print("    company__is_active=True,")
        print("    department__company=F('company')")
        print(")")

        # Pure Django ORM equivalent
        from django.db.models import F

        orm_employees = Employee.objects.filter(
            company__is_active=True,
            department__company=F('company')  # Department belongs to the same company
        ).select_related('company', 'department')

        orm_results = list(orm_employees)
        print(f"Results: {len(orm_results)} employees")
        for emp in orm_results:
            print(f"  - {emp.user.username if emp.user else 'Employee'} in {emp.department.name} at {emp.company.name}")

        # Verify same results
        datalog_employees = {result['emp'] for result in datalog_results}
        orm_employees_set = set(orm_results)
        self.assertEqual(datalog_employees, orm_employees_set)

    @override_settings(DEBUG=True)
    def test_performance_comparison(self):
        """Compare performance of django-datalog vs pure Django ORM."""

        print("\n" + "="*70)
        print("PERFORMANCE COMPARISON: DJANGO-DATALOG vs PURE DJANGO ORM")
        print("="*70)

        # Test django-datalog performance
        initial_queries = len(connection.queries)

        datalog_results = list(query(
            WorksFor(Var("emp"), Var("company")),
            WorksOn(Var("emp"), Var("project", where=Q(company=Var("company"))))
        ))

        datalog_query_count = len(connection.queries) - initial_queries
        print(f"Django-datalog query count: {datalog_query_count}")

        # Test pure Django ORM performance
        initial_queries = len(connection.queries)

        from .models import WorksForStorage, WorksOnStorage

        orm_results = list(Employee.objects.filter(
            Exists(WorksForStorage.objects.filter(subject=OuterRef('pk'))),
            Exists(WorksOnStorage.objects.filter(
                subject=OuterRef('pk'),
                object__company=OuterRef('company')
            ))
        ).select_related('company'))

        orm_query_count = len(connection.queries) - initial_queries
        print(f"Pure Django ORM query count: {orm_query_count}")

        # Show the SQL
        print("\nDjango ORM SQL:")
        for query_info in connection.queries[-orm_query_count:]:
            print(f"  {query_info['sql']}")

        print("\nPerformance Analysis:")
        print(f"- Django-datalog: {datalog_query_count} queries (optimized)")
        print(f"- Pure Django ORM: {orm_query_count} queries")

        if datalog_query_count < orm_query_count:
            improvement = ((orm_query_count - datalog_query_count) / orm_query_count) * 100
            print(f"- Django-datalog is {improvement:.1f}% more efficient")
        elif orm_query_count < datalog_query_count:
            improvement = ((datalog_query_count - orm_query_count) / datalog_query_count) * 100
            print(f"- Pure Django ORM is {improvement:.1f}% more efficient")
        else:
            print("- Both approaches use the same number of queries")

        # Verify same results
        datalog_employees = {result['emp'] for result in datalog_results}
        orm_employees_set = set(orm_results)
        self.assertEqual(datalog_employees, orm_employees_set)

    def test_django_orm_cheat_sheet(self):
        """Provide a cheat sheet for converting django-datalog to Django ORM."""

        print("\n" + "="*70)
        print("DJANGO-DATALOG TO DJANGO ORM CONVERSION CHEAT SHEET")
        print("="*70)

        examples = [
            {
                "description": "Simple cross-variable constraint",
                "datalog": """query(
    WorksFor(Var("emp"), Var("company")),
    WorksOn(Var("emp"), Var("project", where=Q(company=Var("company"))))
)""",
                "orm": """Employee.objects.filter(
    Exists(WorksForStorage.objects.filter(subject=OuterRef('pk'))),
    Exists(WorksOnStorage.objects.filter(
        subject=OuterRef('pk'),
        object__company=OuterRef('company')
    ))
)"""
            },
            {
                "description": "Department-company relationship",
                "datalog": """query(
    MemberOf(Var("emp"), Var("dept")),
    WorksFor(Var("emp"), Var("company", where=Q(department__in=[Var("dept")])))
)""",
                "orm": """Employee.objects.filter(
    department__company=F('company')
)"""
            },
            {
                "description": "Same entity in multiple facts",
                "datalog": """query(
    WorksFor(Var("emp"), Var("company")),
    MemberOf(Var("emp"), Var("dept", where=Q(company=Var("company"))))
)""",
                "orm": """Employee.objects.filter(
    department__company=F('company')
)"""
            }
        ]

        for i, example in enumerate(examples, 1):
            print(f"\n{i}. {example['description']}")
            print("   Django-datalog:")
            for line in example['datalog'].split('\n'):
                print(f"   {line}")
            print("   Django ORM:")
            for line in example['orm'].split('\n'):
                print(f"   {line}")

        print("\nKey Patterns:")
        print("- Var('field', where=Q(related_field=Var('other'))) → F('related_field') = F('other_field')")
        print("- Cross-variable constraints → Exists() with OuterRef()")
        print("- Multiple facts with same variable → JOIN conditions")
        print("- Complex constraints → Subqueries or F() expressions")
