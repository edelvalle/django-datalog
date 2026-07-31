# django-datalog

A high-performance logic programming and inference engine for Django applications with advanced query optimization.

## ✨ Key Features

- **🧠 Logic Programming**: Define facts and rules using intuitive Python syntax
- **🔢 N-ary Relations**: Facts with any number of positions, mixing entities (FKs) and values
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
# settings.py — django-datalog has no models of its own; add it for the
# management commands, and your own app holds the fact storage tables.
INSTALLED_APPS = [..., "django_datalog", "your_app"]
```

You declare the storage tables for your stored facts in your own app (see Quick
start), then migrate that app as usual — there are no library migrations to run.

## Quick start

```python
# your_app/models.py
from django.db import models
from django_datalog.models import Fact, Term, Var, store, store_facts, query, exists, rule

class Employee(models.Model):
    name = models.CharField(max_length=100)

class Company(models.Model):
    name = models.CharField(max_length=100)

# 1. Declare facts — the logical relations (a fact is just types + a name).
class WorksFor(Fact):
    subject: Term[Employee]
    object:  Term[Company]

class ColleaguesOf(Fact):   # inferred: derived by rules, no storage
    subject: Term[Employee]
    object:  Term[Employee]

# 2. For each STORED fact, declare the Django model that holds its rows and bind
#    it with @store. You own this table — its columns, indexes and constraints.
@store(WorksFor)
class WorksForStorage(models.Model):
    subject = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="+")
    object  = models.ForeignKey(Company,  on_delete=models.CASCADE, related_name="+")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["subject", "object"], name="worksfor_edge")]

# 3. Migrate your app normally:  manage.py makemigrations && manage.py migrate
```

```python
# 4. Define inference rules (shared Var names are the join keys).
a, b, c = Var[Employee]("a"), Var[Employee]("b"), Var[Company]("c")
rule(ColleaguesOf(a, b), WorksFor(a, c) & WorksFor(b, c))

# 5. Store facts and query.
store_facts(WorksFor(subject=alice, object=acme), WorksFor(subject=bob, object=acme))

list(query(ColleaguesOf(alice, Var[Employee]("x"))))   # -> [{'x': <Employee bob>}]
exists(WorksFor(alice, acme))                           # -> True
```

A fact with no `@store` is **inferred** — it has no storage and is derived by rules.

## Core Concepts

### Facts
A fact is the logical relation. Use `Term[X]` (shorthand for `X | Var[X]`) for
each slot — "an `X`, or a variable standing for an `X`":

```python
from django_datalog.models import Fact, Term, Var, store

class WorksFor(Fact):
    subject: Term[Employee]  # Employee
    object: Term[Company]    # Company

class ColleaguesOf(Fact):  # Inferred facts have no storage
    subject: Term[Employee]
    object: Term[Employee]
```

A **stored** fact reads and writes an explicit Django model that you declare and
bind with `@store` — you own the table, its migrations, indexes and constraints:

```python
@store(WorksFor)
class WorksForStorage(models.Model):
    subject = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="+")
    object  = models.ForeignKey(Company,  on_delete=models.CASCADE, related_name="+")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["subject", "object"], name="worksfor_edge")]
```

Or map a fact onto an **existing** table:
`@store(WorksFor, subject="employee_id", object="company_id", where=Q(active=True), readonly=True)`.
Inferred facts need no `@store`.

> **Migrating** from a version that generated `<Name>Storage` models? Declare
> one explicit storage model per stored fact and bind it with `@store` — each is
> a mechanical `subject`/`object` `ForeignKey` pair matching the fact's types, so
> a coding agent can generate them from your fact definitions.

### N-ary relations
A fact is not limited to two positions. Declare any positions you need, and mix
**entity** positions (a FK to a Django model) with **value** positions (a typed
value, e.g. an enum member). Every position is typed — use `Term[X]` so the
position accepts an `X` or a `Var[X]`:

```python
class Rank(models.TextChoices):
    MASTER = "master", "Master"
    CHIEF_MATE = "chief_mate", "Chief Mate"

class Crew(Fact):
    user: Term[User]      # entity (FK)
    rank: Term[Rank]      # value (an enum member, not a model)
    vessel: Term[Vessel]  # entity (FK)

@store(Crew)
class CrewStorage(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="+")
    rank = models.CharField(max_length=32, choices=Rank.choices)
    vessel = models.ForeignKey(Vessel, on_delete=models.CASCADE, related_name="+")

    class Meta:
        unique_together = (("user", "rank", "vessel"),)
```

Everything works over the fact's positions:

```python
store_facts(Crew(user=alice, rank=Rank.MASTER, vessel=aurora))

# Pin the value position; leave the entities free.
masters = query(Crew(Var[User]("u"), Rank.MASTER, Var[Vessel]("v")))

# Pin an entity; read the rest.
alices_ranks = query(Crew(alice, Var[Rank]("r"), Var[Vessel]("v")))

