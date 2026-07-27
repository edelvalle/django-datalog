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

## STATUS: RESOLVED (goal-directed rule specialization)

The single-subject blow-up is fixed on the current branch. The Kaiko
reproduction (`test_perf_single_subject.py`) now scales linearly:

| N co-workers | before | after |
|---|---|---|
| 250  | 0.44 s | 0.007 s |
| 500  | 1.57 s | 0.013 s |
| 1000 | 6.75 s | 0.024 s |
| 2000 | 26.9 s | 0.038 s |

Two clarifications on the analysis below (which was profiled on an **older
build**):
- The `rules.py:213 _apply_single_rule` list-dedup in the stack dump had
  already been replaced by a set-based dedup (and then a semi-naïve fixpoint);
  that function no longer exists on this branch. So the "kill the O(n²) dedup"
  fix was already in — and was *not* what still made this slow.
- The real remaining cost was that a *bound* query still derived the **whole
  relation over the neighbourhood** and filtered afterwards (O(neighbourhood²)),
  because rule *derivation* was generic. The "secondary contributor" note below
  (conjunctive bodies loading full extensions) was the right scent.

Fix: `_specialize_rule` (query.py) binds a non-recursive rule's head to the
query's concrete positions before evaluation, so only the answer rows are
derived — O(answer). Recursive relations stay generic (specializing a recursive
base case is unsound); goal-directed recursion remains future work. The
reproduction is now a passing regression guard. Remaining: structural ORM
compilation for the all-variable enumeration path.

--- original analysis (older build) below ---

This reproduced on an earlier build — the semi-naïve fixpoint and `as_queryset`
did not fix it on their own, because the hot path was rule application, not the
parts those changes touched.

## Symptom (measured)

On a ~13k-fact production-shaped dataset (`StaffOf`≈9.9k, `MemberOf`≈2.1k,
`Owns`≈1.5k), a single-user `CanAccessVessel(user, Var("v"))`:

- heaviest user (1458-row answer): **did not return in 5 min**;
- a user whose answer is a **single row**: **did not return in 70 s**.

The cost tracks the *fact base and the derived-set size*, not the answer size —
a one-row answer is as slow as the heaviest.

Runnable reproduction (SQLite, no external DB):
`test_project/testdjdatalog/test_perf_single_subject.py`. `Colleague` over N
co-workers derives ~N facts; time is quadratic in N:

| N (≈derived facts) | time | ms/row |
|---|---|---|
| 250  | 0.42 s | 1.69 |
| 500  | 1.57 s | 3.14 |
| 1000 | 6.75 s | 6.75 |
| 2000 | 26.9 s | 13.47 |

Every doubling ≈ 4× the time. The test's final assertion (2× facts should be
~2× time) currently **fails** — that is the target.

## Root cause (profiled, with `file:line`)

A `faulthandler` stack dump of the hanging query is pinned, every sample, at the
same place:

```
rules.py:213  _apply_single_rule        # <-- here
rules.py:190  apply_targeted_rules
query.py:186  _apply_rules_with_hidden_variables
query.py:142  _get_facts_for_pattern
query.py:116  _satisfy_conjunction_with_targeted_facts
```

`rules.py:213` is:

```python
if new_fact and new_fact not in known_facts and new_fact not in new_facts:
```

`known_facts` and `new_facts` are **lists**, so each `x not in …` is a linear
scan, and every element comparison runs the dataclass `__eq__` → model
`__eq__` → `UUID.__eq__`. Deriving K facts is therefore
O(K · (base + K)) comparisons with a heavy per-comparison constant — quadratic,
which is exactly the curve above. `apply_targeted_rules` (`rules.py:168`) re-runs
this each fixpoint iteration.

Secondary contributor: `_find_all_bindings` (`rules.py:222`) resolves each body
condition independently and merges, so a conjunctive body like
`MemberOf(u,c) & Owns(c,v)` loads the *full* `Owns` extension rather than the
slice joined to `u`'s companies, inflating K before the dedup even runs.

Separately, the fast ORM path never engages for these queries:
`_try_automatic_orm_conversion` (`query.py:614`) bails for (a) inferred facts
(`query.py:627`) and (b) any concrete position (`query.py:633`) — and a per-user
check is both — so everything falls to the fixpoint above.

## Fix direction

**First, the cheap high-impact fix — kill the O(n²) dedup** (turns the curve above
near-linear on its own, no API change):

- Deduplicate derived facts with a **set/dict** keyed by
  `(type(fact), subject_pk, object_pk)` instead of `list.__contains__`
  (`rules.py:213`, and the `all_facts`/`new_facts` accumulation in
  `apply_rules`/`apply_targeted_rules`).
- Make facts **hashable/equal by that key** so comparisons are hash/identity, not
  a recursive `UUID.__eq__` on model instances (compare `subject_id`/`object_id`,
  never load or compare model objects during inference).
- Propagate bound variables in `_find_all_bindings` (`rules.py:222`) so a
  conjunctive body loads only the joined slice, not each condition's full
  extension — shrinks K.

**Then, the structural fix — compile inferred-fact queries to Django ORM** instead
of a Python fixpoint (needed for the all-variable enumeration and to make this a
real runtime read path):

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

- `test_project/testdjdatalog/test_perf_single_subject.py` passes: doubling the
  derived-set size roughly doubles the time (linear), not quadruples it.
- The dedup no longer compares model instances / UUIDs during inference (guard by
  the scaling test above; optionally assert no extra SQL from `__eq__`).
- A single-user concrete-subject query on ~100k stored facts returns well under
  ~100 ms; the all-variable enumeration is O(result), not O(facts²).
- The ORM path handles inferred heads and concrete positions (the two bails at
  `query.py:627,633` are gone or narrowed).
- Results are identical to the pre-fix fixpoint path (cross-check on small data);
  existing tests and the Part 1 chained-inference tests stay green.

---

## How to work this

1. Read `README.md` and the top of `CHANGELOG.md`; use the `Makefile`.
2. Part 1: add the failing reproduction test(s), fix, `make check`, update
   `CHANGELOG.md`.
3. Part 2: add the benchmark, implement ORM compilation behind the same public
   API, keep Part 1 tests green, `make check`, update `CHANGELOG.md`.
4. Cut a release (0.4.2 for Part 1, 0.5.0 for Part 2 given the new query surface).
