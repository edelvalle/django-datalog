"""A fact can be backed by an existing table via @store column mapping."""

from django.db.models import Q
from django.test import TestCase

from django_datalog.models import Fact, Term, Var, query, store, store_facts

from .models import Company, Employee


class EmployedAt(Fact):
    subject: Term[Employee]
    object: Term[Company]


class ManagesAt(Fact):
    subject: Term[Employee]
    object: Term[Company]


# Bind onto the existing Employee table (its own id / company_id columns).
store(EmployedAt, subject="id", object="company_id", readonly=True)(Employee)
store(ManagesAt, subject="id", object="company_id", where=Q(is_manager=True), readonly=True)(Employee)


class MappedStorageTests(TestCase):
    def setUp(self):
        self.acme = Company.objects.create(name="Acme")
        self.alice = Employee.objects.create(company=self.acme, is_manager=True)
        self.bob = Employee.objects.create(company=self.acme)

    def test_reads_from_existing_table(self):
        pairs = {
            (r["e"], r["c"])
            for r in query(EmployedAt(Var[Employee]("e"), Var[Company]("c")), hydrate=False)
        }
        self.assertEqual(pairs, {(self.alice.pk, self.acme.pk), (self.bob.pk, self.acme.pk)})

    def test_concrete_subject_is_filtered(self):
        rows = list(query(EmployedAt(self.alice, Var[Company]("c")), hydrate=False))
        self.assertEqual([r["c"] for r in rows], [self.acme.pk])

    def test_where_restricts_the_extension(self):
        managers = {
            r["e"] for r in query(ManagesAt(Var[Employee]("e"), Var[Company]("c")), hydrate=False)
        }
        self.assertEqual(managers, {self.alice.pk})

    def test_hydrate_returns_instances(self):
        rows = list(query(EmployedAt(self.alice, Var[Company]("c"))))
        self.assertEqual([r["c"] for r in rows], [self.acme])

    def test_readonly(self):
        with self.assertRaises(ValueError):
            store_facts(EmployedAt(subject=self.alice, object=self.acme))
