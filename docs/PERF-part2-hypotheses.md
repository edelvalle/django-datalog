# Part 2 performance — diagnosis, baseline, and hypotheses

Status: working notes for django-datalog Part 2 (query performance), 2026-07-27.
Part 1 (chained inference correctness) is done and released-pending as 0.4.2.
Companion brief: `docs/PLAN-chained-inference-and-performance.md`.

Priority: correctness first (Part 1, done); this doc plans the performance work.
Everything below must return **identical results to the current fixpoint** and
keep the Part 1 chain tests green.

---

## Baseline (measured)

Harness: `test_project/benchmarks/bench_chained.py`, `make benchmark`.
Shape: `PersonWorksFor(Person, Company)` stored; `Colleague(p1,p2) :=
PersonWorksFor(p1,c) & PersonWorksFor(p2,c)` (AND self-join); `InNetwork :=
Colleague` (chain); `Ancestor := ParentOf | (ParentOf & Ancestor)` (recursive).
`fan_out=10` people/company.

| query | N=250 | N=500 | N=1000 |
|---|--:|--:|--:|
| stored `PersonWorksFor(Var,Var)` | 7 ms | 9 ms | 17 ms |
| concrete-subj `Colleague(alice,Var)` — 10 results | 3,629 ms | 14,022 ms | ~50 s+ (timeout) |
| all-var `Colleague(Var,Var)` | 3,625 ms | 14,736 ms | — |
| chained `InNetwork(alice,Var)` — 10 results | 7,896 ms | 31,853 ms | — |
| recursive `Ancestor(root,Var)` (depth 12) | 22 ms | 18 ms | — |

### What the numbers prove
1. **Cost tracks total data, not result size** — `Colleague(alice,Var)` returns
   10 rows but grows 3.6s→14s→~50s with N. Reproduces the downstream
   "273 results, >45 s" symptom.
2. **~O(N²)** — 2× data ≈ 4× time.
3. **Compute-bound, not DB-bound** — every query issues only **3–4 SQL**
   statements; the time is Python.
4. **Chaining compounds** — `InNetwork` (level 2) ≈ 2× `Colleague`.
5. **Stored path and small recursive fixpoint are already fine.**

---

## Root cause (verified, by symbol)

- **No sideways-information-passing (bound-arg pushdown).** A concrete head arg
  (`alice`) is not propagated into body-condition loading. `_create_targeted_condition`
  (`query.py`) keeps only body vars that appear *by name* in the target pattern;
  a concrete value is not a named var, so the body condition is loaded in full
  (`_load_stored_facts_for_pattern` → `SELECT ... FROM storage` with **no**
  `WHERE subject_id=…`, confirmed via captured SQL) and filtered in Python after.
- **Python nested-loop joins** over full relations — `_find_all_bindings`
  (`rules.py:222`), `_find_bindings_for_condition` (`rules.py:253`),
  `_query_against_facts` (`query.py`). O(∏ |relation|).
- **Quadratic dedup** — the fixpoint does `new_fact not in all_facts` against a
  *list* (`rules.py:161` in `apply_rules`, `rules.py:192` in
  `apply_targeted_rules`), i.e. O(M²) in the number of derived facts.
- **Fast ORM path bails** for exactly these queries — `_try_automatic_orm_conversion`
  (`query.py`) raises `NotImplementedError` for inferred facts and for any
  concrete subject/object position. (The concrete-position bail was added
  deliberately in Part-1 era for correctness; Part 2 should replace it with real
  ORM handling, not just remove it.)

---

## Results so far (H0 + H1 done)

`fan_out=10`, concrete-subject `Colleague(alice,Var)` returning 10 rows:

| N | baseline | H0 (set dedup) | H1 (pushdown) |
|--:|--:|--:|--:|
| 500 | 14,022 ms | 463 ms | ~2 ms |
| 1,000 | ~50 s+ | 1,697 ms | 2.8 ms |
| 10,000 | — | — | 2.0 ms |
| 100,000 | — | — | **1.8 ms** |

Chained `InNetwork(alice,Var)` at 100k: **2.2 ms** (H1b pushes the binding through
the inferred body too). Both are **flat in N** — well under the brief's
"<100 ms @ 100k" target. Correctness: full suite (95) + chain tests green;
pushdown disabled for recursive rules (unsound); all-var enumeration unchanged.

