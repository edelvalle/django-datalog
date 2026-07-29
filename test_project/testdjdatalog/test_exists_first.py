"""Tests for exists() / first() (and async aexists/afirst): single-result queries."""

from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.test import TestCase

from django_datalog.models import (
    Fact,
    Term,
    Var,
    aexists,
    afirst,
    exists,
    first,
    query,
    rule,
    rule_context,
    store_facts,
)

from .models import Company, Person, PersonWorksFor


class Colleague(Fact, inferred=True):
    subject: Term[Person]
    object: Term[Person]


class ExistsFirstTests(TestCase):
    def setUp(self):
        self.acme = Company.objects.create(name="Acme")
        self.alice = Person.objects.create(name="Alice")
        self.bob = Person.objects.create(name="Bob")
        self.carol = Person.objects.create(name="Carol")  # no PersonWorksFor
        store_facts(
            PersonWorksFor(subject=self.alice, object=self.acme),
            PersonWorksFor(subject=self.bob, object=self.acme),
        )

    # ---- exists ----
    def test_exists_true_for_stored_fact(self):
        self.assertTrue(exists(PersonWorksFor(self.alice, self.acme)))

    def test_exists_false_when_no_match(self):
        self.assertFalse(exists(PersonWorksFor(self.carol, Var[Company]("c"))))

    def test_exists_true_for_inferred_fact(self):
        with rule_context():
            a, b, c = Var[Person]("a"), Var[Person]("b"), Var[Company]("c")
            rule(Colleague(a, b), PersonWorksFor(a, c) & PersonWorksFor(b, c))
            # alice and bob are colleagues (same company)
            self.assertTrue(exists(Colleague(self.alice, self.bob)))
            self.assertFalse(exists(Colleague(self.alice, self.carol)))

    # ---- first ----
    def test_first_returns_a_single_result(self):
        row = first(PersonWorksFor(Var[Person]("p"), self.acme))
        self.assertIsNotNone(row)
        self.assertIn(row["p"], (self.alice, self.bob))

    def test_first_returns_none_when_no_match(self):
        self.assertIsNone(first(PersonWorksFor(self.carol, Var[Company]("c"))))

    def test_first_hydrate_false_returns_pks(self):
        row = first(PersonWorksFor(self.alice, Var[Company]("c")), hydrate=False)
        self.assertEqual(row, {"c": self.acme.pk})

    def test_first_agrees_with_query(self):
        got = first(PersonWorksFor(Var[Person]("p"), self.acme), hydrate=False)
        all_rows = list(query(PersonWorksFor(Var[Person]("p"), self.acme), hydrate=False))
        self.assertIn(got, all_rows)

    # ---- short-circuit (deterministic, not timing-based) ----
    def test_exists_stops_deriving_after_first(self):
        """exists derives ~one fact; a full query derives the whole extension."""
        import django_datalog.query as q

        # 40 people at one company -> alice has 40 colleagues.
        company = Company.objects.create(name="Big")
        people = Person.objects.bulk_create([Person(name=f"B{i}") for i in range(40)])
        store_facts(*[PersonWorksFor(subject=p, object=company) for p in people])
        alice = people[0]

        with rule_context():
            a, b, c = Var[Person]("a"), Var[Person]("b"), Var[Company]("c")
            rule(Colleague(a, b), PersonWorksFor(a, c) & PersonWorksFor(b, c))

            with patch.object(q, "_instantiate_fact", wraps=q._instantiate_fact) as spy:
                exists(Colleague(alice, Var[Person]("x")))
            exists_derivations = spy.call_count

            with patch.object(q, "_instantiate_fact", wraps=q._instantiate_fact) as spy:
                list(query(Colleague(alice, Var[Person]("x")), hydrate=False))
            full_derivations = spy.call_count

        self.assertLessEqual(exists_derivations, 2)   # stopped at the first match
        self.assertGreaterEqual(full_derivations, 40)  # full derives everything
        self.assertLess(exists_derivations, full_derivations)

    # ---- async ----
    def test_async_variants(self):
        self.assertTrue(async_to_sync(aexists)(PersonWorksFor(self.alice, self.acme)))
        self.assertIsNone(
            async_to_sync(afirst)(PersonWorksFor(self.carol, Var[Company]("c")))
        )
        row = async_to_sync(afirst)(PersonWorksFor(self.alice, Var[Company]("c")), hydrate=False)
        self.assertEqual(row, {"c": self.acme.pk})
