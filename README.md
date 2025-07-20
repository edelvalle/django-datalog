# django-datalog

Django Datalog - A logic programming and inference engine for Django applications.

## Features

- **Fact-based data modeling**: Define facts as Python dataclasses with Django model integration
- **Logic programming**: Write inference rules using a familiar Python syntax  
- **Query system**: Query facts and derived conclusions with variable binding
- **Q object constraints**: Filter query results using Django Q objects
- **Performance optimized**: Intelligent query reordering and batch hydration
- **Django integration**: Seamless integration with existing Django models and ORM

## Quick Start

### Installation

```bash
pip install django-datalog
```

Add `djdatalog` to your `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    # ... your other apps
    'djdatalog',
]
```

### Basic Usage

```python
from dataclasses import dataclass
from djdatalog import Fact, Var, query, rule, store_facts
from django.contrib.auth.models import User

# Define facts
@dataclass
class ParentOf(Fact):
    \"\"\"Person is parent of another person\"\"\"
    subject: User | Var  # Parent
    object: User | Var   # Child

@dataclass 
class GrandparentOf(Fact):
    \"\"\"Person is grandparent of another person (inferred)\"\"\"
    subject: User | Var  # Grandparent
    object: User | Var   # Grandchild

# Define inference rules
rule(
    GrandparentOf(Var("grandparent"), Var("grandchild")),
    # := (implied by)
    ParentOf(Var("grandparent"), Var("parent")),
    ParentOf(Var("parent"), Var("grandchild"))
)

# Store facts
john = User.objects.get(username="john")
alice = User.objects.get(username="alice") 
bob = User.objects.get(username="bob")

store_facts(
    ParentOf(subject=john, object=alice),
    ParentOf(subject=alice, object=bob)
)

# Query with inference
for result in query(GrandparentOf(john, Var("grandchild"))):
    print(f"John is grandparent of {result['grandchild'].username}")
    # Output: John is grandparent of bob

# Query with constraints
from django.db.models import Q

for result in query(ParentOf(Var("parent", where=Q(is_active=True)), Var("child"))):
    print(f"{result['parent']} -> {result['child']}")
```

## Advanced Features

### Q Object Constraints

Filter query variables using Django Q objects:

```python
# Find active users who are parents
active_parents = query(ParentOf(Var("parent", where=Q(is_active=True)), Var("child")))

# Complex constraints with AND/OR
adults = query(ParentOf(
    Var("parent", where=Q(age__gte=18) & Q(is_staff=False)), 
    Var("child")
))
```

### Hydration Control

Control whether to fetch full model instances or just PKs:

```python
# Get full objects (default)
results = list(query(ParentOf(alice, Var("child")), hydrate=True))
print(results[0]["child"].username)  # Full User object

# Get PKs only (better performance)  
results = list(query(ParentOf(alice, Var("child")), hydrate=False))
print(results[0]["child"])  # Just the user ID
```

### Multiple Rules

Chain multiple inference rules:

```python
@dataclass
class SiblingOf(Fact):
    subject: User | Var
    object: User | Var

# Rule: People are siblings if they have the same parent
rule(
    SiblingOf(Var("person1"), Var("person2")),
    ParentOf(Var("parent"), Var("person1")),
    ParentOf(Var("parent"), Var("person2"))
)

# Rule: Siblings are mutual (symmetric relationship)
rule(
    SiblingOf(Var("person2"), Var("person1")), 
    SiblingOf(Var("person1"), Var("person2"))
)
```

## Documentation

For full documentation, visit [our documentation site](#) (to be added).

## Contributing

We welcome contributions! Please see our [Contributing Guide](#) for details.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history and changes.