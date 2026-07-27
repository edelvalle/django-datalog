"""Chained inference: rule bodies that reference other inferred facts must resolve.

Reproduces the correctness gap where a rule whose body references another
*inferred* fact returned an empty result (the intermediate level was never
materialized). See docs/PLAN-chained-inference-and-performance.md, Part 1.
"""

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

from .models import Company, ParentOf, Person, PersonWorksFor


# Inferred facts used to build multi-level chains (no DB storage).
class NetColleague(Fact, inferred=True):  # level 1: body references stored facts
    subject: Term[Person]
    object: Term[Person]


class InSameNetwork(Fact, inferred=True):  # level 2: body references NetColleague
    subject: Term[Person]
    object: Term[Person]


class NetworkL3(Fact, inferred=True):  # level 3: body references InSameNetwork
    subject: Term[Person]
    object: Term[Person]


class Ancestor(Fact, inferred=True):  # recursive: references itself
    subject: Term[Person]
    object: Term[Person]


class ChainedInferenceTests(TestCase):
    def setUp(self):
        self.acme = Company.objects.create(name="Acme")
        self.alice = Person.objects.create(name="Alice")
        self.bob = Person.objects.create(name="Bob")
        store_facts(
            PersonWorksFor(subject=self.alice, object=self.acme),
            PersonWorksFor(subject=self.bob, object=self.acme),
        )

    def _define_network_rules(self, levels: int = 2):
        """Register NetColleague(:= stored) and up to two derived levels on top."""
        a, b, c = Var[Person]("a"), Var[Person]("b"), Var[Company]("c")
        rule(
            NetColleague(a, b),
            PersonWorksFor(a, c) & PersonWorksFor(b, c),
        )
        if levels >= 2:
            rule(InSameNetwork(Var[Person]("a"), Var[Person]("b")),
                 NetColleague(Var[Person]("a"), Var[Person]("b")))
        if levels >= 3:
            rule(NetworkL3(Var[Person]("a"), Var[Person]("b")),
                 InSameNetwork(Var[Person]("a"), Var[Person]("b")))

    def test_two_level_chain(self):
        """A rule whose body is an inferred fact resolves through to stored facts."""
        with rule_context():
            self._define_network_rules(levels=2)
            level1 = {r["x"].pk for r in query(NetColleague(self.alice, Var[Person]("x")))}
            level2 = {r["x"].pk for r in query(InSameNetwork(self.alice, Var[Person]("x")))}

        self.assertIn(self.bob.pk, level2)
        self.assertEqual(level2, level1)  # the chain re-exposes level 1 exactly

    def test_three_level_chain(self):
        """A :- B, B :- C, C :- stored resolves end to end."""
        with rule_context():
            self._define_network_rules(levels=3)
            level1 = {r["x"].pk for r in query(NetColleague(self.alice, Var[Person]("x")))}
            level3 = {r["x"].pk for r in query(NetworkL3(self.alice, Var[Person]("x")))}

        self.assertIn(self.bob.pk, level3)
        self.assertEqual(level3, level1)

    def test_recursive_transitive_closure(self):
        """A recursive rule returns the full closure and terminates."""
        people = [Person.objects.create(name=f"P{i}") for i in range(4)]
        store_facts(*[ParentOf(subject=people[i], object=people[i + 1]) for i in range(3)])

        with rule_context():
            a, b, c = Var[Person]("a"), Var[Person]("b"), Var[Person]("c")
            rule(Ancestor(a, b), ParentOf(a, b) | (ParentOf(a, c) & Ancestor(c, b)))
            descendants = {
                r["d"].pk for r in query(Ancestor(people[0], Var[Person]("d")))
            }

        self.assertEqual(descendants, {people[1].pk, people[2].pk, people[3].pk})

    def test_chain_hydrate_false(self):
        """Chained inference works with hydrate=False (PKs)."""
        with rule_context():
            self._define_network_rules(levels=2)
            xs = {r["x"] for r in query(InSameNetwork(self.alice, Var[Person]("x")), hydrate=False)}

        self.assertIn(self.bob.pk, xs)

    def test_chain_all_variable_positions(self):
        """Chained inference works when the outer query has all-variable positions."""
        with rule_context():
            self._define_network_rules(levels=2)
            pairs = {
                (r["a"].pk, r["b"].pk)
                for r in query(InSameNetwork(Var[Person]("a"), Var[Person]("b")))
            }

        self.assertIn((self.alice.pk, self.bob.pk), pairs)
