"""Tests for the async query/write interface (aquery, astore_facts, aretract_facts)."""

from asgiref.sync import async_to_sync
from django.test import TestCase

from django_datalog.models import (
    Var,
    aquery,
    aretract_facts,
    astore_facts,
    query,
    store_facts,
)

from .models import ParentOf, Person


class AsyncInterfaceTests(TestCase):
    """The async API mirrors the sync API and shares the DB connection context."""

    def setUp(self):
        self.alice = Person.objects.create(name="Alice")
        self.bob = Person.objects.create(name="Bob")
        self.charlie = Person.objects.create(name="Charlie")

    def test_astore_and_aquery(self):
        """astore_facts writes and aquery reads them back."""

        async def scenario():
            await astore_facts(
                ParentOf(subject=self.alice, object=self.bob),
                ParentOf(subject=self.alice, object=self.charlie),
            )
            return await aquery(ParentOf(self.alice, Var[Person]("child")))

        results = async_to_sync(scenario)()
        self.assertEqual({r["child"].name for r in results}, {"Bob", "Charlie"})

    def test_aretract_facts(self):
        """aretract_facts removes previously stored facts."""

        async def scenario():
            await astore_facts(ParentOf(subject=self.alice, object=self.bob))
            await aretract_facts(ParentOf(subject=self.alice, object=self.bob))
            return await aquery(ParentOf(self.alice, Var[Person]("child")))

        results = async_to_sync(scenario)()
        self.assertEqual(len(results), 0)

    def test_aquery_matches_sync_query(self):
        """aquery returns the same results as the sync query()."""
        store_facts(
            ParentOf(subject=self.alice, object=self.bob),
            ParentOf(subject=self.bob, object=self.charlie),
        )
        sync_results = {r["child"].name for r in query(ParentOf(self.alice, Var[Person]("child")))}
        async_results = {
            r["child"].name for r in async_to_sync(aquery)(ParentOf(self.alice, Var[Person]("child")))
        }
        self.assertEqual(sync_results, {"Bob"})
        self.assertEqual(async_results, sync_results)

    def test_aquery_returns_list(self):
        """aquery materializes results into a list (not a lazy iterator)."""

        async def scenario():
            await astore_facts(ParentOf(subject=self.alice, object=self.bob))
            return await aquery(ParentOf(self.alice, Var[Person]("child")))

        results = async_to_sync(scenario)()
        self.assertIsInstance(results, list)
