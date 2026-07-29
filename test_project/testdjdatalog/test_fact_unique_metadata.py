"""``unique=`` controls the storage uniqueness constraint of a stored fact.

- ``Unique.TOGETHER`` (default): the (subject, object) pair is unique — a plain edge.
- ``Unique.SUBJECT`` / ``Unique.OBJECT``: that single position is unique — e.g. each
  object has at most one subject (a single owner per owned thing).
"""

from django.db.models import UniqueConstraint
from django.test import SimpleTestCase

from django_datalog.models import Fact, Term, Unique

from .models import Company, Person


def _unique_constraint_fields(meta) -> list[tuple[str, ...]]:
    return [tuple(c.fields) for c in meta.constraints if isinstance(c, UniqueConstraint)]


class FactUniqueMetadataTests(SimpleTestCase):
    def test_default_is_unique_together(self):
        class DefaultEdge(Fact):
            subject: Term[Company]
            object: Term[Person]

        meta = DefaultEdge._django_model._meta
        self.assertEqual(meta.unique_together, (("subject", "object"),))
        self.assertEqual(_unique_constraint_fields(meta), [])

    def test_unique_object(self):
        class OwnedThing(Fact, unique=Unique.OBJECT):
            subject: Term[Company]
            object: Term[Person]

        meta = OwnedThing._django_model._meta
        # A Meta UniqueConstraint on `object` (not a unique=True FK) so each
        # object appears once without tripping Django's W342 warning.
        self.assertEqual(_unique_constraint_fields(meta), [("object",)])
        self.assertFalse(meta.get_field("object").unique)
        self.assertFalse(meta.get_field("subject").unique)
        self.assertEqual(meta.unique_together, ())

    def test_unique_subject(self):
        class SubjectOnce(Fact, unique=Unique.SUBJECT):
            subject: Term[Company]
            object: Term[Person]

        meta = SubjectOnce._django_model._meta
        self.assertEqual(_unique_constraint_fields(meta), [("subject",)])
        self.assertFalse(meta.get_field("subject").unique)
        self.assertFalse(meta.get_field("object").unique)
        self.assertEqual(meta.unique_together, ())
