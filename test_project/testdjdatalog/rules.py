"""
Datalog rules for the test Django project.
These rules define inference logic for deriving new facts from existing ones.
"""

from django_datalog.models import Var
from django_datalog.rules import rule

from .models import (
    ColleaguesOf,
    Company,
    Department,
    Employee,
    GrandparentOf,
    MemberOf,
    ParentOf,
    Person,
    PersonColleaguesOf,
    PersonWorksFor,
    Project,
    ProjectColleagues,
    SiblingOf,
    TeamMates,
    WorksFor,
    WorksOn,
)

# Family relationship rules
rule(
    GrandparentOf(Var[Person]("grandparent"), Var[Person]("grandchild")),
    # A person is a grandparent of another if they are the parent of that person's parent
    (
        ParentOf(Var[Person]("grandparent"), Var[Person]("parent")),
        ParentOf(Var[Person]("parent"), Var[Person]("grandchild")),
    ),
)

# Note: This sibling rule currently allows self-siblings (person being sibling of themselves)
# This is a limitation of the current rule system which doesn't support inequality constraints
rule(
    SiblingOf(Var[Person]("person1"), Var[Person]("person2")),
    # Two people are siblings if they have the same parent
    # TODO: Add constraint that person1 != person2 to exclude self-siblings
    (
        ParentOf(Var[Person]("parent"), Var[Person]("person1")),
        ParentOf(Var[Person]("parent"), Var[Person]("person2")),
    ),
)

# Work relationship rules (Person-based for internal tests)
rule(
    PersonColleaguesOf(Var[Person]("person1"), Var[Person]("person2")),
    # Two people are colleagues if they work for the same company
    (
        PersonWorksFor(Var[Person]("person1"), Var[Company]("company")),
        PersonWorksFor(Var[Person]("person2"), Var[Company]("company")),
    ),
)

# Work relationship rules (Employee-based for real application)
rule(
    ColleaguesOf(Var[Employee]("emp1"), Var[Employee]("emp2")),
    # Two employees are colleagues if they work for the same company
    (
        WorksFor(Var[Employee]("emp1"), Var[Company]("company")),
        WorksFor(Var[Employee]("emp2"), Var[Company]("company")),
    ),
)

rule(
    TeamMates(Var[Employee]("emp1"), Var[Employee]("emp2")),
    # Two employees are teammates if they work in the same department
    (
        MemberOf(Var[Employee]("emp1"), Var[Department]("department")),
        MemberOf(Var[Employee]("emp2"), Var[Department]("department")),
    ),
)

rule(
    ProjectColleagues(Var[Employee]("emp1"), Var[Employee]("emp2")),
    # Two employees are project colleagues if they work on the same project
    (
        WorksOn(Var[Employee]("emp1"), Var[Project]("project")),
        WorksOn(Var[Employee]("emp2"), Var[Project]("project")),
    ),
)
