# django-datalog

A high-performance logic programming and inference engine for Django applications with advanced query optimization.

## ✨ Key Features

- **🧠 Logic Programming**: Define facts and rules using intuitive Python syntax
- **🚀 Advanced Query Optimization**: AST-based analysis with up to 75% query reduction
- **🔗 Cross-Variable Constraints**: Complex relational queries with automatic optimization
- **🛡️ Security First**: 100% Django ORM - eliminates SQL injection vulnerabilities
- **⚡ Zero Configuration**: Transparent optimization - no code changes required
- **🔧 Developer Tools**: CLI tools for query analysis and optimization insights

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

> **📈 Performance Note**: All existing code automatically benefits from the new advanced query optimization system. No changes required - just upgrade and get better performance!

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

# Complex cross-variable constraints (automatically optimized)
results = list(query(
    WorksFor(Var("emp"), Var("company")),
    WorksOn(Var("emp"), Var("project", where=Q(company=Var("company"))))
))
# ↑ Automatically converts to optimized Django ORM with EXISTS subqueries

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

# Cross-variable constraints (reference other variables)
query(
    WorksFor(Var("emp"), Var("company")),
    WorksOn(Var("emp"), Var("project", where=Q(company=Var("company"))))
)
# Finds employees working on projects from their own company

# Complex cross-variable relationships
query(
    MemberOf(Var("emp"), Var("dept")),
    WorksFor(Var("emp"), Var("company", where=Q(is_active=True, department__in=[Var("dept")])))
)
# Finds employees in departments that belong to active companies
```

## Performance Features

### Advanced Query Analysis System
The engine features a sophisticated AST-based optimization system that works transparently:

- **Query AST Parser**: Automatically parses queries into abstract syntax trees
- **Dependency Analysis**: Maps variable relationships and constraint dependencies
- **Execution Planning**: Creates optimal execution plans based on query structure
- **Recursive ORM Construction**: Builds complex Django ORM queries automatically
- **Cross-Variable Constraint Resolution**: Transforms complex constraints into optimized EXISTS subqueries

### Automatic Optimization
The engine automatically:
- **Converts complex patterns** to optimized Django ORM queries (up to 75% query reduction)
- **Propagates constraints** across same-named variables
- **Orders execution** by selectivity (most selective first)
- **Learns from execution times** for better planning
- **Pushes constraints** to the database
- **Eliminates SQL injection** by using 100% Django ORM

```python
# You write natural cross-variable queries:
query(
    WorksFor(Var("emp"), Var("company")),
    WorksOn(Var("emp"), Var("project", where=Q(company=Var("company"))))
)

# Engine automatically generates optimized SQL like:
# SELECT ... FROM worksforstorage 
# INNER JOIN employee ON (...) 
# INNER JOIN company ON (...)
# WHERE EXISTS(
#     SELECT 1 FROM worksonstorage U0 
#     INNER JOIN project U2 ON (...) 
#     WHERE (...) AND U2.company_id = worksforstorage.object_id
# )
# Result: 16 queries → 4 queries (75% improvement)
```

### Performance Analysis Tools
```bash
# Analyze query patterns and get optimization recommendations
python manage.py convert_to_orm --analyze

# Interactive query analysis
python manage.py convert_to_orm --interactive

# Process file with django-datalog queries
python manage.py convert_to_orm --file my_queries.py
```

## Example: Complete Employee System

```python
# models.py
class Employee(models.Model):
    name = models.CharField(max_length=100)
    is_manager = models.BooleanField(default=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE)

class Project(models.Model):
    name = models.CharField(max_length=100)
    company = models.ForeignKey(Company, on_delete=models.CASCADE)

class WorksFor(Fact):
    subject: Employee | Var
    object: Company | Var

class WorksOn(Fact):
    subject: Employee | Var  
    object: Project | Var

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
    WorksOn(subject=alice, object=tech_project),
    WorksOn(subject=bob, object=other_project),
)

# Simple queries (automatically optimized)
colleagues = query(ColleaguesOf(alice, Var("colleague")))

# Complex cross-variable constraints (75% query reduction!)
same_company_projects = query(
    WorksFor(Var("emp"), Var("company")),
    WorksOn(Var("emp"), Var("project", where=Q(company=Var("company"))))
)
# ↑ Finds employees working on projects from their own company
# Automatically converts to optimized Django ORM with EXISTS subqueries
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

## Documentation

- **[docs/](docs/)** - Technical documentation and reference materials
- **[docs/django_orm_equivalents.md](docs/django_orm_equivalents.md)** - Django ORM equivalent queries and conversion patterns

## Requirements

- Python 3.10+
- Django 5.0+

## License

MIT License
