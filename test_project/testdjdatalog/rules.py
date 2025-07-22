"""
Datalog rules for the test Django project.
These rules define inference logic for deriving new facts from existing ones.
"""

from django_datalog.models import Var
from django_datalog.rules import rule

from .models import (
    ColleaguesOf,
    GrandparentOf,
    MemberOf,
    ParentOf,
    PersonColleaguesOf,
    PersonWorksFor,
    ProjectColleagues,
    SiblingOf,
    TeamMates,
    WorksFor,
    WorksOn,
)

# Family relationship rules
rule(
    GrandparentOf(Var("grandparent"), Var("grandchild")),
    # A person is a grandparent of another if they are the parent of that person's parent
    (
        ParentOf(Var("grandparent"), Var("parent")),
        ParentOf(Var("parent"), Var("grandchild")),
    ),
)

# Note: This sibling rule currently allows self-siblings (person being sibling of themselves)
# This is a limitation of the current rule system which doesn't support inequality constraints
rule(
    SiblingOf(Var("person1"), Var("person2")),
    # Two people are siblings if they have the same parent
    # TODO: Add constraint that person1 != person2 to exclude self-siblings
    (
        ParentOf(Var("parent"), Var("person1")),
        ParentOf(Var("parent"), Var("person2")),
    ),
)

# Work relationship rules (Person-based for internal tests)
rule(
    PersonColleaguesOf(Var("person1"), Var("person2")),
    # Two people are colleagues if they work for the same company
    (
        PersonWorksFor(Var("person1"), Var("company")),
        PersonWorksFor(Var("person2"), Var("company")),
    ),
)

# Work relationship rules (Employee-based for real application)
rule(
    ColleaguesOf(Var("emp1"), Var("emp2")),
    # Two employees are colleagues if they work for the same company
    (
        WorksFor(Var("emp1"), Var("company")),
        WorksFor(Var("emp2"), Var("company")),
    ),
)

rule(
    TeamMates(Var("emp1"), Var("emp2")),
    # Two employees are teammates if they work in the same department
    (
        MemberOf(Var("emp1"), Var("department")),
        MemberOf(Var("emp2"), Var("department")),
    ),
)

rule(
    ProjectColleagues(Var("emp1"), Var("emp2")),
    # Two employees are project colleagues if they work on the same project
    (
        WorksOn(Var("emp1"), Var("project")),
        WorksOn(Var("emp2"), Var("project")),
    ),
)
