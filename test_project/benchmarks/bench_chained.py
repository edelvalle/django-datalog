#!/usr/bin/env python
"""Baseline performance benchmark for django-datalog inferred queries.

Reproduces the production-shaped slowness reported downstream: concrete-subject
inferred queries that scan whole relations and join them in Python, so a query
returning a handful of rows still does O(all-facts) — sometimes >45s.

Not part of the test suite. Run:

    make benchmark                       # from test_project/
    make benchmark ARGS="--sizes 10000,100000 --queries concrete,chained"

Each query reports wall-clock, result count, and SQL statements issued. Queries
that exceed --cap report TIMEOUT (the interesting baseline signal) instead of
hanging. Everything runs against a throwaway test database.
"""

import argparse
import os
import time

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "testsite.settings")
django.setup()

from django.db import connection  # noqa: E402
from django.test.runner import DiscoverRunner  # noqa: E402
from django.test.utils import (  # noqa: E402
    CaptureQueriesContext,
    setup_test_environment,
    teardown_test_environment,
)

from django_datalog.models import (  # noqa: E402
    Fact,
    Term,
    Var,
    query,
    reset_optimizer_cache,
    rule,
    store_facts,
)
from django_datalog.rules import _rules  # noqa: E402
from testdjdatalog.models import Company, ParentOf, Person, PersonWorksFor  # noqa: E402


# Inferred facts modelling the access-control shape (self-join + chain + recursion).
class Colleague(Fact):  # AND-join: two people at the same company
    subject: Term[Person]
    object: Term[Person]


class InNetwork(Fact):  # chain: re-exposes Colleague (level 2)
    subject: Term[Person]
    object: Term[Person]


class Ancestor(Fact):  # recursive: transitive closure over ParentOf
    subject: Term[Person]
    object: Term[Person]


def _clear_db():
    PersonWorksFor._django_model.objects.all().delete()
    ParentOf._django_model.objects.all().delete()
    Person.objects.all().delete()
    Company.objects.all().delete()


