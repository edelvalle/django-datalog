"""Static typing checks for the parametric ``Var`` API.

This module is never executed. It is a *type-checker* test: it asserts that a
typed ``Var[Model]`` only fits into a matching fact slot. Run it with the
``arg-type`` error code enabled and unused-ignore warnings on::

    make typecheck-vars        # from test_project/
    # i.e. zuban mypy --enable-error-code arg-type --warn-unused-ignores \
    #          testdjdatalog/typing_check.py

Every intentional misuse is marked ``# type: ignore[arg-type]``. With
``--warn-unused-ignores`` the module type-checks cleanly *only if*:
  * every correct usage below produces no error, and
  * every misuse below actually produces the expected ``arg-type`` error
    (otherwise its ignore is flagged as unused).

If someone breaks the typed-``Var`` machinery, this file stops type-checking.
"""

from django.db.models import Q

from django_datalog.models import Var, query
from testdjdatalog.models import Company, Employee, Project, WorksFor, WorksOn


def correct_usage() -> None:
    """Typed variables placed in matching slots — must type-check clean."""
    emp = Var[Employee]("emp")
    company = Var[Company]("company")
    project = Var[Project]("project")

    query(WorksFor(emp, company))
    query(WorksOn(emp, project))

    # concrete model instances are also valid in a slot (Term[X] == X | Var[X])
    query(WorksOn(emp, Var[Project]("p", where=Q(company=company))))

    # bare Var stays valid (untyped escape hatch, inferred from the slot)
    query(WorksFor(Var("anon_emp"), Var("anon_company")))


def rejected_usage() -> None:
    """Typed variables in the wrong slot — each line MUST raise arg-type."""
    emp = Var[Employee]("emp")
    company = Var[Company]("company")
    project = Var[Project]("project")

    query(WorksFor(company, emp))  # type: ignore[arg-type]  # subject/object swapped
    query(WorksOn(emp, company))  # type: ignore[arg-type]  # company is not a Project
    query(WorksFor(project, company))  # type: ignore[arg-type]  # project is not an Employee
