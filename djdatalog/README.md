# djdatalog

A powerful Django extension that brings Datalog-style logic programming to Django ORM. Build complex permission systems, relationship inference, and logical queries with ease.

## 🚀 Features

- **Declarative Logic Programming**: Define facts and rules using Python dataclasses
- **Automatic Django Integration**: Generates Django models for fact storage automatically  
- **Query Optimization**: Built-in query optimization with PK hydration and batch processing
- **Q Object Constraints**: Combine Datalog queries with Django Q objects for powerful filtering
- **Inference Engine**: Automatic rule evaluation with cycle detection and optimization
- **Performance First**: Optimized for large datasets with selective hydration and intelligent batching

## 📦 Installation

```bash
pip install djdatalog
```

Add to your Django settings:

```python
INSTALLED_APPS = [
    # ... your apps
    'djdatalog',
]
```

Run migrations:

```bash
python manage.py makemigrations djdatalog
python manage.py migrate
```

## 🎯 Quick Start

### 1. Define Your Facts

```python
from dataclasses import dataclass
from djdatalog.models import Fact, Var
from myapp.models import Person

@dataclass
class ParentOf(Fact):
    """Person is parent of another person"""
    subject: Person | Var  # Parent
    object: Person | Var   # Child

@dataclass
class MarriedTo(Fact):
    """Person is married to another person"""
    subject: Person | Var  # Spouse 1
    object: Person | Var   # Spouse 2

@dataclass
class GrandparentOf(Fact):
    """Person is grandparent of another person"""
    subject: Person | Var  # Grandparent
    object: Person | Var   # Grandchild
```

### 2. Define Inference Rules

```python
from djdatalog.models import rule

# Rule: Grandparents are inferred from parent relationships
rule(
    GrandparentOf(Var("grandparent"), Var("grandchild")),
    # :=  (implied by)
    ParentOf(Var("grandparent"), Var("parent")),
    ParentOf(Var("parent"), Var("grandchild"))
)
```

### 3. Store and Query Facts

```python
from djdatalog.models import store_facts, query

# Store facts
john = Person.objects.get(name="John")
alice = Person.objects.get(name="Alice")
bob = Person.objects.get(name="Bob")

store_facts(
    ParentOf(subject=john, object=alice),  # John is parent of Alice
    ParentOf(subject=alice, object=bob)    # Alice is parent of Bob
)

# Query with automatic inference
for result in query(GrandparentOf(john, Var("grandchild"))):
    print(f"{john.name} is grandparent of {result['grandchild'].name}")
    # Output: "John is grandparent of Bob"
```

## 🔥 Advanced Features

### Q Object Constraints

Combine Datalog logic with Django's Q objects for powerful database-level filtering:

```python
from django.db.models import Q

# Get only adult children (18+)
adult_children = []
for result in query(ParentOf(john, Var("child", where=Q(age__gte=18)))):
    adult_children.append(result["child"])

# Complex constraints - married adults living in New York
married_adults_ny = query(
    ParentOf(Var("parent"), Var("child", where=Q(age__gte=18) & Q(married=True) & Q(city="New York")))
)
```

### Performance Optimization

Control hydration for better performance:

```python
# Get only IDs (fast)
vessel_ids = []
for result in query(HasAccess(user, Var("vessel")), hydrate=False):
    vessel_ids.append(result["vessel"])  # This is just the ID

# Get full objects (default)  
vessels = []
for result in query(HasAccess(user, Var("vessel")), hydrate=True):
    vessels.append(result["vessel"])  # This is the full model instance
```

### Complex Rules

```python
# Multiple conditions in rules
rule(
    HasAccess(Var("user"), Var("vessel")),
    # User has access if they are staff OR company member
    ShoreStaffOf(Var("user"), Var("vessel")),
    CrewOf(Var("user"), Var("vessel")),
    [  # OR condition (nested list)
        MemberOf(Var("user"), Var("company")),
        Owns(Var("company"), Var("vessel"))
    ]
)

# Conditional rules
rule(
    CanEdit(Var("user"), Var("vessel")),
    HasAccess(Var("user"), Var("vessel")),
    AdminOf(Var("user"), Var("vessel"))
)
```

## 📚 Core Concepts

### Facts

Facts represent relationships between entities. They're defined as dataclasses inheriting from `Fact`:

```python
@dataclass
class WorksFor(Fact):
    subject: Employee | Var  # Employee works for
    object: Company | Var    # Company
```

Facts automatically generate Django models for persistence with optimized indexing.

### Variables 

Variables (`Var`) are placeholders in queries and rules:

```python
# Find all companies where John works
for result in query(WorksFor(john, Var("company"))):
    print(result["company"])

# With constraints
for result in query(WorksFor(john, Var("company", where=Q(active=True)))):
    print(result["company"])  
```

### Rules

