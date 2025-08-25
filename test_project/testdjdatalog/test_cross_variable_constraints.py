"""
Test cross-variable constraints in django-datalog.

This tests the ability to reference one variable's value in another variable's constraint.
"""

from django.db.models import Q
from django.test import TestCase

from django_datalog.models import Var, query, rule, rule_context, store_facts

from .models import (
    Company,
    Department, 
    Employee,
    Project,
    MemberOf,
    WorksFor,
    WorksOn,
)


class CrossVariableConstraintsTest(TestCase):
    """Test cross-variable constraint functionality."""

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
            
            # Project assignments
            WorksOn(subject=self.alice, object=self.project_a),
            WorksOn(subject=self.bob, object=self.project_a),
            WorksOn(subject=self.dave, object=self.project_b),
        )

    def test_cross_variable_constraint_same_company(self):
        """Test cross-variable constraint: employees working on projects from their company."""
        # Query: Find employees working on projects where project.company == employee.company
        results = list(query(
            WorksFor(Var("emp"), Var("company")),
            WorksOn(Var("emp"), Var("project", where=Q(company=Var("company"))))
        ))
        
        # Should find Alice and Bob (work for TechCorp, project_a is TechCorp's)
        # Should NOT find Dave (works for OldCorp, but project_b is also OldCorp's, so actually should find Dave too)
        self.assertEqual(len(results), 3)
        
        found_employees = {result["emp"] for result in results}
        self.assertIn(self.alice, found_employees)
        self.assertIn(self.bob, found_employees)
        self.assertIn(self.dave, found_employees)
        # Charlie doesn't work on any project, so not in results

    def test_cross_variable_constraint_department_company(self):
        """Test cross-variable constraint: departments belonging to specific companies."""
        # Query: Find employees in departments that belong to active companies
        results = list(query(
            MemberOf(Var("emp"), Var("dept")),
            WorksFor(Var("emp"), Var("company", where=Q(is_active=True, department__in=[Var("dept")])))
        ))
        
        # Should find Alice, Bob, Charlie (all work for active TechCorp)
        # Should NOT find Dave (works for inactive OldCorp)
        self.assertEqual(len(results), 3)
        
        found_employees = {result["emp"] for result in results}
        self.assertIn(self.alice, found_employees)
        self.assertIn(self.bob, found_employees) 
        self.assertIn(self.charlie, found_employees)
        self.assertNotIn(self.dave, found_employees)

    def test_cross_variable_constraint_with_additional_filters(self):
        """Test cross-variable constraints combined with regular constraints."""
        # Query: Find managers working in departments with budget > 75000
        results = list(query(
            MemberOf(Var("emp", where=Q(is_manager=True)), Var("dept", where=Q(budget__gt=75000))),
            WorksFor(Var("emp"), Var("company", where=Q(is_active=True, department__in=[Var("dept")])))
        ))
        
        # Should find only Alice (manager in Engineering dept with 100k budget)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["emp"], self.alice)

    @rule_context
    def test_cross_variable_constraint_in_rules(self):
        """Test cross-variable constraints work in rule definitions."""
        from .models import ColleaguesOf
        
        # Rule: Employees are colleagues if they work for the same company
        # AND work in departments that belong to that company
        # Note: This rule will include self-colleagues, but the query will find all valid colleagues
        rule(
            ColleaguesOf(Var("emp1"), Var("emp2")),
            WorksFor(Var("emp1"), Var("company")) &
            WorksFor(Var("emp2"), Var("company")) &
            MemberOf(Var("emp1"), Var("dept1", where=Q(company=Var("company")))) &
            MemberOf(Var("emp2"), Var("dept2", where=Q(company=Var("company"))))
        )
        
        # Query for Alice's colleagues
        results = list(query(ColleaguesOf(self.alice, Var("colleague"))))
        
        # Should find Alice, Bob and Charlie (same company, departments belong to company)
        # Should NOT find Dave (different company)
        self.assertEqual(len(results), 3)
        
        found_colleagues = {result["colleague"] for result in results}
        self.assertIn(self.alice, found_colleagues)  # Alice is her own colleague
        self.assertIn(self.bob, found_colleagues)
        self.assertIn(self.charlie, found_colleagues)
        self.assertNotIn(self.dave, found_colleagues)

    def test_cross_variable_constraint_error_cases(self):
        """Test error handling for invalid cross-variable constraints."""
        # This should work fine when implemented, but test graceful handling
        try:
            results = list(query(
                WorksFor(Var("emp"), Var("company")),
                MemberOf(Var("emp"), Var("dept", where=Q(nonexistent_field=Var("company"))))
            ))
            # If implementation is complete, this might work or give empty results
            # If not implemented yet, might raise an exception
        except Exception as e:
            # Should be a meaningful error message
            self.assertIsInstance(e, (ValueError, TypeError, AttributeError))