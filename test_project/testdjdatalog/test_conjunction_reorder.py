"""The conjunction solver picks the most-constrained condition first. A broad
condition written before a selective one must not force the broad relation to
be reloaded once per row of the broad relation."""

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from django_datalog.models import Var, query, store_facts

from .models import Company, Employee, ManagerOf, WorksFor


class ConjunctionReorderTests(TestCase):
    N = 100  # broad relation size

    def setUp(self):
        self.co = Company.objects.create(name="Acme")
        self.emps = [Employee.objects.create(company=self.co) for _ in range(self.N)]
        self.boss = self.emps[0]
        store_facts(*[WorksFor(subject=e, object=self.co) for e in self.emps])
        # The boss manages just three employees (the selective relation).
        store_facts(*[ManagerOf(subject=self.boss, object=self.emps[i]) for i in (1, 2, 3)])

    def test_broad_first_still_cheap(self):
        # WorksFor (all N) written before ManagerOf(boss, ...) (only 3 rows).
        # Solving the selective, concrete-anchored condition first keeps this to
        # a handful of queries; the naive left-to-right order would reload the
        # concrete condition once per WorksFor row (~N queries).
        pats = (WorksFor(Var("emp"), Var("co")), ManagerOf(self.boss, Var("emp")))
        with CaptureQueriesContext(connection) as ctx:
            rows = list(query(*pats, hydrate=False))

        self.assertEqual(len(rows), 3)  # the three managed employees
        self.assertLess(
            len(ctx.captured_queries),
            self.N // 2,
            f"expected few queries, got {len(ctx.captured_queries)} for N={self.N}",
        )

    def test_result_is_order_independent(self):
        # The same query written the other way returns the same answer.
        a = {r["emp"] for r in query(
            WorksFor(Var("emp"), Var("co")), ManagerOf(self.boss, Var("emp")), hydrate=False
        )}
        b = {r["emp"] for r in query(
            ManagerOf(self.boss, Var("emp")), WorksFor(Var("emp"), Var("co")), hydrate=False
        )}
        self.assertEqual(a, b)
        self.assertEqual(len(a), 3)
