# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
