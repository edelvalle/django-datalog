# Work brief: chained inference (correctness) then query performance

Status: brief for the django-datalog maintainer/agent, 2026-07-24.
Priority order (agreed): **(1) correctness — chained inference must work all the
way; (2) performance — rule evaluation must scale.**  Do #1 first; its tests must
stay green while #2 is implemented.

Context: a downstream project (Kaiko) modelled its access-control in
django-datalog 0.4.1 and hit two blockers. Both are reproduced below against
this repo's own vocabulary so they can be turned into failing tests directly.

---

# Part 1 — Correctness: inference does not chain through rule bodies

## Symptom

A rule whose **head** is inferred works when its **body** references only
*stored* facts.  As soon as a rule body references **another inferred fact**, the
query returns nothing — no error, just an empty result.

## Minimal reproduction (self-contained, add as a failing test)

```python
from dataclasses import dataclass
from django_datalog import Fact, Var, query, rule, store_facts

@dataclass
class WorksFor(Fact):                       # STORED
    subject: Employee | Var
    object: Company | Var

@dataclass
class Colleague(Fact, inferred=True):       # level-1 inferred (body: stored facts)
    subject: Employee | Var
    object: Employee | Var

@dataclass
class InSameNetwork(Fact, inferred=True):   # level-2 inferred (body: an inferred fact)
    subject: Employee | Var
    object: Employee | Var

# Colleague := two employees who work for the same company
rule(Colleague(Var("a"), Var("b")),
     WorksFor(Var("a"), Var("c")) & WorksFor(Var("b"), Var("c")))

# InSameNetwork := just re-exposes Colleague (the simplest possible chain)
rule(InSameNetwork(Var("a"), Var("b")),
     Colleague(Var("a"), Var("b")))

store_facts(WorksFor(alice, acme), WorksFor(bob, acme))

list(query(Colleague(alice, Var("x"))))      # ✅ [{'x': bob.pk}]   — rule over STORED facts
list(query(InSameNetwork(alice, Var("x"))))  # ❌ []  EXPECTED [{'x': bob.pk}]
```

`Colleague` resolves (its body is stored `WorksFor`). `InSameNetwork` returns
empty because its body references the inferred `Colleague`, which the engine
never materialises while resolving `InSameNetwork`.

### The real-world case that motivated this

```python
# StaffOf / MemberOf / Owns are STORED; CanAccessVessel and the Comment relation are inferred.
rule(CanAccessVessel(u, v), StaffOf(u, v) | (MemberOf(u, c) & Owns(c, v)))     # works
rule(SharesVesselWith(u, u2), CanAccessVessel(u, v) & CanAccessVessel(u2, v))  # returns []
```

`CanAccessVessel(user, Var("v"))` resolves correctly (including concrete subject +
free object). `SharesVesselWith(user, Var("u2"))` — a self-join over the inferred
`CanAccessVessel` — returns empty. Downstream had to drop the rule and compose
the primitive in Python; that is the workaround this task removes.

## Root cause (verified, with `file:line`)

The single-inferred-level case works because `apply_targeted_rules`
(`rules.py:168`) runs a proper fixpoint. The chain breaks earlier, when the fact
base and rule set for that fixpoint are assembled:

1. `_get_facts_for_pattern` (`query.py:126`) selects **only** rules whose head
   type equals the *target* pattern type:
   ```python
   for rule in get_rules():
       if type(rule.head) is type(pattern):   # query.py:134
           relevant_rules.append(rule)
   ```
   Resolving `InSameNetwork` therefore collects the `InSameNetwork` rule only —
   the `Colleague` rule is **excluded**, so `Colleague` is never derived.

2. `_build_targeted_fact_base_for_rules` (`query.py:193`) builds the base for
   those rules by loading, per body condition, **stored facts only**:
   ```python
   condition_facts = _load_stored_facts_for_pattern(targeted_condition)  # query.py:204
   ```
   and `_load_stored_facts_for_pattern` returns `[]` for inferred facts:
   ```python
   if fact_class._is_inferred:   # query.py:154
       return []
   ```
   So the `Colleague` condition inside `InSameNetwork`'s body contributes **zero**
   facts to the base.

Net: `apply_targeted_rules` runs over a base with no `Colleague` facts and a rule
set without the `Colleague` rule → derives nothing → empty result. No cycle
detection is involved; the intermediate level is simply never computed.

## Fix direction

Make body-condition resolution **transitive**. Two equivalent shapes; pick one:

- **Recursive resolution (preferred).** In `_build_targeted_fact_base_for_rules`,
  for each body condition: if the condition's fact type is inferred, resolve it
  with `_get_facts_for_pattern(condition)` (which loads stored facts *and* applies
  its rules) instead of `_load_stored_facts_for_pattern`; otherwise load stored as
  today. This naturally recurses to any depth.

- **Transitive rule closure.** Before the fixpoint, expand `relevant_rules` to the
  closure: the target rule plus every rule whose head type appears (recursively)
  in the collected rule bodies; build the base from the *stored (leaf)* conditions
  across the whole closure; then run `apply_targeted_rules` with the full closure.
  The existing fixpoint (`rules.py:184`, `max_iterations=100`) already derives
  level-1 then level-2 once both rules and leaf facts are present.

