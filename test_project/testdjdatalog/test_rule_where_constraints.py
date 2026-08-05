"""Regression: a Var(where=Q(...)) constraint in a rule body must be enforced
at join time, not only when loading stored facts. Rules deriving the same head
share one fact base, so a row admitted by one rule's load-time filter must not
satisfy another rule's join. See GitHub issue #1."""

from django.contrib.auth.models import User
from django.db.models import Q
from django.test import TestCase

from django_datalog.models import (
    Fact,
    Term,
    Var,
    query,
    rule,
    rule_context,
    store_facts,
)

from .models import Crew, Rank, Vessel


class Staff(Fact):  # inferred (no @store)
    user: Term[User]
    vessel: Term[Vessel]
    role: Term[str]


class WhereLeaksAcrossRulesTests(TestCase):
    def setUp(self):
        self.ana = User.objects.create(username="ana", email="ana@kaikosystems.com")
        self.bob = User.objects.create(username="bob", email="bob@example.com")
        self.aurora = Vessel.objects.create(name="Aurora")
        store_facts(
            Crew(user=self.ana, rank=Rank.MASTER, vessel=self.aurora),
            Crew(user=self.bob, rank=Rank.CHIEF_MATE, vessel=self.aurora),
        )

    def test_where_constraints_are_enforced_per_rule(self):
        kaiko = Q(email__endswith="@kaikosystems.com")
        with rule_context():
            rule(
                Staff(Var("u"), Var("v"), "admin"),
                Crew(Var("u", where=kaiko), Var("rank"), Var("v")),
            )
            rule(
                Staff(Var("u"), Var("v"), "crew"),
                Crew(Var("u", where=~kaiko), Var("rank"), Var("v")),
            )
            results = {
                (r["u"].username, r["role"])
                for r in query(Staff(Var("u"), Var("v"), Var("role")))
            }
        self.assertEqual(results, {("ana", "admin"), ("bob", "crew")})

    def test_single_rule_still_correct(self):
        # A single constrained rule was already correct through load-time
        # filtering; confirm the join-time enforcement keeps it so.
        kaiko = Q(email__endswith="@kaikosystems.com")
        with rule_context():
            rule(
                Staff(Var("u"), Var("v"), "admin"),
                Crew(Var("u", where=kaiko), Var("rank"), Var("v")),
            )
            results = {
                (r["u"].username, r["role"])
                for r in query(Staff(Var("u"), Var("v"), Var("role")))
            }
        self.assertEqual(results, {("ana", "admin")})
