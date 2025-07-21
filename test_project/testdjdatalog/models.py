"""
Django models for testing django_datalog functionality.
These models will be used to create facts and test datalog inference.
"""

from decimal import Decimal

from django.contrib.auth.models import User
from django.db import models

from django_datalog.models import Fact, Var


# Models originally from django_datalog.models (used by internal tests)
class Person(models.Model):
    """Example Person model for family relationship tests."""

    name = models.CharField(max_length=100)
    age = models.PositiveIntegerField(null=True, blank=True)
    city = models.CharField(max_length=100, blank=True)
    married = models.BooleanField(default=False)
    retired = models.BooleanField(default=False)

    def __str__(self):
        return self.name


class Company(models.Model):
    """Company model for business relationship tests."""

    name = models.CharField(max_length=100)
    founded_year = models.IntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    active = models.BooleanField(default=True)  # Keep both for compatibility
    city = models.CharField(max_length=100, blank=True)

    class Meta:
        verbose_name_plural = "companies"

    def __str__(self):
        return self.name


class Department(models.Model):
    """A department within a company."""

    name = models.CharField(max_length=100)
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    budget = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))

    def __str__(self):
        return f"{self.name} - {self.company.name}"


class Employee(models.Model):
    """Employee model that can work with both Person and User."""

    # Optional relationship to Person (for internal django_datalog tests)
    person = models.OneToOneField(Person, on_delete=models.CASCADE, null=True, blank=True)

    # Optional relationship to User (for Django integration tests)
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)

    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    department = models.ForeignKey(Department, on_delete=models.CASCADE, null=True, blank=True)
    position = models.CharField(max_length=100, blank=True)
    salary = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    hire_date = models.DateField(null=True, blank=True)
    is_manager = models.BooleanField(default=False)

    def __str__(self):
        if self.person:
            return f"{self.person.name} at {self.company.name}"
        elif self.user:
            return f"{self.user.get_full_name() or self.user.username} at {self.company.name}"
        else:
            return f"Employee at {self.company.name}"


class Project(models.Model):
    """A project that employees can work on."""

    name = models.CharField(max_length=100)
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    is_completed = models.BooleanField(default=False)
    employees = models.ManyToManyField(Employee, through="ProjectAssignment")

    def __str__(self):
        return f"{self.name} ({self.company.name})"


class ProjectAssignment(models.Model):
    """Assignment of an employee to a project with a role."""

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    role = models.CharField(max_length=100, default="Contributor")
    assigned_date = models.DateField(null=True, blank=True)

    def __str__(self):
        name = "Unknown"
        if self.employee.person:
            name = self.employee.person.name
        elif self.employee.user:
            name = self.employee.user.username
        return f"{name} - {self.project.name} ({self.role})"


# Facts using Person model (for internal django_datalog tests)
class ParentOf(Fact):
    """Person is parent of another person."""

    subject: Person | Var  # Parent
    object: Person | Var  # Child


class MarriedTo(Fact):
    """Person is married to another person."""

    subject: Person | Var  # Spouse 1
    object: Person | Var  # Spouse 2


class GrandparentOf(Fact):
    """Person is grandparent of another person (inferred)."""

    subject: Person | Var  # Grandparent
    object: Person | Var  # Grandchild


class SiblingOf(Fact):
    """Person is sibling of another person."""

    subject: Person | Var  # Sibling 1
    object: Person | Var  # Sibling 2


class PersonWorksFor(Fact):
    """Person works for a company (for internal tests)."""

    subject: Person | Var  # Person
    object: Company | Var  # Company


class WorksFor(Fact):
    """Employee works for a company."""

    subject: Employee | Var  # Employee
    object: Company | Var  # Company


class MemberOf(Fact):
    """Employee is member of a department."""

    subject: Employee | Var  # Employee
    object: Department | Var  # Department


class ManagerOf(Fact):
    """Employee is manager of another employee."""

    subject: Employee | Var  # Manager
    object: Employee | Var  # Employee being managed


class WorksOn(Fact):
    """Employee works on a project."""

    subject: Employee | Var  # Employee
    object: Project | Var  # Project


class PersonColleaguesOf(Fact):
    """Two people are colleagues (work at same company) - for internal tests."""

    subject: Person | Var  # Person 1
    object: Person | Var  # Person 2


class ColleaguesOf(Fact):
    """Two employees are colleagues (work at same company)."""

    subject: Employee | Var  # Employee 1
    object: Employee | Var  # Employee 2


class TeamMates(Fact):
    """Two employees are teammates (work in same department)."""

    subject: Employee | Var  # Employee 1
    object: Employee | Var  # Employee 2


class ProjectColleagues(Fact):
    """Two employees are project colleagues (work on same project)."""

    subject: Employee | Var  # Employee 1
    object: Employee | Var  # Employee 2


class CanAccess(Fact):
    """Employee can access a project."""

    subject: Employee | Var  # Employee
    object: Project | Var  # Project


class HasAuthority(Fact):
    """Employee has authority over a department/project."""

    subject: Employee | Var  # Employee
    object: Department | Project | Var  # Department or Project