**Termination / recursion (must handle):** support recursive rules (e.g. a
transitive-closure `Ancestor := Parent | (Parent & Ancestor)`) without infinite
recursion. Use memoization keyed by (fact type, bound positions) plus a
"currently-resolving" stack, or standard semi-naïve stratified evaluation. The
existing `max_iterations` guard in `apply_rules` is a backstop, not the design.

## Acceptance criteria (Part 1)

- The `InSameNetwork` reproduction above returns `[{'x': bob.pk}]`.
- A 3-level chain (`A :- B`, `B :- C`, `C :- stored`) resolves end to end.
- A **recursive** rule (transitive closure over a small `Parent` chain of depth
  ≥3) returns the full closure and terminates.
- Both `hydrate=True` and `hydrate=False`.
- Chained inference works with the outer query having concrete positions
  (`InSameNetwork(alice, Var("x"))`) and all-variable positions
  (`InSameNetwork(Var("a"), Var("b"))`).
- All existing tests (`make test`, and `test_project/`) stay green.

---

# Part 2 — Performance: rule evaluation must scale (do after Part 1)

## Symptom (measured on ~118k-edge production-shaped data)

- Enumerating one stored fact type (`10,223` rows): ~4 s.
- A single concrete-subject inferred query, `CanAccessVessel(user, Var("v"))` for a
  user with 273 results: **did not return within 45 s**.
- The all-variable enumeration `CanAccessVessel(Var, Var)`: does not complete.

The engine is only usable on tiny fact sets today, so datalog cannot be a runtime
read path.

## Root cause (verified, with `file:line`)

Every query that touches an inferred fact takes the in-memory fixpoint path, which
loads full fact extensions into Python lists and unifies with nested loops
(`_satisfy_conjunction_with_targeted_facts` `query.py:89` →
`_query_against_facts` `query.py:292`, O(facts) per condition, O(product) per
join). The fast ORM path is skipped for exactly the queries that need it:

`_try_automatic_orm_conversion` (`query.py:614`) raises `NotImplementedError`
(→ fixpoint fallback) when:

```python
if not hasattr(fact_class, '_django_model') or getattr(fact_class, 'inferred', False):
    raise NotImplementedError("ORM conversion only supports stored facts")   # query.py:627
if not isinstance(condition.subject, Var) or not isinstance(condition.object, Var):
    raise NotImplementedError("ORM conversion only supports variable positions")  # query.py:633
```

So (a) any inferred fact and (b) any concrete subject/object both force the slow
path. A per-user access check is *both*.

## Fix direction

Compile inferred-fact queries to Django ORM instead of a Python fixpoint:

- **Expand a (non-recursive) rule into a queryset over the base-fact storage
  models.** e.g. `CanAccessVessel(u, Var("v"))` →
  `StaffOfStorage.objects.filter(subject_id=u).values_list("object_id")` unioned
  with `OwnsStorage ⋈ MemberOfStorage.filter(subject_id=u)` — one SQL round trip,
  not a scan. OR-bodies → `Q(...) | Q(...)`; AND-bodies → joins/`__in` across
  storage models.
- **Support concrete positions** (remove the `query.py:633` bail): translate a
  concrete subject/object into `.filter(subject_id=…)`/`.filter(object_id=…)`.
- **Emit a queryset / `Q` from `query()`** (not just materialised PK dicts) so
  callers get a lazy JOIN they can compose — this is the downstream blocker for a
  real read path. A new `as_queryset=`/`compile()` entry point is fine.
- Recursive rules can stay on an (improved, semi-naïve) fixpoint or use recursive
  CTEs; the priority is the common **non-recursive** case above.
- Interaction with Part 1: chained inference should compile transitively too
  (inline the sub-rule's compiled queryset), but correctness via the fixpoint is
  acceptable first — Part 2 optimises the same semantics.

## Acceptance criteria (Part 2)

- Add a benchmark (e.g. `test_project/`) that seeds N∈{1k,10k,100k} stored facts
  and asserts wall-clock budgets:
  - concrete-subject inferred query (`CanAccessVessel(user, Var)`) at 100k: well
    under ~100 ms.
  - all-variable enumeration completes and is O(result), not O(facts²).
- The ORM path handles inferred heads and concrete positions (the two bails above
  are gone or narrowed).
- Results are identical to the fixpoint path (cross-check the two on small data).
- `query(..., hydrate=False)` for a compiled query issues O(1) SQL round trips,
  not one-per-fact.

---

## How to work this

1. Read `README.md` and the top of `CHANGELOG.md`; use the `Makefile`.
2. Part 1: add the failing reproduction test(s), fix, `make check`, update
   `CHANGELOG.md`.
3. Part 2: add the benchmark, implement ORM compilation behind the same public
   API, keep Part 1 tests green, `make check`, update `CHANGELOG.md`.
4. Cut a release (0.4.2 for Part 1, 0.5.0 for Part 2 given the new query surface).
