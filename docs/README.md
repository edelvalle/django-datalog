# Django-datalog Documentation

This directory contains technical documentation and reference materials for django-datalog.

## Contents

- **[django_orm_equivalents.md](django_orm_equivalents.md)** - How to convert django-datalog queries to pure Django ORM, with performance comparisons and conversion patterns

## Related Documentation

- **[../README.md](../README.md)** - Main project README with installation and usage examples  
- **[../CHANGELOG.md](../CHANGELOG.md)** - Version history and feature changes
- **[../CLAUDE.md](../CLAUDE.md)** - Development guide for working on this project

## Key Features Reference

### Cross-Variable Constraints
Variables can reference other variables in Q constraints:
```python
Var("project", where=Q(company=Var("company")))
```

### Advanced Query Analysis
- AST-based query optimization
- Up to 75% query reduction for complex patterns
- 100% Django ORM - eliminates SQL injection vulnerabilities
- Zero configuration - works transparently

### CLI Tools
```bash
python manage.py convert_to_orm --analyze        # Pattern analysis
python manage.py convert_to_orm --interactive    # Interactive mode  
python manage.py convert_to_orm --file queries.py # File processing
```