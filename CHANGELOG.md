# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.2] - 2026-08-05

### 🐛 Fixes
- **`Var(where=Q(...))` in a rule body is now enforced at join time** (GitHub #1). The constraint was applied only when loading stored facts, never during unification. Rules that derive the same head share one fact base, so a row admitted by one rule's load-time filter reached another rule's join and derived a fact that violates its own constraint. A literal `where` (a `Q` with no references to other variables) is now checked in `_unify_facts`; a `Q` that references another variable stays a cross-variable constraint, resolved by the query layer.

### 🚀 Performance
- **The conjunction engine solves the least-free condition first.** Each later condition reloads once per binding of the earlier ones (bound variables are filtered in Python, not pushed into the DB), so a broad condition written before a selective one made the selective relation reload once per broad row. The engine now picks the condition with the fewest open positions at each step: a fixed position (concrete, or a variable already bound) counts 0, a free variable 1.0, a free variable with a literal `where` 0.5. `AND` is commutative, so results are unchanged. On a broad-by-selective join at N=10,000 this holds the query count flat at 4 instead of ~10,003.

### 📝 Docs
- Document narrowing a position by its related model: `where=Q(...)` on a position's `Var` filters that position by its model's fields and pushes into the SQL join.

## [0.6.1] - 2026-07-31

### 🚀 Features
- **N-ary relations — a fact can have more than two positions.** A `Fact` is no longer limited to `subject`/`object`. Declare any positions you need, and mix entity positions (a FK to a Django model) with value positions (a typed value, e.g. an enum member). Every position stays typed — use `Term[X]` so it accepts an `X` or a `Var[X]`:

  ```python
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

  Query, `store_facts`, `retract_facts`, `exists`/`first`, `as_queryset`, and rule bodies/heads all work over the fact's positions. A value position pins a filter (`Crew(Var[User]("u"), Rank.MASTER, Var[Vessel]("v"))`) and stays its value through hydration. An entity position hydrates to its model instance and accepts a `where` constraint. `as_queryset(..., on=<position>)` takes any position name.
- Binary facts (`subject`/`object`) are unchanged and keep all query optimizations. The goal-directed and ORM-conversion optimizers apply to binary relations. An N-ary relation uses the correct fixpoint evaluator.

## [0.6.0] - 2026-07-29

### 💥 Breaking / Changed
- **Explicit storage models — no more generated models.** A stored `Fact` no longer generates a `<Name>Storage` model in `__init_subclass__`. You declare the Django model yourself and bind it with `@store(<Fact>)`:

  ```python
  class WorksFor(Fact):
      subject: Term[Employee]
      object:  Term[Company]

  @store(WorksFor)
  class WorksForStorage(models.Model):
      subject = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="+")
      object  = models.ForeignKey(Company,  on_delete=models.CASCADE, related_name="+")
      class Meta:
          constraints = [models.UniqueConstraint(fields=["subject", "object"], name="worksfor_edge")]
  ```

  The storage tables now have a real model file, normal migrations, and you control their columns, indexes and constraints (which is what enables optimizer columns/indexes). `@store(<Fact>, subject=…, object=…, where=…, readonly=…)` can map a fact onto an existing table's columns.
- **`inferred=True` is gone.** A fact is *inferred* precisely when it has no `@store` binding — so `class ColleaguesOf(Fact, inferred=True)` becomes just `class ColleaguesOf(Fact)`. A rule head must be an inferred (unbound) fact.
- Removed: the model generator, the abstract `FactModel`, and the `unique=` / `Unique` API (constraints live on your model's `Meta` now). A stored fact used before it is bound, or written when `readonly`, raises a clear error.
- **Migrating** off the generated models: declare one explicit storage model per stored fact and bind it with `@store` (see the README). Each is a mechanical `subject`/`object` `ForeignKey` pair matching the fact's annotated types — a coding agent/LLM can generate them straight from your fact definitions.

## [0.5.3] - 2026-07-29

### 🚀 Features
- **Per-fact uniqueness via `unique=`**: a stored `Fact` can declare its storage uniqueness constraint — `class Owns(Fact, unique=Unique.OBJECT)`. `Unique.TOGETHER` (default) keeps the `(subject, object)` pair unique (a plain edge); `Unique.SUBJECT` / `Unique.OBJECT` make that single position unique, so each subject/object appears at most once (e.g. `OBJECT` enforces a single owner per owned thing at the database level). Exported as `django_datalog.models.Unique`.

## [0.5.2] - 2026-07-29

### 🚀 Features
- **`exists` / `first` (+ async `aexists` / `afirst`)**: single-result query entry points — `if exists(CanAccessVessel(user, vessel)): ...` for access checks, `first(WorksFor(alice, Var("company")))` for "give me one". They genuinely short-circuit: inferred-fact derivation stops at the first match rather than computing the whole extension (a bound access check over a realistic neighbourhood is ~0.6 ms; deriving the full set would be O(neighbourhood)). `exists` skips hydration; `first` hydrates only the one result it keeps.

### ⚡ Performance
- **Streaming (lazy) evaluation**: rule-body joins and inferred-fact derivation now stream their results instead of materializing the full set, so `query(..., hydrate=False)` and the new `exists`/`first` stop deriving as soon as the consumer stops. Recursive relations still use the eager fixpoint (a closure can't short-circuit); results are unchanged.

## [0.5.1] - 2026-07-29

### 🐛 Bug Fixes
- **`Fact` `&`/`|` operators type-accept heterogeneous fact types**: the operator annotations used `Self`, so a type checker rejected composing different fact types — the primary use of rule bodies (`MemberOf(u, c) & Owns(c, v)` raised `Unsupported operand types for &`). They now accept any `Fact`, matching the runtime, so mixed-type rule bodies like `StaffOf(...) | (MemberOf(...) & Owns(...))` type-check without `# type: ignore[operator]`.