exists(Crew(alice, Rank.MASTER, aurora))                        # access-style check
as_queryset(Crew(alice, Rank.MASTER, Var[Vessel]("v")), on="vessel")  # queryset of vessels
```

A value position stays its value through hydration. An entity position hydrates
to its model instance and accepts a `where` constraint. Binary `subject`/`object`
facts are unchanged and keep every query optimization.

### Typed variables
`Var` is parametric: `Var[Employee]("emp")` records that the variable stands
for an `Employee`, so it only fits into `Employee`-typed slots. Create each
variable once and reuse it across a rule/query — the type is carried along and
a type checker rejects a variable used in the wrong position:

```python
emp = Var[Employee]("emp")
company = Var[Company]("company")

query(WorksFor(emp, company))    # ✅ ok
query(WorksFor(company, emp))    # ✗ type error: Var[Company] can't be an Employee slot
```

Bare `Var("emp")` is still valid (inferred from the slot it fills), so the
type parameter is fully opt-in and backward compatible.

### Rules
Define inference logic with tuples (AND) and lists (OR):

```python
from django_datalog.rules import rule

# Simple rule: Colleagues work at same company
emp1, emp2 = Var[Employee]("emp1"), Var[Employee]("emp2")
company = Var[Company]("company")
rule(
    ColleaguesOf(emp1, emp2),
    WorksFor(emp1, company) & WorksFor(emp2, company)
)

# Disjunctive rule: HasAccess via admin OR manager
user, resource = Var[User]("user"), Var[Resource]("resource")
rule(
    HasAccess(user, resource),
    IsAdmin(user) | IsManager(user, resource)
)

# Mixed rule: Complex access control
user, doc, folder = Var[User]("user"), Var[Document]("doc"), Var[Folder]("folder")
rule(
    CanEdit(user, doc),
    IsOwner(user, doc) |
    (IsManager(user, folder) & Contains(folder, doc))
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

### Async interface
Every read/write has an `a`-prefixed async counterpart — `aquery`,
`astore_facts`, and `aretract_facts` — for use from async views and tasks.
They mirror the sync API exactly and run the engine in Django's
thread-sensitive executor, so they share the ORM connection context:

```python
from django_datalog.models import aquery, astore_facts, aretract_facts, Var

async def handler(request):
    await astore_facts(WorksFor(alice, tech_corp))

    # aquery awaits and returns a list (already materialized)
    results = await aquery(
        WorksFor(Var[Employee]("emp"), Var[Company]("company")),
    )

    await aretract_facts(WorksFor(alice, tech_corp))
```

### Composable querysets
`as_queryset` resolves an inferred query and hands back a lazy Django
`QuerySet` you can compose with the ORM — ideal for access-control read paths
(the target model is inferred from the fact when you omit it):

```python
from django_datalog.models import as_queryset, aas_queryset, Var

# Vessels a user can access, then compose freely with the ORM:
vessels = as_queryset(CanAccessVessel(user, Var("v")), on="object")
active = vessels.filter(active=True).order_by("name")

# async variant
vessels = await aas_queryset(CanAccessVessel(user, Var("v")), on="object")
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
# Basic variable (typed — only fits Employee slots)
emp = Var[Employee]("employee")

# With Django Q constraints
senior_emp = Var[Employee]("employee", where=Q(years_experience__gte=5))

# Multiple constraints
constrained = Var[Employee]("emp", where=Q(is_active=True) & Q(department="Engineering"))

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
    subject: Term[Employee]
    object: Term[Company]

class WorksOn(Fact):
    subject: Term[Employee]
    object: Term[Project]

class ColleaguesOf(Fact):   # inferred: no storage
    subject: Term[Employee]
    object: Term[Employee]

# storage.py — explicit models for the stored facts
@store(WorksFor)
class WorksForStorage(models.Model):
    subject = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="+")
    object  = models.ForeignKey(Company,  on_delete=models.CASCADE, related_name="+")

@store(WorksOn)
class WorksOnStorage(models.Model):
    subject = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="+")
    object  = models.ForeignKey(Project,  on_delete=models.CASCADE, related_name="+")

# rules.py
emp1, emp2 = Var[Employee]("emp1"), Var[Employee]("emp2")
company = Var[Company]("company")
rule(
    ColleaguesOf(emp1, emp2),
    WorksFor(emp1, company) & WorksFor(emp2, company)
)

# usage.py
store_facts(
    WorksFor(subject=alice, object=tech_corp),
    WorksFor(subject=bob, object=tech_corp),
    WorksOn(subject=alice, object=tech_project),
    WorksOn(subject=bob, object=other_project),
)

# Simple queries (automatically optimized)
colleagues = query(ColleaguesOf(alice, Var[Employee]("colleague")))

# Complex cross-variable constraints (75% query reduction!)
emp, company = Var[Employee]("emp"), Var[Company]("company")
same_company_projects = query(
    WorksFor(emp, company),
    WorksOn(emp, Var[Project]("project", where=Q(company=company)))
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

- Python 3.12+
- Django 5.2 (LTS)

## License

MIT License
