"""N-ary relations: a fact can have more than two positions, mixing entities
(FKs) with typed values (an enum member)."""

from django.contrib.auth.models import User
from django.db.models import Q
from django.test import TestCase

from django_datalog.models import (
    Fact,
    Term,
    Var,
    exists,
    query,
    retract_facts,
    rule,
    rule_context,
    store_facts,
)

from .models import Crew, Rank, Vessel


class NaryStorageTests(TestCase):
    """Store, retract, and query a ternary Crew(user, rank, vessel) relation."""

    def setUp(self):
        self.alice = User.objects.create(username="alice")
        self.bob = User.objects.create(username="bob")
        self.aurora = Vessel.objects.create(name="Aurora")
        self.borealis = Vessel.objects.create(name="Borealis")

        store_facts(
            Crew(user=self.alice, rank=Rank.MASTER, vessel=self.aurora),
            Crew(user=self.bob, rank=Rank.FIRST_ENGINEER, vessel=self.aurora),
            Crew(user=self.alice, rank=Rank.CHIEF_MATE, vessel=self.borealis),
        )

    def test_positions_recorded_in_order(self):
        self.assertEqual(Crew._positions, ("user", "rank", "vessel"))

    def test_query_all(self):
        rows = {
            (r["u"], r["r"], r["v"])
            for r in query(
                Crew(Var[User]("u"), Var[Rank]("r"), Var[Vessel]("v")), hydrate=False
            )
        }
        self.assertEqual(
            rows,
            {
                (self.alice.pk, Rank.MASTER, self.aurora.pk),
                (self.bob.pk, Rank.FIRST_ENGINEER, self.aurora.pk),
                (self.alice.pk, Rank.CHIEF_MATE, self.borealis.pk),
            },
        )

    def test_pin_value_position(self):
        # Who is a master anywhere?
        masters = {
            r["u"]
            for r in query(
                Crew(Var[User]("u"), Rank.MASTER, Var[Vessel]("v")), hydrate=False
            )
        }
        self.assertEqual(masters, {self.alice.pk})

    def test_pin_two_positions(self):
        # Which vessel does alice serve on as chief mate?
        rows = list(
            query(Crew(self.alice, Rank.CHIEF_MATE, Var[Vessel]("v")), hydrate=False)
        )
        self.assertEqual([r["v"] for r in rows], [self.borealis.pk])

    def test_pin_entity_position(self):
        # Every rank/vessel alice holds.
        rows = {
            (r["r"], r["v"])
            for r in query(
                Crew(self.alice, Var[Rank]("r"), Var[Vessel]("v")), hydrate=False
            )
        }
        self.assertEqual(
            rows,
            {(Rank.MASTER, self.aurora.pk), (Rank.CHIEF_MATE, self.borealis.pk)},
        )

    def test_hydrate_entities_keep_value(self):
        # Entity positions hydrate to instances; the value position stays its value.
        rows = list(query(Crew(self.alice, Rank.MASTER, Var[Vessel]("v"))))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["v"], self.aurora)

    def test_where_on_entity_position(self):
        rows = {
            r["u"]
            for r in query(
                Crew(
                    Var[User]("u"),
                    Rank.MASTER,
                    Var[Vessel]("v", where=Q(name="Aurora")),
                ),
                hydrate=False,
            )
        }
        self.assertEqual(rows, {self.alice.pk})

    def test_exists(self):
        self.assertTrue(exists(Crew(self.alice, Rank.MASTER, self.aurora)))
        self.assertFalse(exists(Crew(self.bob, Rank.MASTER, self.aurora)))

    def test_retract(self):
        retract_facts(Crew(user=self.alice, rank=Rank.MASTER, vessel=self.aurora))
        self.assertFalse(exists(Crew(self.alice, Rank.MASTER, self.aurora)))
        # The other crew rows are untouched.
        self.assertTrue(exists(Crew(self.alice, Rank.CHIEF_MATE, self.borealis)))


class SeniorCrew(Fact):
    """Inferred: a user holds a senior rank aboard a vessel."""

    user: Term[User]
    vessel: Term[Vessel]


class NaryInferenceTests(TestCase):
    """Rules can read an N-ary fact in their body and derive from it."""

    def setUp(self):
        self.alice = User.objects.create(username="alice")
        self.bob = User.objects.create(username="bob")
        self.aurora = Vessel.objects.create(name="Aurora")
        store_facts(
            Crew(user=self.alice, rank=Rank.MASTER, vessel=self.aurora),
            Crew(user=self.bob, rank=Rank.FIRST_ENGINEER, vessel=self.aurora),
        )

    def test_rule_over_nary_body(self):
        # A master is senior crew.
        with rule_context():
            rule(
                SeniorCrew(Var[User]("u"), Var[Vessel]("v")),
                Crew(Var[User]("u"), Rank.MASTER, Var[Vessel]("v")),
            )
            seniors = {
                r["u"]
                for r in query(
                    SeniorCrew(Var[User]("u"), Var[Vessel]("v")), hydrate=False
                )
            }
        self.assertEqual(seniors, {self.alice.pk})
