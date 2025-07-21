# django-datalog

Django Datalog - A logic programming and inference engine for Django applications.

## Features

- **Fact-based data modeling**: Define facts as Python classes that integrate seamlessly with Django models
- **Logic programming**: Write inference rules using a familiar Python syntax  
- **Query system**: Query facts and derived conclusions with variable binding
- **Q object constraints**: Filter query results using Django Q objects for powerful filtering
- **Performance optimized**: Intelligent query reordering and batch hydration for optimal performance
- **Django integration**: Seamless integration with existing Django models and ORM

## Quick Start

### Installation

```bash
pip install django-datalog
```

Add `django_datalog` to your `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    # ... your other apps
    'django_datalog',
]
```

Run migrations to create the datalog fact tables:

```bash
python manage.py migrate
```

### Basic Example: Company Employee Management

Let's start with a realistic business scenario - managing employees in a company:

```python
# models.py
from django.db import models
from django.contrib.auth.models import User
from django_datalog.models import Fact, Var

class Company(models.Model):
    name = models.CharField(max_length=100)
    
class Department(models.Model):
    name = models.CharField(max_length=100)
    company = models.ForeignKey(Company, on_delete=models.CASCADE)

class Employee(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    department = models.ForeignKey(Department, on_delete=models.CASCADE)
    is_manager = models.BooleanField(default=False)

# Define Facts - Note: No @dataclass decorator needed!
class WorksFor(Fact):
    """Employee works for a company."""
    subject: Employee | Var  # Employee
    object: Company | Var    # Company

class MemberOf(Fact):
    """Employee is member of a department."""
    subject: Employee | Var    # Employee
    object: Department | Var   # Department

class ColleaguesOf(Fact):
    """Two employees are colleagues (inferred from working at same company)."""
    subject: Employee | Var  # Employee 1
    object: Employee | Var   # Employee 2

class TeamMates(Fact):
    """Two employees are teammates (inferred from same department)."""
    subject: Employee | Var  # Employee 1
    object: Employee | Var   # Employee 2
```

```python
# rules.py - Define inference logic
from django_datalog.rules import rule
from django_datalog.models import Var
from .models import WorksFor, MemberOf, ColleaguesOf, TeamMates

# Rule: Employees are colleagues if they work for the same company
rule(
    ColleaguesOf(Var("emp1"), Var("emp2")),
    WorksFor(Var("emp1"), Var("company")),
    WorksFor(Var("emp2"), Var("company")),
)

# Rule: Employees are teammates if they work in the same department  
rule(
    TeamMates(Var("emp1"), Var("emp2")),
    MemberOf(Var("emp1"), Var("department")),
    MemberOf(Var("emp2"), Var("department")),
)
```

```python
# Usage in views.py or management commands
from django_datalog.models import query, store_facts
from django.db.models import Q

# Store some facts
tech_corp = Company.objects.create(name="Tech Corp")
engineering = Department.objects.create(name="Engineering", company=tech_corp)

alice_user = User.objects.create(username="alice")
bob_user = User.objects.create(username="bob")

alice = Employee.objects.create(user=alice_user, company=tech_corp, department=engineering, is_manager=True)
bob = Employee.objects.create(user=bob_user, company=tech_corp, department=engineering)

# Store facts about work relationships
store_facts(
    WorksFor(subject=alice, object=tech_corp),
    WorksFor(subject=bob, object=tech_corp),
    MemberOf(subject=alice, object=engineering),
    MemberOf(subject=bob, object=engineering),
)

# Query: Find all of Alice's colleagues (inferred automatically!)
colleagues = list(query(ColleaguesOf(alice, Var("colleague"))))
for result in colleagues:
    colleague = result["colleague"]
    print(f"Alice works with {colleague.user.username}")

# Query: Find all teammates in engineering
teammates = list(query(TeamMates(Var("emp1"), Var("emp2"))))
for result in teammates:
    emp1, emp2 = result["emp1"], result["emp2"]
    print(f"{emp1.user.username} and {emp2.user.username} are teammates")

# Query with constraints: Find managers who work for Tech Corp
managers = list(query(WorksFor(Var("employee", where=Q(is_manager=True)), tech_corp)))
for result in managers:
    manager = result["employee"]
    print(f"{manager.user.username} is a manager at {tech_corp.name}")
```

## Advanced Features

### Intelligent Query Optimization (🚀 NEW!)