All-variable enumeration (`Colleague(Var,Var)`) after **H3** (hash join):
10k pairs 142 ms, 100k pairs ~1.07 s (was: did not complete), 500k pairs ~5.6 s
— ~11 µs/pair, i.e. O(result). Concrete/chained stay ~2 ms.

**Still open:** **H2** (compile non-recursive rules to a composable Django
queryset / `compile()` / `as_queryset=` — the 0.5.0 read-path API, and pushes
enumeration/joins into SQL); **H4** semi-naïve fixpoint for deep recursion;
**H5** column pushdown / `hydrate=False` fast path; **H6** cross-query
memoization / materialization.

## Hypotheses (test against the baseline)

### H0 — Set-based dedup (near-free quick win)   ✅ DONE
### H1 — Bound-argument pushdown (magic sets / SIP)   ✅ DONE (incl. H1b through inferred bodies)
### H3 — Hash-indexed in-memory joins   ✅ DONE (all-var / large joins now O(result))

(original hypothesis notes below, kept for the remaining items)

### H0 — Set-based dedup (near-free quick win)
Replace list-membership dedup in `apply_rules`/`apply_targeted_rules` with a set
keyed on the fact's hash (facts are already hashable by type+pks). Turns O(M²)
into O(M). *Low risk, no semantic change.* Expect: big drop on the all-var and
chained cases immediately. Measure first — it may move the needle a lot alone.

### H1 — Bound-argument pushdown (magic sets / SIP)  ← highest leverage
Propagate concrete + already-bound positions from the query/head into body
DB filters: `Colleague(alice,Var)` should load
`PersonWorksForStorage.filter(subject_id=alice)` (1 row), not all rows. For joins
thread the join var left→right (`subject_id__in=<prev results>`). Applies to
recursive AND non-recursive. Moderate complexity: carry the head→body substitution
into base-building and push it through `_fact_to_django_query`.
Measure: rows scanned + wall-clock vs N; concrete-subject must become ~O(result).

### H2 — Full ORM compilation of non-recursive rules  ← strategic endgame
Compile a rule tree into one queryset: OR→`Q|Q`, AND→joins/EXISTS/`__in`,
chained inference→inline the sub-rule's compiled queryset, concrete positions→
`.filter()`. Expose a lazy queryset/`Q` via a new `compile()`/`as_queryset=`
entry point so callers get a composable JOIN (the real downstream read-path
blocker). Highest complexity; non-recursive only. Measure: 1 round trip,
O(result), and `hydrate=False` issues O(1) SQL.

### H3 — Hash-indexed in-memory joins
For paths that must stay in Python (recursive rules, or before H1/H2), index the
fact base in dicts keyed on the join key instead of linear scans in
`_find_bindings_for_condition` / `_query_against_facts` → O(|A|+|out|).
Low complexity, no DB changes.

### H4 — Semi-naïve fixpoint
`apply_targeted_rules` re-applies every rule over ALL facts each iteration. Join
only against the last round's delta. Targets recursive/transitive-closure cost.

### H5 — Constraint & column pushdown
Push `Var(where=Q(...))` and bound positions to the DB; use `.values()` /
`hydrate=False` to avoid pulling full rows + `select_related` when only PKs are
needed. Complements H1.

### H6 — Cross-query memoization / optional materialization
Cache inferred extensions across queries (process/request scope, invalidated on
`store_facts`/`retract_facts`), or a `materialize()` that persists derived facts
for read-heavy use. Orthogonal; risk is invalidation correctness.

---

## Suggested order
1. **H0** — measure the free win first (set dedup).
2. **H1** — the broad, high-leverage lever; unblocks the concrete-subject read path.
3. **H3 + H4** — make the residual Python path (recursive rules) usable.
4. **H2** — composable-queryset endgame, built on H1's pushdown mechanics.
5. H5 folds into H1/H2; H6 is a separate lever for read-heavy workloads.

## Guardrails
- Every optimized path cross-checks results against the current fixpoint on small
  data (identical sets).
- Part 1 chain tests (`test_chained_inference.py`) stay green.
- Add wall-clock/row-scanned assertions to the benchmark as budgets land
  (target from brief: concrete-subject inferred < ~100 ms at 100k).

## Release
Part 2 → 0.5.0 (new query surface / `compile()` entry point), per the brief.
