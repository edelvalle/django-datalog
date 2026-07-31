# Plan: explicit storage models (`@store`), remove model generation

Status: proposal, 2026-07-29. Target release: **0.6.0** (breaking).

## Motivation

Today a stored `Fact` dynamically generates a Django model in
`Fact.__init_subclass__` (`type(f"{Name}Storage", (FactModel,), ...)`). Per VP
feedback this is risky and hard to maintain:

- the storage tables have no source-of-truth model file and their migrations are
  implicit/magic;
- you cannot add a column or index that an optimizer needs, because there is no
  real model to put it on — you would have to reach into the generator;
- constraints live in the generator, not where a maintainer expects them.

Goal: **zero magic. Storage models are explicit and user-owned.** A `Fact` is
bound to its storage model with a decorator. Constraints, indexes, and any
optimizer columns live on that explicit model with normal migrations.

## Target API

`Fact` stays the *logical predicate* — it declares position types for rules,
`Var` typing, and model extraction. It generates nothing:

```python
class WorksFor(Fact):
    subject: Term[Employee]
    object:  Term[Company]
```

Storage is an explicit model, bound with `@store(Fact)`:

```python
@store(WorksFor)
class WorksForStorage(models.Model):
    subject = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="+")
    object  = models.ForeignKey(Company,  on_delete=models.CASCADE, related_name="+")

    class Meta:                        # constraints + indexes live here now
        constraints = [models.UniqueConstraint(fields=["subject", "object"], name="worksfor_edge")]
        indexes = [models.Index(fields=["object"])]
```

Reusing an existing table (subsumes the earlier "source-backed facts" idea) via
column mapping:

```python
@store(WorksFor, subject="employee_id", object="company_id", where=Q(active=True), readonly=True)
class Employment(models.Model):
    employee = FK(Employee); company = FK(Company); active = BooleanField()
```

`@store` signature:

```python
def store(fact_cls, *, subject="subject", object="object", where=None, readonly=False):
    def bind(model_cls):
        fact_cls._django_model = model_cls
        fact_cls._subject_col = subject
        fact_cls._object_col = object
        fact_cls._source_where = where
        fact_cls._readonly = readonly
        # validate: subject/object annotation models match the mapped FK targets
        return model_cls
    return bind
```

## What is removed

- `Fact._create_django_model` and the abstract `FactModel` — deleted.
- **`unique=` / `Unique` (0.5.3)** — obsolete; constraints move to the model's
  `Meta`. Removed in 0.6.0.
- Auto-injection of `<Name>Storage` into the fact's module — gone.

## Engine changes (query.py) — mostly recoverable from the reverted source-backed commit

The engine assumes fields literally named `subject`/`object`. Generalize to the
mapped columns (the reverted source-backed branch already did ~80% of this;
recover it from git and adapt to the current engine):

- `_load_stored_facts_for_pattern`: apply `_source_where`; read the mapped
  columns as pks via `.values(subject_col, object_col)`; facts carry pks.
- `_fact_to_django_query`: filter/relate through the mapped columns; concrete
  position → pk; a `Var.where` is prefixed via the relation name (strip a
  trailing `_id`).
- Unification (`_unify_facts` / `_unify_fact_pattern`): compare concrete
  positions by pk (`getattr(v, "pk", v)`), so an instance pattern matches a
  pk-carrying fact.
- `_try_automatic_orm_conversion`: the advanced analyzer assumes subject/object
  fields — keep using it when the column map is the default (`subject`/`object`);
  defer to the loader path for mapped columns.
- Hydration: resolve pks → instances from the position model types (unchanged).

Every change must be re-verified against the current engine (goal-directed
specialization, lazy `exists`/`first`, H0–H4) with the full suite **and** the
benchmark, so we don't regress the performance work.

## store_facts / retract_facts

- Write through the bound model: `model(**{subject_col: f.subject, object_col: f.object})`,
  `bulk_create(..., ignore_conflicts=True)`.
- `readonly=True` (or unbound) → raise a clear error.
- Unbound stored fact used in a query → clear error: "WorksFor has no storage;
  bind a model with @store(WorksFor)".

## Backward compatibility

Breaking for every stored fact (including downstream Kaiko). Mitigations:

1. **`manage.py datalog_make_storage`** — prints the explicit model + `@store`
   decorator for each currently-defined `Fact`, so migration is copy-paste. The
   old generator logic already knows how to build the model; the command emits
   its source.
2. **Migration guide** in `docs/` + README rewrite of the facts section.
3. Chosen path (see open decisions): hard break at 0.6.0, or a deprecation
   window that keeps the generator with a `DeprecationWarning` and removes it in
   a later major.

## Work breakdown

0. Recover the reverted source-backed engine code (column mapping, pk
   unification, column-aware loading) from git as the foundation.
1. `@store` decorator + `Fact` binding attrs; delete `_create_django_model` +
   `FactModel`; unbound-fact errors.
2. Engine column-awareness (load / filter / unify / hydrate); analyzer split.
3. `store_facts` / `retract_facts` through the bound model + `readonly`.
4. Remove `unique=` / `Unique`; document constraints-on-model.
5. `datalog_make_storage` codegen command + migration guide.
6. Convert `test_project`'s ~17 facts to explicit models + `@store` + real
   migrations; update all tests. Re-run full suite + benchmark.
7. README/CHANGELOG; cut 0.6.0.

## Risks

- Big breaking change; Kaiko must migrate (codegen + guide reduce cost).
- Engine column-awareness must not regress the perf/lazy work — cross-check with
  the full suite and `make benchmark` at each step.
- `test_project` migration is a large but mechanical diff.

## Open decisions (need sign-off before building)

1. Decorator on the model (`@store(WorksFor)`) — confirmed by the sketch.
2. Include column mapping (`subject=`/`object=`/`where=`/`readonly=`) so an
   existing table can back a fact? (Recommended — near-free, subsumes
   source-backed.)
3. **Hard break at 0.6.0** (VP's intent) **vs deprecation window** (gentler on
   Kaiko). Recommend hard break + `datalog_make_storage`.
4. Keep the `Fact` position annotations (yes — needed for `Var` typing, model
   extraction, and to validate they agree with the model's FK targets).
