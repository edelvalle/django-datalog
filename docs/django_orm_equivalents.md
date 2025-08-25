# Django ORM Equivalents of Cross-Variable Constraints

This document shows how to convert django-datalog cross-variable constraint queries into pure Django ORM queries for reference and performance comparison.

## Performance Comparison

The advanced query analyzer in django-datalog now automatically optimizes queries to achieve excellent performance, but understanding the Django ORM equivalents can be helpful for debugging and learning.

| Approach | Query Count | Efficiency | Security |
|----------|-------------|------------|----------|
| Original django-datalog | 16 queries | Baseline | ✅ Safe |
| **Advanced analyzer django-datalog** | **4 queries** | **75% improvement** | ✅ Safe |
| Pure Django ORM (manual) | 1 query | 94% improvement | ✅ Safe |

> **Note**: The advanced query analyzer automatically generates optimized Django ORM queries similar to the manual examples below.

## Key Conversion Patterns

### 1. Simple Cross-Variable Constraint

**Django-datalog (automatically optimized):**
```python
query(
    WorksFor(Var("emp"), Var("company")),
    WorksOn(Var("emp"), Var("project", where=Q(company=Var("company"))))
)
# Advanced analyzer automatically converts this to optimized Django ORM
```

**Equivalent Django ORM (manual):**
```python
from django.db.models import Exists, OuterRef

Employee.objects.filter(
    Exists(WorksForStorage.objects.filter(subject=OuterRef('pk'))),
    Exists(WorksOnStorage.objects.filter(
        subject=OuterRef('pk'),
        object__company=OuterRef('company')
    ))
).select_related('company')
```

**Generated SQL (by advanced analyzer):**
```sql
SELECT ... FROM testdjdatalog_worksforstorage 
INNER JOIN testdjdatalog_employee ON (worksforstorage.subject_id = employee.id) 
INNER JOIN testdjdatalog_company ON (worksforstorage.object_id = company.id)
WHERE EXISTS(
    SELECT 1 FROM testdjdatalog_worksonstorage U0 
    INNER JOIN testdjdatalog_project U2 ON (U0.object_id = U2.id) 
    WHERE (U0.subject_id = worksforstorage.subject_id 
           AND U2.company_id = worksforstorage.object_id) 
    LIMIT 1
)
```

### 2. Department-Company Relationship

**Django-datalog:**
```python
query(
    MemberOf(Var("emp"), Var("dept")),
    WorksFor(Var("emp"), Var("company", where=Q(is_active=True, department__in=[Var("dept")])))
)
```

**Django ORM equivalent:**
```python
from django.db.models import F

Employee.objects.filter(
    company__is_active=True,
    department__company=F('company')
)
```

### 3. Same Entity in Multiple Facts

**Django-datalog:**
```python
query(
    WorksFor(Var("emp"), Var("company")),
    MemberOf(Var("emp"), Var("dept", where=Q(company=Var("company"))))
)
```

**Django ORM equivalent:**
```python
Employee.objects.filter(
    department__company=F('company')
)
```

## Conversion Rules

| Django-datalog Pattern | Django ORM Equivalent | Notes |
|------------------------|----------------------|-------|
| `Var('field', where=Q(related_field=Var('other')))` | `F('related_field') = F('other_field')` | Field comparison |
| Cross-variable constraints | `Exists()` with `OuterRef()` | Subquery pattern |
| Multiple facts with same variable | JOIN conditions | Automatic JOINs |
| Complex constraints | Subqueries or `F()` expressions | Advanced patterns |

## Advanced Query Analysis System

Django-datalog's advanced query analyzer automatically handles these conversions:

### AST-Based Analysis
- Parses queries into abstract syntax trees
- Analyzes variable relationships and dependencies
- Creates optimized execution plans

### Automatic ORM Generation
- Builds complex Django ORM queries with EXISTS subqueries
- Handles cross-variable constraint resolution with OuterRef
- Uses recursive ORM construction for complex patterns

### Performance Benefits
- Up to 75% query reduction (16→4 queries) for complex patterns
- 100% Django ORM - eliminates SQL injection vulnerabilities
- Zero configuration - works transparently

## When to Use Each Approach

### Use django-datalog when:
- You need **logic programming** features (rules, inference)
- Working with **complex rule-based systems**
- Need **declarative query syntax**
- Building **expert systems** or **AI applications**
- Want **automatic optimization** without manual ORM coding

### Use pure Django ORM when:
- You need **maximum performance** for simple queries
- Working with **simple relational queries**
- Team is **highly experienced with Django ORM**
- Need **full control** over SQL generation

## Example: Finding Employees on Same-Company Projects

This query finds employees who work on projects from their own company (excluding cross-company assignments).

### Test Data Results:
- **Alice** (TechCorp) → Project Alpha (TechCorp) ✅
- **Bob** (TechCorp) → Project Alpha (TechCorp) ✅  
- **Charlie** (TechCorp) → Cross Project (OldCorp) ❌ *filtered out*
- **Dave** (OldCorp) → Project Beta (OldCorp) ✅

### Django-datalog (4 queries with advanced analyzer):
```python
results = list(query(
    WorksFor(Var("emp"), Var("company")),
    WorksOn(Var("emp"), Var("project", where=Q(company=Var("company"))))
))
# Returns 3 results (Alice, Bob, Dave) - Charlie excluded by constraint
```

### Manual Django ORM (1 query):
```python
from django.db.models import Exists, OuterRef

employees = Employee.objects.filter(
    Exists(WorksForStorage.objects.filter(subject=OuterRef('pk'))),
    Exists(WorksOnStorage.objects.filter(
        subject=OuterRef('pk'),
        object__company=OuterRef('company')
    ))
)
```

## CLI Tools for Analysis

Django-datalog provides CLI tools to analyze query patterns:

```bash
# Analyze query patterns and get optimization recommendations
python manage.py convert_to_orm --analyze

# Interactive query analysis
python manage.py convert_to_orm --interactive

# Process file with django-datalog queries
python manage.py convert_to_orm --file my_queries.py
```

## Summary

The advanced query analyzer in django-datalog automatically generates optimized Django ORM queries similar to the manual examples shown above. This provides the best of both worlds:

- **Declarative syntax** of logic programming
- **Performance** approaching hand-optimized Django ORM
- **Security** through 100% Django ORM usage
- **Zero configuration** - optimization happens automatically

For most use cases, the django-datalog approach with automatic optimization is recommended as it provides excellent performance with much simpler, more maintainable code.