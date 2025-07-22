# django-datalog

A logic programming and inference engine for Django applications.

## Installation

```bash
pip install django-datalog
```

```python
# settings.py
INSTALLED_APPS = ['django_datalog']
```

```bash
python manage.py migrate
```

## Core Concepts

### Facts
Define facts as Python classes with Django model integration:

```python
from django_datalog.models import Fact, Var

class WorksFor(Fact):
    subject: Employee | Var  # Employee
    object: Company | Var    # Company

class ColleaguesOf(Fact, inferred=True):  # Inferred facts can't be stored directly
    subject: Employee | Var
    object: Employee | Var
```

### Rules
Define inference logic with tuples (AND) and lists (OR):

```python
from django_datalog.rules import rule

# Simple rule: Colleagues work at same company
rule(
    ColleaguesOf(Var("emp1"), Var("emp2")),
    WorksFor(Var("emp1"), Var("company")) & WorksFor(Var("emp2"), Var("company"))
)

# Disjunctive rule: HasAccess via admin OR manager
rule(
    HasAccess(Var("user"), Var("resource")),
    IsAdmin(Var("user")) | IsManager(Var("user"), Var("resource"))
)

# Mixed rule: Complex access control
rule(
    CanEdit(Var("user"), Var("doc")),
    IsOwner(Var("user"), Var("doc")) | 
    (IsManager(Var("user"), Var("folder")) & Contains(Var("folder"), Var("doc")))
)
```

### Fact Operators
Use `|` (OR) and `&` (AND) operators:

```python
# Modern operator syntax (recommended):
rule(head, fact1 | fact2)           # OR: fact1 OR fact2
rule(head, fact1 & fact2)           # AND: fact1 AND fact2

# Combining operators:
rule(head, (fact1 & fact2) | fact3)  # (fact1 AND fact2) OR fact3
rule(head, fact1 & fact2 & fact3)    # fact1 AND fact2 AND fact3
rule(head, fact1 | fact2 | fact3)    # fact1 OR fact2 OR fact3

# Legacy syntax (still supported):
rule(head, [fact1, fact2])           # OR (list syntax)
rule(head, (fact1, fact2))          # AND (tuple syntax)
```

### Storing Facts
```python
from django_datalog.models import store_facts

store_facts(
    WorksFor(subject=alice, object=tech_corp),
    WorksFor(subject=bob, object=tech_corp),
)
```

### Querying
```python
from django_datalog.models import query

# Find Alice's colleagues
colleagues = list(query(ColleaguesOf(alice, Var("colleague"))))

# With Django Q constraints
managers = list(query(WorksFor(Var("emp", where=Q(is_manager=True)), tech_corp)))

# Complex queries
results = list(query(
    ColleaguesOf(Var("emp1"), Var("emp2")),
    WorksFor(Var("emp1"), Var("company", where=Q(is_active=True)))
))
```

### Rule Context
Isolate rules for testing or temporary logic:

```python
from django_datalog.models import rule_context

# As context manager
with rule_context():
    rule(TestFact(Var("x")), LocalFact(Var("x")))
    results = query(TestFact(Var("x")))  # Rules active here

# As decorator
@rule_context
def test_something(self):
    rule(TestFact(Var("x")), LocalFact(Var("x")))
    assert len(query(TestFact(Var("x")))) > 0
```

### Variables & Constraints
```python
# Basic variable
emp = Var("employee")

# With Django Q constraints
senior_emp = Var("employee", where=Q(years_experience__gte=5))

# Multiple constraints
constrained = Var("emp", where=Q(is_active=True) & Q(department="Engineering"))
```

## Performance Features

### Automatic Optimization
The engine automatically:
- Propagates constraints across same-named variables
- Orders execution by selectivity (most selective first)
- Learns from execution times for better planning
- Pushes constraints to the database

```python
# You write natural queries:
query(
    ColleaguesOf(Var("emp1"), Var("emp2", where=Q(department="Engineering"))),
    WorksFor(Var("emp1"), Var("company", where=Q(is_active=True)))
)

# Engine automatically optimizes constraint propagation and execution order
```

## Example: Complete Employee System

```python
# models.py
class Employee(models.Model):
    name = models.CharField(max_length=100)
    is_manager = models.BooleanField(default=False)

class WorksFor(Fact):
    subject: Employee | Var
    object: Company | Var

class ColleaguesOf(Fact, inferred=True):
    subject: Employee | Var
    object: Employee | Var

# rules.py
rule(
    ColleaguesOf(Var("emp1"), Var("emp2")),
    WorksFor(Var("emp1"), Var("company")) & WorksFor(Var("emp2"), Var("company"))
)

# usage.py
store_facts(
    WorksFor(subject=alice, object=tech_corp),
    WorksFor(subject=bob, object=tech_corp),
)

# Query automatically infers colleagues
colleagues = query(ColleaguesOf(alice, Var("colleague")))
```

## Testing

```python
class MyTest(TestCase):
    @rule_context  # Isolate rules per test
    def test_access_control(self):
        rule(CanAccess(Var("user")), IsAdmin(Var("user")))
        
        results = query(CanAccess(admin_user))
        self.assertEqual(len(results), 1)
```

## Requirements

- Python 3.10+
- Django 5.0+

## License

MIT License