Django-datalog includes an adaptive query optimizer that automatically:

1. **Propagates constraints** across variables with the same name
2. **Orders query execution** by selectivity (most selective first)  
3. **Learns from execution times** to improve future query planning
4. **Adapts performance** based on historical data
5. **Pushes constraints to the database** for maximum performance

```python
# The optimizer works automatically - no changes needed to your code!
results = query(
    ColleaguesOf(Var("emp1"), Var("emp2", where=Q(department="Engineering"))),
    WorksFor(Var("emp1"), Var("company", where=Q(is_active=True))),
    WorksFor(Var("emp2"), Var("company"))
)

# Behind the scenes, the optimizer:
# 1. Propagates Q(department="Engineering") to ALL emp2 variables
# 2. Propagates Q(is_active=True) to ALL company variables  
# 3. Reorders execution to run most selective constraints first
# 4. Records execution times for each pattern type
# 5. Uses timing data to optimize future query planning
# 6. Result: Massive performance improvements that get better over time!
```

**Constraint Propagation Example:**
```python
# You write this natural query:
active_managers = query(
    ManagerOf(Var("mgr", where=Q(is_manager=True)), Var("emp")),
    WorksFor(Var("mgr"), Var("company", where=Q(is_active=True))),
    WorksFor(Var("emp"), Var("company"))
)

# Optimizer automatically transforms it to:
# ManagerOf(Var("mgr", where=Q(is_manager=True)), Var("emp")),
# WorksFor(Var("mgr", where=Q(is_manager=True)), Var("company", where=Q(is_active=True))),  
# WorksFor(Var("emp"), Var("company", where=Q(is_active=True)))
# 
# Result: All constraints are applied everywhere, and execution is optimized!
```

**Rule Constraint Propagation:**
```python  
# Constraints in rule heads automatically propagate to rule bodies:
rule(
    SeniorManager(Var("mgr", where=Q(seniority__gte=5)), Var("dept")),
    WorksFor(Var("mgr"), Var("company")),  # Gets Q(seniority__gte=5) automatically!
    MemberOf(Var("mgr"), Var("dept"))      # Gets Q(seniority__gte=5) automatically!
)
```

**Adaptive Query Optimization:**
```python
from django_datalog.models import (
    get_optimizer_timing_stats, 
    time_fact_execution
)

# The query planner automatically learns from execution times
results1 = query(WorksFor(Var("emp"), Var("company")))  # Times this query
results2 = query(WorksFor(Var("emp", where=Q(is_manager=True)), Var("company")))  # Times this too

# Check what the optimizer has learned
stats = get_optimizer_timing_stats()
print(stats)
# {
#   'WorksFor': {'count': 1, 'avg_time': 0.005, 'min_time': 0.005, 'max_time': 0.005},
#   'WorksFor(subject:Q(is_manager=True))': {'count': 1, 'avg_time': 0.001, 'min_time': 0.001, 'max_time': 0.001}
# }

# Future queries automatically use this knowledge to execute faster patterns first!
# The constrained pattern will be prioritized because it's historically faster

# Manual timing (if needed)
with time_fact_execution(my_pattern):
    # Your custom query logic here
    custom_results = do_something()
```

### Context-Local Rules

Use `rule_context()` to define temporary rules that are only active within a specific scope:

```python
from django_datalog.models import rule_context

# Scenario 1: Rules defined inside context
with rule_context():
    # Define temporary rule for active teammates
    rule(
        TeamMates(Var("emp1"), Var("emp2")),
        MemberOf(Var("emp1"), Var("dept")),
        MemberOf(Var("emp2"), Var("dept")),
        WorksFor(Var("emp1"), Var("company", where=Q(is_active=True))),
        WorksFor(Var("emp2"), Var("company", where=Q(is_active=True))),
    )
    
    # Rules are active here - only teammates at active companies
    active_teammates = list(query(TeamMates(Var("emp1"), Var("emp2"))))
    
# Rules are no longer active here - teammates query returns empty

# Scenario 2: Rules passed as arguments
with rule_context(
    # Pass rule as tuple: (head, body1, body2, ...)
    (
        ColleaguesOf(Var("emp1"), Var("emp2")),
        WorksFor(Var("emp1"), Var("company")),
        WorksFor(Var("emp2"), Var("company")),
    )
):
    # Rule is active within this context
    colleagues = list(query(ColleaguesOf(Var("emp1"), Var("emp2"))))

# Nested contexts work too
with rule_context():
    rule(ColleaguesOf(Var("emp1"), Var("emp2")), WorksFor(Var("emp1"), Var("company")), WorksFor(Var("emp2"), Var("company")))
    
    with rule_context():
        rule(TeamMates(Var("emp1"), Var("emp2")), MemberOf(Var("emp1"), Var("dept")), MemberOf(Var("emp2"), Var("dept")))
        # Both colleague and teammate rules active here
        
    # Only colleague rules active here
```

