"""``unique=`` controls the storage uniqueness constraint of a stored fact.

- ``Unique.TOGETHER`` (default): the (subject, object) pair is unique — a plain edge.
- ``Unique.SUBJECT`` / ``Unique.OBJECT``: that single position is unique — e.g. each
  object has at most one subject (a single owner per owned thing).
"""

from django.test import SimpleTestCase

from django_datalog.models import Fact, Term, Unique

from .models import Company, Person


class FactUniqueMetadataTests(SimpleTestCase):
    def test_default_is_unique_together(self):
        class DefaultEdge(Fact):
            subject: Term[Company]
            object: Term[Person]

        meta = DefaultEdge._django_model._meta
        self.assertEqual(meta.unique_together, (("subject", "object"),))
        self.assertFalse(meta.get_field("subject").unique)
        self.assertFalse(meta.get_field("object").unique)

    def test_unique_object(self):
        class OwnedThing(Fact, unique=Unique.OBJECT):
            subject: Term[Company]
            object: Term[Person]

        meta = OwnedThing._django_model._meta
        self.assertTrue(meta.get_field("object").unique)  # one subject per object
        self.assertFalse(meta.get_field("subject").unique)
        self.assertEqual(meta.unique_together, ())

    def test_unique_subject(self):
        class SubjectOnce(Fact, unique=Unique.SUBJECT):
            subject: Term[Company]
            object: Term[Person]

        meta = SubjectOnce._django_model._meta
        self.assertTrue(meta.get_field("subject").unique)
        self.assertFalse(meta.get_field("object").unique)
        self.assertEqual(meta.unique_together, ())
