"""Regression guard: a bound single-subject inferred query scales ~linearly.

See docs/PLAN-chained-inference-and-performance.md, Part 2.

History: on a ~13k-fact production dataset a single-user ``CanAccessVessel``
query (answer: 1 row) did not return in 70s and the heaviest user (1458 rows)
did not return in 5 min. The cost tracked the *derived-set* size, not the
answer size: even with a bound subject the engine derived the whole relation
over the neighbourhood (O(neighbourhood²)) and filtered afterwards.

Fixed by goal-directed rule specialization (``_specialize_rule`` in query.py):
a non-recursive rule's head is bound to the query's concrete positions before
evaluation, so only the answer rows are derived. ``Colleague`` over N
co-workers at one company now runs in O(N) instead of O(N²).

Run:
    PYTHONPATH=.. uv run python manage.py test testdjdatalog.test_perf_single_subject -v2
"""

import time

from django.test import TestCase

from django_datalog.models import Fact, Term, Var, query, rule, rule_context, store_facts

from .models import Company, Person, PersonWorksFor


class Colleague(Fact):
    subject: Term[Person]
    object: Term[Person]


class DerivedSetDedupScalingTests(TestCase):
    """``Colleague(first, Var)`` over N co-workers must scale ~linearly in N."""

    def _seed(self, n: int) -> Person:
        company = Company.objects.create(name="Acme")
        people = Person.objects.bulk_create([Person(name=f"P{i}") for i in range(n)])
        store_facts(*[PersonWorksFor(subject=p, object=company) for p in people])
        return people[0]

    def test_bound_subject_scales_linearly(self):
        timings = {}
        for n in (250, 500, 1000, 2000):
            with rule_context():
                first = self._seed(n)
                a, b, c = Var[Person]("a"), Var[Person]("b"), Var[Company]("c")
                rule(Colleague(a, b), PersonWorksFor(a, c) & PersonWorksFor(b, c))

                start = time.perf_counter()
                result = list(query(Colleague(first, Var[Person]("x")), hydrate=False))
                elapsed = time.perf_counter() - start

            timings[n] = elapsed
            self.assertEqual(len(result), n)  # first person's colleagues = everyone
            print(f"n={n:>5} co-workers -> {elapsed:8.3f}s ({elapsed / n * 1000:.3f} ms/row)")

        print(f"scaling: {timings}")
        # Doubling N should ~double the time (linear), not quadruple it (quadratic).
        ratio = timings[2000] / timings[1000]
        self.assertLess(
            ratio,
            3.0,
            f"2x the derived facts took {ratio:.1f}x longer (want ~2x): {timings}",
        )