**Benefits of Context-Local Rules:**
- **Clean testing**: Define rules only for specific test scenarios
- **Temporary logic**: Apply business rules conditionally without global pollution
- **Experimentation**: Try different rule sets without affecting production rules
- **Isolation**: Prevent rule conflicts between different parts of your application

### Q Object Constraints

Use Django Q objects to add powerful filtering to your queries:

```python
from django.db.models import Q

# Find senior employees (with complex constraints)
senior_employees = query(
    WorksFor(
        Var("employee", where=Q(user__date_joined__year__lt=2020) & Q(is_manager=True)), 
        Var("company")
    )
)

# Find employees in specific departments
engineering_employees = query(
    MemberOf(Var("employee"), Var("dept", where=Q(name__icontains="engineering")))
)
```

### Hydration Control

Control whether to fetch full model instances or just PKs for better performance:

```python
# Get full objects (default) - includes all related data
results = list(query(WorksFor(Var("employee"), tech_corp), hydrate=True))
employee = results[0]["employee"]
print(employee.user.username)  # Full Employee object with related User

# Get PKs only (better performance for large datasets)  
results = list(query(WorksFor(Var("employee"), tech_corp), hydrate=False))
employee_id = results[0]["employee"]  # Just the employee ID (integer)
```

### Family Relationships Example

Django-datalog also works great for modeling family relationships:

```python
class Person(models.Model):
    name = models.CharField(max_length=100)
    age = models.IntegerField()

class ParentOf(Fact):
    """Person is parent of another person."""
    subject: Person | Var  # Parent
    object: Person | Var   # Child

class GrandparentOf(Fact):
    """Person is grandparent of another person (inferred)."""
    subject: Person | Var  # Grandparent  
    object: Person | Var   # Grandchild

class SiblingOf(Fact):
    """Person is sibling of another person (inferred)."""
    subject: Person | Var  # Sibling 1
    object: Person | Var   # Sibling 2

# Define family rules
rule(
    GrandparentOf(Var("grandparent"), Var("grandchild")),
    ParentOf(Var("grandparent"), Var("parent")),
    ParentOf(Var("parent"), Var("grandchild")),
)

rule(
    SiblingOf(Var("person1"), Var("person2")),
    ParentOf(Var("parent"), Var("person1")),
    ParentOf(Var("parent"), Var("person2")),
)

# Usage
john = Person.objects.create(name="John", age=65)
alice = Person.objects.create(name="Alice", age=40) 
bob = Person.objects.create(name="Bob", age=15)

store_facts(
    ParentOf(subject=john, object=alice),
    ParentOf(subject=alice, object=bob)
)

# Query: Find Bob's grandparents (automatically inferred!)
grandparents = list(query(GrandparentOf(Var("grandparent"), bob)))
print(f"Bob's grandparent: {grandparents[0]['grandparent'].name}")  # John
```

## Key Benefits

- **No complex SQL**: Express complex relationship logic in simple Python rules
- **Automatic inference**: New facts are derived automatically from your rules
- **Performance optimized**: Query reordering and batch loading for optimal performance  
- **Django native**: Works seamlessly with your existing Django models and admin
- **Type safe**: Full type hints and IDE support with modern Python syntax

## Fact Retraction

Remove facts when relationships change:

```python
from django_datalog.models import retract_facts

# Remove a work relationship
retract_facts(WorksFor(subject=alice, object=tech_corp))

# The system will automatically update inferred facts like ColleaguesOf
```

## Requirements

- Python 3.10+
- Django 5.0+

## Documentation

For detailed examples, API reference, and advanced usage, see the [repository documentation](https://github.com/edelvalle/django-datalog) and [CHANGELOG.md](CHANGELOG.md).

## Contributing

We welcome contributions! Please see our repository on [GitHub](https://github.com/edelvalle/django-datalog) for details.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history and changes.
