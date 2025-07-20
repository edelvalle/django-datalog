"""
Test rules for djdatalog - only loaded when DJDATALOG_TESTING is True.
These provide example inference rules using the test facts.
"""

from django.conf import settings

# Only create rules when in testing mode
if getattr(settings, 'DJDATALOG_TESTING', False):
    from djdatalog.models import Var, rule
    from djdatalog.tests.test_facts import (
        ParentOf, GrandparentOf, SiblingOf, WorksFor, ColleaguesOf
    )
    
    # Rule: Grandparents are inferred from parent relationships
    rule(
        GrandparentOf(Var("grandparent"), Var("grandchild")),
        # := (implied by)
        ParentOf(Var("grandparent"), Var("parent")),
        ParentOf(Var("parent"), Var("grandchild"))
    )
    
    # Rule: People are siblings if they have the same parent
    rule(
        SiblingOf(Var("person1"), Var("person2")),
        # := (implied by)
        ParentOf(Var("parent"), Var("person1")),
        ParentOf(Var("parent"), Var("person2"))
        # Note: In practice, you'd add a condition to exclude person1 == person2
    )
    
    # Rule: People are colleagues if they work for the same company
    rule(
        ColleaguesOf(Var("person1"), Var("person2")),
        # := (implied by)
        WorksFor(Var("person1"), Var("company")),
        WorksFor(Var("person2"), Var("company"))
        # Note: In practice, you'd add a condition to exclude person1 == person2
    )
    
    print("djdatalog: Loaded test rules for family and work relationships")