## [0.5.0] - 2026-07-27

### 🚀 Features
- **Composable querysets**: `as_queryset(pattern, on="object", model=None)` (and async `aas_queryset`) resolve an inferred query and return a lazy `Model.objects.filter(pk__in=…)` the caller can compose with the ORM — e.g. `as_queryset(CanAccessVessel(user, Var("v"))).filter(active=True)`. The target model is inferred from the fact's annotation when omitted.

### ⚡ Performance
- **Set-based fixpoint dedup**: `apply_rules`/`apply_targeted_rules` now track derived facts in a set instead of `x not in list`, removing the O(M²) dedup. ~30–66× on inference-heavy queries on its own.
- **Goal-directed rule specialization**: a bound inferred query (e.g. `Colleague(alice, Var)`) now binds each non-recursive rule's head to the query's concrete positions before evaluation, so only the answer rows are derived instead of the whole relation over the subject's neighbourhood. A single-subject query over 2000 co-workers at one company went from 27 s (O(neighbourhood²)) to 0.04 s (linear). Recursive relations stay generic (specializing a recursive base case is unsound).
- **Bound-argument pushdown (sideways information passing)**: when a query pins a position (e.g. `Colleague(alice, Var)`), concrete/bound values are pushed into the DB filters and join-variable values gathered from one condition constrain the next (`pk__in`), including through chained inferred bodies. Concrete-subject and chained-concrete inferred queries become O(neighbourhood) instead of O(all-facts): a per-user access check that took >45 s on ~100k facts now runs in **~2 ms** (flat in N). Pushdown is disabled for recursive rules (unsound there). Results are unchanged — the fixpoint and pushed-down paths agree.
- **Hash-joined rule bodies**: rule-body conditions are joined left-to-right with a hash join on their shared variables instead of a recomputed nested-loop product, so all-variable enumeration and recursive rules over large data are O(result) rather than O(facts^N). Enumerating 100k inferred pairs went from not-completing to ~1 s.
- **Semi-naïve fixpoint**: rule evaluation now joins each round against only the previous round's newly-derived facts (the delta) instead of re-deriving the whole extension every iteration. Deep transitive closures are dramatically faster (depth-100 closure ~1.2 s → ~30 ms).

### 🐛 Bug Fixes
- **Deep recursion is no longer silently truncated**: the fixpoint had a hard `max_iterations = 100` cap, so a transitive closure deeper than 100 returned an incomplete result. The semi-naïve fixpoint terminates when no new facts are derived (the domain is finite), removing the cap — closures of any depth now compute to completion.

### 🐛 Bug Fixes
- **Chained inference now resolves through inferred rule bodies**: a rule whose body referenced another *inferred* fact previously returned an empty result because the intermediate level was never materialized. Body-condition resolution is now transitive — inferred conditions are resolved recursively (stored facts + their own rules) — so inference chains to any depth. Recursive rules still terminate (a condition of a type currently being resolved is left to the fixpoint), and each inferred type's extension is memoized per query.

## [0.4.1] - 2026-07-22

### 🚀 Features
- **Async interface**: `aquery`, `astore_facts`, and `aretract_facts` — async counterparts of the sync API for use from async views/tasks. They wrap the engine with `asgiref.sync.sync_to_async` (thread-sensitive) so the ORM connection context is shared; `aquery` awaits and returns a list.

## [0.4.0] - 2026-07-21

