"""Runtime smoke test: &/| compose different fact types into rule-body structures.

The type-level guarantee (mixed-type composition type-checks) lives in
testdjdatalog/typing_check.py; this confirms the runtime shape is unchanged.
"""

from django.test import TestCase

from django_datalog.models import FactConjunction, Var

from .models import Company, Department, Employee, MemberOf, Project, WorksFor, WorksOn


class HeterogeneousCompositionTests(TestCase):
    def test_and_builds_conjunction_across_types(self):
        emp, company, project = Var[Employee]("e"), Var[Company]("c"), Var[Project]("p")
        conj = WorksFor(emp, company) & WorksOn(emp, project)
        self.assertIsInstance(conj, FactConjunction)
        self.assertEqual([type(f) for f in conj], [WorksFor, WorksOn])

    def test_or_builds_disjunction_across_types(self):
        emp, company, dept = Var[Employee]("e"), Var[Company]("c"), Var[Department]("d")
        disj = WorksFor(emp, company) | MemberOf(emp, dept)
        self.assertIsInstance(disj, list)
        self.assertEqual([type(f) for f in disj], [WorksFor, MemberOf])

    def test_or_with_nested_and(self):
        emp, company, project = Var[Employee]("e"), Var[Company]("c"), Var[Project]("p")
        disj = WorksFor(emp, company) | (WorksFor(emp, company) & WorksOn(emp, project))
        self.assertIsInstance(disj, list)
        self.assertEqual(len(disj), 2)
        self.assertIsInstance(disj[1], FactConjunction)