Rules define logical implications - how new facts can be inferred from existing ones:

```python
rule(
    # Head (what we can infer)
    ColleaguesOf(Var("person1"), Var("person2")),
    
    # Body (conditions that must be true)
    WorksFor(Var("person1"), Var("company")),
    WorksFor(Var("person2"), Var("company"))
)
```

## 🛠️ API Reference

### Core Functions

#### `query(*fact_patterns, hydrate=True)`

Query facts with automatic rule inference.

**Parameters:**
- `*fact_patterns`: Fact patterns to match (conjunction)
- `hydrate`: If `True` (default), return full model instances. If `False`, return PKs only.

**Returns:** Iterator of dictionaries mapping variable names to values.

#### `store_facts(*facts)`

Store facts in the database.

**Parameters:**
- `*facts`: Fact instances to store

#### `retract_facts(*facts)`

Remove facts from the database.

**Parameters:**
- `*facts`: Fact instances to remove

#### `rule(head, *body)`

Define an inference rule.

**Parameters:**
- `head`: The fact that can be inferred
- `*body`: Conditions that must be true (supports nested lists for OR conditions)

### Fact Class

Base class for all facts:

```python
@dataclass  
class MyFact(Fact):
    subject: ModelA | Var
    object: ModelB | Var
```

### Var Class

Variable placeholder for queries:

```python
Var(name: str, where: Q = None)
```

**Parameters:**
- `name`: Variable name
- `where`: Optional Django Q object for constraints

## 🎨 Use Cases

### Permission Systems

```python
# Define permission facts
@dataclass
class HasRole(Fact):
    subject: User | Var
    object: Role | Var

@dataclass  
class RolePermits(Fact):
    subject: Role | Var
    object: Permission | Var

@dataclass
class CanPerform(Fact):
    subject: User | Var
    object: Permission | Var

# Rule: Users can perform actions their roles permit
rule(
    CanPerform(Var("user"), Var("permission")),
    HasRole(Var("user"), Var("role")),
    RolePermits(Var("role"), Var("permission"))
)
```

### Organizational Hierarchies

```python
@dataclass
class ReportsTo(Fact):
    subject: Employee | Var
    object: Employee | Var

@dataclass  
class IsManager(Fact):
    subject: Employee | Var
    object: Employee | Var

# Transitive closure: If A reports to B and B reports to C, then A reports to C
rule(
    IsManager(Var("manager"), Var("employee")),
    ReportsTo(Var("employee"), Var("manager"))
)

rule(
    IsManager(Var("senior"), Var("junior")),
    ReportsTo(Var("junior"), Var("middle")),
    IsManager(Var("senior"), Var("middle"))
)
```

### Graph Relationships

```python
@dataclass
class Connected(Fact):
    subject: Node | Var
    object: Node | Var

@dataclass
class Reachable(Fact):  
    subject: Node | Var
    object: Node | Var

# Transitive reachability
rule(
    Reachable(Var("start"), Var("end")),
    Connected(Var("start"), Var("end"))
)

rule(
    Reachable(Var("start"), Var("end")),
    Connected(Var("start"), Var("middle")),
    Reachable(Var("middle"), Var("end"))
)
```

## ⚡ Performance Tips

1. **Use `hydrate=False`** when you only need IDs:
   ```python
   ids = [r["vessel"] for r in query(HasAccess(user, Var("vessel")), hydrate=False)]
   ```

2. **Add Q object constraints** to filter at database level:
   ```python
   query(HasAccess(user, Var("vessel", where=Q(active=True))))
   ```

3. **Batch fact operations**:
   ```python
   store_facts(*[MemberOf(user, company) for user in users])
   ```

4. **Design efficient rules** - put more selective conditions first:
   ```python
   rule(
       HasAccess(Var("user"), Var("vessel")),
       SpecificRole(Var("user"), Var("vessel")),  # More selective first
       GeneralMembership(Var("user"), Var("company"))  # Less selective second
   )
   ```

## 🐛 Troubleshooting

### Common Issues

**Q: My rules aren't working**
- Check that all variables in the rule body are bound
- Ensure fact tables are populated  
- Verify Django models are properly migrated

**Q: Queries are slow**
- Use `hydrate=False` when possible
- Add Q object constraints to filter early
- Check your rule ordering - put selective conditions first

**Q: Getting infinite recursion**
- djdatalog has built-in cycle detection, but complex recursive rules may hit limits
- Consider restructuring rules to be more specific

## 🤝 Contributing

We welcome contributions! Please see our contributing guidelines for details.

## 📄 License

MIT License - see LICENSE file for details.

## 🔗 Links

- **Documentation**: [Coming Soon]
- **Issue Tracker**: [GitHub Issues]
- **Discussions**: [GitHub Discussions]

---

*djdatalog brings the power of logic programming to Django, making complex relational queries simple and intuitive.*