### 🎯 Type Safety
- **Parametric `Var`**: `Var` is now generic — `Var[Employee]("emp")` records the model a variable stands for, so a type checker rejects a variable used in a mismatched fact slot (e.g. an `Employee` variable in a `Company` position). Create a variable once and reuse it across a rule/query to keep its binding type-consistent.
- **`Term[X]` alias**: shorthand for `X | Var[X]`, used in fact field annotations (`subject: Term[Employee]`) so the model name isn't repeated.
- **Static enforcement**: `Fact` is decorated with `@dataclass_transform`, so type checkers synthesize a typed `__init__` for every fact subclass and check `Var`/instance arguments against each slot.
- **Backward compatible**: bare `Var("emp")` still works (inferred from the slot it fills); the type parameter is entirely opt-in.

### 🔧 Changed
- **Requires Django >= 5.2.16** (pinned to the 5.2 LTS series).

### 🚀 Major Features
- **Cross-Variable Constraints & Advanced Query Optimization**: Complete query analysis system
- **Cross-Variable References**: Variables can reference other variables in Q constraints (`Var("project", where=Q(company=Var("company")))`)
- **AST-Based Analysis**: Converts queries into abstract syntax trees for sophisticated optimization
- **Automatic ORM Generation**: Builds complex Django ORM queries with EXISTS subqueries automatically
- **Performance**: Up to 75% query reduction (16→4 queries) for complex relational patterns
- **Security**: 100% Django ORM - eliminates all SQL injection vulnerabilities
- **Zero Configuration**: Works transparently - existing code gets better performance automatically
- **CLI Tools**: New `convert_to_orm` management command for query analysis and optimization insights
- **Simplified Architecture**: Streamlined optimizer focuses on constraint propagation, advanced analysis handles optimization

## [0.3.1] - 2025-07-23

### 🐛 Bug Fixes
- **Code Cleanup**: Remove debug print statements from optimizer.py:70-71

## [0.3.0] - 2025-07-22

### 🚀 Major Features Added

#### **Fact Operators**
- **New `|` (OR) and `&` (AND) operators** for Facts to create intuitive rule expressions
- `Fact1 | Fact2` creates `[Fact1, Fact2]` (disjunction)  
- `Fact1 & Fact2` creates `(Fact1, Fact2)` (conjunction)
- Support for complex expressions like `(Fact1 & Fact2) | Fact3`

#### **Enhanced Rule System**
- **Disjunctive Rules**: Rules now support OR alternatives using list syntax
- **Modern Syntax**: Updated rule processing with match-case pattern matching
- **FactConjunction**: New tuple subclass for better type safety
- **Future Annotations**: Full support for `from __future__ import annotations`

#### **Rule Context Management**
- **Dual-mode `rule_context`**: Works as both context manager and decorator
- Context Manager: `with rule_context(): ...`
- Decorator: `@rule_context` for test methods
- **Perfect Test Isolation**: Rules defined in context don't leak to other tests

#### **Inferred Facts**
- **`inferred=True` parameter**: Facts computed exclusively via rules without Django model storage
- **No Database Storage**: Inferred facts exist only as computed conclusions
- **Always Up-to-Date**: Recomputed on every query to reflect current rule logic
- **Zero Migrations**: No Django models or database tables created

### 🛠️ Technical Improvements
- **Validation**: Rules now validate that inferred facts can only be rule heads
- **Error Handling**: Better TypeErrors for invalid operator combinations
- **Test Suite**: 60+ tests with comprehensive coverage of new features
- **Performance**: Optimized rule processing with modern Python features

### 📚 Documentation
- **Compact README**: Streamlined documentation focusing on core concepts
- **Modern Examples**: All examples use new operator syntax
- **Complete Migration Guide**: Shows both new and legacy syntax

### 🔄 Breaking Changes
- **Removed vessel-related tests**: Simplified test suite
- **Updated rule signature**: Enhanced to support new syntax patterns

### 💡 Usage Examples
```python
# Inferred facts - no database storage
class HasAccess(Fact, inferred=True):
    subject: User | Var
    object: Resource | Var

# Modern operator syntax (recommended)
rule(
    HasAccess(Var("user"), Var("resource")),
    IsOwner(Var("user"), Var("resource")) | 
    IsManager(Var("user"), Var("resource")) |
    (MemberOf(Var("user"), Var("team")) & TeamOwns(Var("team"), Var("resource")))
)

# Rule context for testing
@rule_context
def test_access_control(self):
    rule(CanEdit(Var("user")), IsAdmin(Var("user")))
    results = query(CanEdit(admin_user))
    assert len(results) == 1
```

## [0.2.0] - 2025-01-21