def seed(num_people: int, fan_out: int, ancestor_depth: int):
    """Seed `num_people` across companies of `fan_out` members, plus a ParentOf chain."""
    num_companies = (num_people // fan_out) + 1
    companies = Company.objects.bulk_create(
        [Company(name=f"C{i}") for i in range(num_companies)], batch_size=5000
    )
    people = Person.objects.bulk_create(
        [Person(name=f"U{i}") for i in range(num_people)], batch_size=5000
    )
    wf = PersonWorksFor._django_model
    wf.objects.bulk_create(
        [wf(subject=people[i], object=companies[i // fan_out]) for i in range(num_people)],
        batch_size=5000,
    )

    chain = Person.objects.bulk_create([Person(name=f"A{i}") for i in range(ancestor_depth + 1)])
    po = ParentOf._django_model
    po.objects.bulk_create([po(subject=chain[i], object=chain[i + 1]) for i in range(ancestor_depth)])
    return people, chain


def _define_rules():
    _rules.clear()
    a, b, c = Var[Person]("a"), Var[Person]("b"), Var[Company]("c")
    rule(Colleague(a, b), PersonWorksFor(a, c) & PersonWorksFor(b, c))
    rule(InNetwork(Var[Person]("a"), Var[Person]("b")), Colleague(Var[Person]("a"), Var[Person]("b")))
    pa, pb, pc = Var[Person]("a"), Var[Person]("b"), Var[Person]("c")
    rule(Ancestor(pa, pb), ParentOf(pa, pb) | (ParentOf(pa, pc) & Ancestor(pc, pb)))


def timed(label: str, fn):
    reset_optimizer_cache()
    with CaptureQueriesContext(connection) as ctx:
        start = time.perf_counter()
        n = fn()
        dt = (time.perf_counter() - start) * 1000
    print(f"  {label:<44}{dt:10.1f} ms{n:>9} rows{len(ctx.captured_queries):>5} SQL", flush=True)


def timed_reorder_compare(label: str, fn):
    """Run a conjunction with the freedom-based reorder ON, then OFF, for contrast."""
    import django_datalog.query as _q

    timed(f"{label} [reorder ON]", fn)
    original = _q._freedom_score
    _q._freedom_score = lambda condition, bindings: 0.0  # disable: keep written order
    try:
        timed(f"{label} [reorder OFF]", fn)
    finally:
        _q._freedom_score = original


def run_scale(num_people: int, fan_out: int, ancestor_depth: int, queries: set[str]):
    _clear_db()
    people, chain = seed(num_people, fan_out, ancestor_depth)
    _define_rules()
    alice = people[0]

    total_pairs = (num_people // fan_out) * fan_out * fan_out
    print(
        f"\n=== N={num_people:,} people, {fan_out}/company "
        f"(~{total_pairs:,} colleague pairs), ancestor_depth={ancestor_depth} ===",
        flush=True,
    )
    cases = [
        ("stored", "stored: PersonWorksFor(Var, Var)",
         lambda: len(list(query(PersonWorksFor(Var[Person]("p"), Var[Company]("c")))))),
        ("concrete", "inferred concrete-subject: Colleague(alice, Var)",
         lambda: len(list(query(Colleague(alice, Var[Person]("x")))))),
        ("allvar", "inferred all-var: Colleague(Var, Var)",
         lambda: len(list(query(Colleague(Var[Person]("a"), Var[Person]("b")))))),
        ("chained", "chained concrete-subject: InNetwork(alice, Var)",
         lambda: len(list(query(InNetwork(alice, Var[Person]("x")))))),
        ("recursive", "recursive: Ancestor(root, Var)",
         lambda: len(list(query(Ancestor(chain[0], Var[Person]("d")))))),
    ]
    for key, label, fn in cases:
        if key in queries:
            timed(label, fn)

    if "conjunction" in queries:
        # Broad x selective join written broad-first: colleagues of alice via a
        # shared company. PersonWorksFor(Var, Var) is the whole relation;
        # PersonWorksFor(alice, Var) is selective. Left-to-right reloads the
        # selective side once per broad row; the reorder solves selective first.
        timed_reorder_compare(
            "conjunction: colleagues-of-alice (broad-first)",
            lambda: len(list(query(
                PersonWorksFor(Var[Person]("p"), Var[Company]("c")),
                PersonWorksFor(alice, Var[Company]("c")),
            ))),
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    # NOTE: concrete-subject and chained-concrete queries are now O(neighbourhood)
    # (flat in N). The all-var enumeration is still O(result) via the Python
    # fixpoint, so it dominates at large N — exclude it with --queries when
    # pushing sizes up (e.g. --sizes 100000 --queries concrete,chained).
    parser.add_argument("--sizes", default="1000,10000,100000",
                        help="comma-separated people counts (default 1000,10000,100000)")
    parser.add_argument("--fan-out", type=int, default=10,
                        help="people per company; join blow-up scales with fan_out^2 (default 10)")
    parser.add_argument("--ancestor-depth", type=int, default=12,
                        help="length of the ParentOf chain for the recursive case (default 12)")
    parser.add_argument("--queries", default="stored,concrete,allvar,chained,recursive,conjunction",
                        help="comma-separated subset: stored,concrete,allvar,chained,recursive,conjunction")
    args = parser.parse_args()
    sizes = [int(s) for s in args.sizes.split(",") if s.strip()]
    queries = {q.strip() for q in args.queries.split(",") if q.strip()}

    runner = DiscoverRunner(verbosity=0)
    old_config = runner.setup_databases()
    setup_test_environment()
    print("django-datalog inferred-query performance benchmark", flush=True)
    try:
        for n in sizes:
            run_scale(n, args.fan_out, args.ancestor_depth, queries)
    finally:
        teardown_test_environment()
        runner.teardown_databases(old_config)


if __name__ == "__main__":
    main()
