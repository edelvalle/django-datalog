"""Tests for as_queryset / aas_queryset - composable querysets from inferred queries."""

from asgiref.sync import async_to_sync
from django.test import TestCase

from django_datalog.models import (
    Fact,
    Term,
    Var,
    aas_queryset,
    as_queryset,
    query,
    rule,
    rule_context,
    store_facts,
)

from .models import Company, Person, PersonWorksFor


class Reaches(Fact):  # inferred: person reaches a company via PersonWorksFor
    subject: Term[Person]
    object: Term[Company]


class ReachedBy(Fact):
    subject: Term[Company]
    object: Term[Person]


class AsQuerysetTests(TestCase):
    def setUp(self):
        self.acme = Company.objects.create(name="Acme", is_active=True)
        self.globex = Company.objects.create(name="Globex", is_active=False)
        self.alice = Person.objects.create(name="Alice")
        self.bob = Person.objects.create(name="Bob")
        store_facts(
            PersonWorksFor(subject=self.alice, object=self.acme),
            PersonWorksFor(subject=self.alice, object=self.globex),
            PersonWorksFor(subject=self.bob, object=self.acme),
        )

    def test_returns_composable_queryset_of_objects(self):
        with rule_context():
            rule(Reaches(Var[Person]("p"), Var[Company]("c")),
                 PersonWorksFor(Var[Person]("p"), Var[Company]("c")))
            qs = as_queryset(Reaches(self.alice, Var[Company]("c")), on="object")

        # It's a real Company queryset, composable and lazy.
        self.assertEqual({c.name for c in qs}, {"Acme", "Globex"})
        self.assertEqual({c.name for c in qs.filter(is_active=True)}, {"Acme"})

    def test_matches_engine_results(self):
        with rule_context():
            rule(Reaches(Var[Person]("p"), Var[Company]("c")),
                 PersonWorksFor(Var[Person]("p"), Var[Company]("c")))
            engine_ids = {r["c"].pk for r in query(Reaches(self.alice, Var[Company]("c")))}
            qs = as_queryset(Reaches(self.alice, Var[Company]("c")), on="object")
            qs_ids = set(qs.values_list("pk", flat=True))
        self.assertEqual(qs_ids, engine_ids)

    def test_on_subject(self):
        with rule_context():
            rule(ReachedBy(Var[Company]("c"), Var[Person]("p")),
                 PersonWorksFor(Var[Person]("p"), Var[Company]("c")))
            qs = as_queryset(ReachedBy(self.acme, Var[Person]("p")), on="object", model=Person)
        self.assertEqual({p.name for p in qs}, {"Alice", "Bob"})

    def test_model_inferred_from_annotation(self):
        with rule_context():
            rule(Reaches(Var[Person]("p"), Var[Company]("c")),
                 PersonWorksFor(Var[Person]("p"), Var[Company]("c")))
            # model omitted -> inferred as Company from the fact's object annotation
            qs = as_queryset(Reaches(self.alice, Var[Company]("c")), on="object")
        self.assertEqual({c.name for c in qs}, {"Acme", "Globex"})

    def test_async_variant(self):
        with rule_context():
            rule(Reaches(Var[Person]("p"), Var[Company]("c")),
                 PersonWorksFor(Var[Person]("p"), Var[Company]("c")))
            qs = async_to_sync(aas_queryset)(Reaches(self.alice, Var[Company]("c")), on="object")
            names = {c.name for c in qs}
        self.assertEqual(names, {"Acme", "Globex"})