### Added
- **Context-local rules**: New `rule_context()` context manager for temporary rules that are only active within a specific scope
- **Intelligent Query Optimizer**: Automatic constraint propagation and selectivity-aware query planning
- **Adaptive Query Planning**: Query planner learns from actual execution times to improve future optimization decisions
- **Timing-Based Optimization**: Context manager `time_fact_execution()` for automatic query timing and feedback
- **Constraint Propagation**: Variables with the same name automatically share constraints across predicates
- **Query Planning**: Automatic reordering of query execution based on constraint selectivity and historical performance
- Support for scoped rule definitions that don't pollute the global rule registry
- Nested rule contexts with proper isolation between context levels

### Features
- `rule_context()` context manager allows rules to be defined that are only active within the context
- Rules can be passed as arguments to `rule_context()` or defined inside the context block
- Context manager properly restores original global rules when exiting
- **Automatic Constraint Propagation**: When multiple predicates use the same variable name, constraints are automatically merged using logical AND
- **Selectivity-Based Planning**: Query execution is automatically ordered to execute most selective constraints first  
- **Adaptive Learning**: Query planner learns from actual execution times and uses them to optimize future queries
- **Pattern-Specific Tracking**: Different constraint patterns are tracked separately for precise optimization
- **Performance Monitoring**: Built-in timing statistics with `get_optimizer_timing_stats()`
- **Caching**: Query selectivity estimates are cached with smart invalidation when new timing data arrives
- Full support for variable constraints and complex rule logic within contexts

### Performance
- **Adaptive Performance**: Query execution gets faster over time as the planner learns from historical data
- **Massive Query Speedups**: Intelligent query planning can improve performance by orders of magnitude
- **Reduced Database Load**: Constraint propagation eliminates unnecessary database queries
- **Smart Execution Order**: Most selective and fastest patterns execute first, minimizing query time
- **No Row Counting Overhead**: Removed expensive database estimation calls in favor of timing-based optimization
- **Memory-Safe Design**: Bounded data structures prevent memory leaks in production environments

### Memory Optimizations
- **Bounded Timing Data**: Execution times use bounded deques (max 100 samples per pattern) to prevent unbounded growth
- **LRU Cache Eviction**: Selectivity cache uses LRU eviction with configurable size limits (default 500 entries)
- **Automatic Cleanup**: No manual cleanup required - data structures self-manage memory usage
- **Production Ready**: Eliminates memory leaks that could cause gradual memory exhaustion
- **Removed PerformanceTracker**: Simplified architecture by removing redundant performance tracking system
- **Eliminated Global Fact Loading**: Replaced inefficient `_get_all_facts_with_inference()` with targeted fact loading
- **Query-Driven Loading**: Only loads facts relevant to specific query patterns, achieving 62% reduction in database queries
- **Hidden Variable Optimization**: Introduced UUID-based hidden variables for rule processing, eliminating bulk loading operations

### Code Quality
- **Eliminated Inline Imports**: Moved all function-level imports to module level for better code organization
- **Resolved Circular Dependencies**: Created separate `variables.py` module to break circular import dependencies
- **Improved Module Structure**: Clean separation between variables, optimizer, query, and rules modules

## [0.1.0] - 2025-01-21

Initial release of django-datalog - a complete datalog inference engine for Django applications.

### Added
- Django Datalog engine with fact-based data modeling
- Logic programming with inference rules using Python syntax
- Query system with variable binding and constraint support
- Q object integration for filtering query results
- Performance optimizations including query reordering and batch hydration
- Modular architecture with separate facts, query, and rules modules
- Comprehensive test suite with family relationship examples
- Conditional test model loading for package testing
- Support for both hydrated objects and PK-only queries

### Features
- **Fact Definition**: Define facts as Python dataclasses with Django model integration
- **Inference Rules**: Write rules to derive new facts from existing ones
- **Query Engine**: Query facts with variable binding and automatic inference
- **Django Q Objects**: Use Django's Q objects to add constraints to query variables
- **Performance**: Intelligent query planning and batch operations
- **Testing**: Built-in test framework with example models and facts

### Performance
- Query reordering based on selectivity and variable constraints
- Batch hydration of model instances to reduce database queries
- PK-only query mode for improved performance when full objects aren't needed
- Cached model type metadata to avoid runtime type introspection

### Technical
- Modular package structure separating facts, queries, and rules
- Automatic Django model generation from fact definitions
- Django app integration with proper migrations and settings
- Type hints throughout with support for Union types (Model | Var)
- Comprehensive error handling and validation

[0.1.0]: https://github.com/edelvalle/django-datalog/releases/tag/v0.1.0
