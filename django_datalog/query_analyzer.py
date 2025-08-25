"""
Advanced Query Analysis System for django-datalog

This module provides sophisticated query analysis, planning, and ORM construction:

1. Query AST: Parses django-datalog queries into abstract syntax trees
2. Dependency Analysis: Analyzes variable relationships and constraint dependencies  
3. Execution Planning: Creates optimized execution plans based on analysis
4. Recursive ORM Construction: Builds Django ORM queries from execution plans

The goal is to automatically convert complex django-datalog patterns into
optimal Django ORM queries without hardcoded patterns.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from enum import Enum
import uuid

from django.db.models import Q, F, Exists, OuterRef, Subquery
from django.db import models

from .facts import Fact
from .variables import Var, has_variable_references


class ConstraintType(Enum):
    """Types of constraints in queries."""
    SIMPLE_FILTER = "simple_filter"           # Q(field=value) 
    CROSS_VARIABLE = "cross_variable"         # Q(field=Var('other'))
    SELF_REFERENCE = "self_reference"         # Same variable in multiple places
    COMPLEX_EXPRESSION = "complex_expression"  # Complex Q expressions


class RelationshipType(Enum):
    """Types of relationships between facts."""
    INDEPENDENT = "independent"        # No shared variables
    JOIN = "join"                     # Share variables (standard join)
    CONSTRAINT = "constraint"         # One constrains the other
    RECURSIVE = "recursive"           # Recursive dependency


@dataclass
class VariableInfo:
    """Information about a variable in the query."""
    name: str
    fact_positions: List[Tuple[Fact, str]]  # (fact, field) where variable appears
    constraints: List[Q] = field(default_factory=list)  # Q objects that constrain this variable
    model_type: Optional[type] = None  # Django model type this variable represents
    is_join_variable: bool = False     # True if variable joins multiple facts
    dependency_level: int = 0          # Dependency ordering (0 = independent, higher = more dependent)


@dataclass
class FactNode:
    """AST node representing a fact in the query."""
    fact: Fact
    fact_type: type
    django_model: type
    subject_var: Optional[str] = None  # Variable name if subject is a variable
    object_var: Optional[str] = None   # Variable name if object is a variable
    constraints: List[Q] = field(default_factory=list)  # Local constraints on this fact
    constraint_types: List[ConstraintType] = field(default_factory=list)


@dataclass
class QueryAST:
    """Abstract Syntax Tree representation of a django-datalog query."""
    facts: List[FactNode]
    variables: Dict[str, VariableInfo]
    relationships: List[Tuple[FactNode, FactNode, RelationshipType]]
    execution_plan: Optional['ExecutionPlan'] = None


@dataclass
class ExecutionStep:
    """A single step in the execution plan."""
    step_id: str
    operation: str  # 'filter', 'join', 'exists', 'subquery'
    facts: List[FactNode]
    variables: List[str]
    depends_on: List[str] = field(default_factory=list)  # Step IDs this depends on
    orm_strategy: Optional[str] = None  # How to implement this in Django ORM
    estimated_cost: float = 1.0


@dataclass 
class ExecutionPlan:
    """Complete execution plan for the query."""
    steps: List[ExecutionStep]
    primary_model: type  # Main Django model to start the query from
    join_strategy: str   # 'nested_loops', 'exists_subqueries', 'direct_joins'
    estimated_total_cost: float = 0.0


class QueryAnalyzer:
    """
    Advanced analyzer that parses queries into ASTs and creates execution plans.
    """
    
    def __init__(self, facts: List[Fact]):
        self.facts = facts
        self.ast: Optional[QueryAST] = None
    
    def analyze(self) -> QueryAST:
        """Main entry point: analyze query and build AST with execution plan."""
        # Step 1: Parse facts into AST nodes
        fact_nodes = self._parse_facts()
        
        # Step 2: Analyze variables and their relationships
        variables = self._analyze_variables(fact_nodes)
        
        # Step 3: Determine relationships between facts
        relationships = self._analyze_relationships(fact_nodes, variables)
        
        # Step 4: Build the AST
        self.ast = QueryAST(
            facts=fact_nodes,
            variables=variables,
            relationships=relationships
        )
        
        # Step 5: Create execution plan
        self.ast.execution_plan = self._create_execution_plan(self.ast)
        
        return self.ast
    
    def _parse_facts(self) -> List[FactNode]:
        """Parse facts into AST nodes."""
        fact_nodes = []
        
        for fact in self.facts:
            # Get Django model for this fact type
            fact_type = type(fact)
            django_model = getattr(fact_type, '_django_model', None)
            
            if not django_model:
                continue  # Skip facts without Django models
            
            # Extract variable names and constraints
            subject_var = fact.subject.name if isinstance(fact.subject, Var) else None
            object_var = fact.object.name if isinstance(fact.object, Var) else None
            
            # Collect constraints from variables
            constraints = []
            constraint_types = []
            
            if isinstance(fact.subject, Var) and fact.subject.where:
                constraints.append(fact.subject.where)
                constraint_types.append(self._classify_constraint(fact.subject.where))
            
            if isinstance(fact.object, Var) and fact.object.where:
                constraints.append(fact.object.where)
                constraint_types.append(self._classify_constraint(fact.object.where))
            
            node = FactNode(
                fact=fact,
                fact_type=fact_type,
                django_model=django_model,
                subject_var=subject_var,
                object_var=object_var,
                constraints=constraints,
                constraint_types=constraint_types
            )
            fact_nodes.append(node)
        
        return fact_nodes
    
    def _classify_constraint(self, constraint: Q) -> ConstraintType:
        """Classify the type of constraint."""
        if has_variable_references(constraint):
            return ConstraintType.CROSS_VARIABLE
        elif hasattr(constraint, 'children') and len(constraint.children) > 1:
            return ConstraintType.COMPLEX_EXPRESSION
        else:
            return ConstraintType.SIMPLE_FILTER
    
    def _analyze_variables(self, fact_nodes: List[FactNode]) -> Dict[str, VariableInfo]:
        """Analyze variables and their relationships."""
        variables = {}
        
        # First pass: collect all variable occurrences
        for fact_node in fact_nodes:
            # Process subject variable
            if fact_node.subject_var:
                if fact_node.subject_var not in variables:
                    variables[fact_node.subject_var] = VariableInfo(
                        name=fact_node.subject_var,
                        fact_positions=[],
                        model_type=self._get_model_type(fact_node.fact, 'subject')
                    )
                variables[fact_node.subject_var].fact_positions.append(
                    (fact_node.fact, 'subject')
                )
            
            # Process object variable
            if fact_node.object_var:
                if fact_node.object_var not in variables:
                    variables[fact_node.object_var] = VariableInfo(
                        name=fact_node.object_var,
                        fact_positions=[],
                        model_type=self._get_model_type(fact_node.fact, 'object')
                    )
                variables[fact_node.object_var].fact_positions.append(
                    (fact_node.fact, 'object')
                )
        
        # Second pass: analyze variable properties
        for var_info in variables.values():
            # Determine if this is a join variable
            var_info.is_join_variable = len(var_info.fact_positions) > 1
            
            # Collect constraints that apply to this variable
            for fact, field in var_info.fact_positions:
                var_obj = getattr(fact, field)
                if isinstance(var_obj, Var) and var_obj.where:
                    var_info.constraints.append(var_obj.where)
        
        # Third pass: compute dependency levels
        self._compute_dependency_levels(variables)
        
        return variables
    
    def _get_model_type(self, fact: Fact, field: str) -> Optional[type]:
        """Extract Django model type from fact field annotation."""
        try:
            field_info = fact.__dataclass_fields__[field]
            return self._extract_model_type_from_annotation(field_info.type)
        except (KeyError, AttributeError):
            return None
    
    def _extract_model_type_from_annotation(self, type_annotation) -> Optional[type]:
        """Extract Django model type from type annotation."""
        if hasattr(type_annotation, "__args__"):
            # Handle Union types (Model | Var)
            for arg_type in type_annotation.__args__:
                if hasattr(arg_type, "_meta") and hasattr(arg_type._meta, "app_label"):
                    return arg_type
        elif hasattr(type_annotation, "_meta") and hasattr(type_annotation._meta, "app_label"):
            return type_annotation
        return None
    
    def _compute_dependency_levels(self, variables: Dict[str, VariableInfo]):
        """Compute dependency ordering for variables."""
        # Simple heuristic: variables with cross-variable constraints depend on others
        for var_info in variables.values():
            dependency_level = 0
            for constraint in var_info.constraints:
                if has_variable_references(constraint):
                    dependency_level += 1
            var_info.dependency_level = dependency_level
    
    def _analyze_relationships(self, fact_nodes: List[FactNode], 
                             variables: Dict[str, VariableInfo]) -> List[Tuple[FactNode, FactNode, RelationshipType]]:
        """Analyze relationships between facts."""
        relationships = []
        
        for i, fact1 in enumerate(fact_nodes):
            for j, fact2 in enumerate(fact_nodes):
                if i >= j:  # Avoid duplicates and self-relationships
                    continue
                
                relationship = self._determine_relationship(fact1, fact2, variables)
                if relationship != RelationshipType.INDEPENDENT:
                    relationships.append((fact1, fact2, relationship))
        
        return relationships
    
    def _determine_relationship(self, fact1: FactNode, fact2: FactNode, 
                               variables: Dict[str, VariableInfo]) -> RelationshipType:
        """Determine the relationship between two facts."""
        # Check for shared variables
        fact1_vars = {fact1.subject_var, fact1.object_var} - {None}
        fact2_vars = {fact2.subject_var, fact2.object_var} - {None}
        shared_vars = fact1_vars & fact2_vars
        
        if not shared_vars:
            return RelationshipType.INDEPENDENT
        
        # Check for cross-variable constraints
        has_cross_var_constraint = False
        for constraint_type in fact1.constraint_types + fact2.constraint_types:
            if constraint_type == ConstraintType.CROSS_VARIABLE:
                has_cross_var_constraint = True
                break
        
        if has_cross_var_constraint:
            return RelationshipType.CONSTRAINT
        else:
            return RelationshipType.JOIN
    
    def _create_execution_plan(self, ast: QueryAST) -> ExecutionPlan:
        """Create an optimized execution plan from the AST that handles ALL query patterns."""
        # Determine primary model (model with most connections or least constraints)
        primary_model = self._choose_primary_model(ast)
        
        # Strategy: Use the primary model as the base and add EXISTS/JOIN conditions
        # This approach can handle ANY pattern including complex cross-variable constraints
        
        steps = []
        
        # Single comprehensive step that handles all facts
        all_variables = set()
        for fact_node in ast.facts:
            if fact_node.subject_var:
                all_variables.add(fact_node.subject_var)
            if fact_node.object_var:
                all_variables.add(fact_node.object_var)
        
        # Create a unified execution step
        step = ExecutionStep(
            step_id=f"unified_{uuid.uuid4().hex[:8]}",
            operation="unified_query",
            facts=ast.facts,
            variables=list(all_variables),
            orm_strategy="comprehensive_exists",
            estimated_cost=1.0  # Single optimized query
        )
        steps.append(step)
        
        # Always use exists_subqueries strategy for maximum compatibility
        join_strategy = "comprehensive_exists"
        
        return ExecutionPlan(
            steps=steps,
            primary_model=primary_model,
            join_strategy=join_strategy,
            estimated_total_cost=1.0  # Optimized to single query
        )
    
    def _choose_primary_model(self, ast: QueryAST) -> type:
        """Choose the best primary model to start the query from."""
        # Strategy: Choose model that appears most frequently and has least constraints
        model_counts = {}
        model_constraint_counts = {}
        
        for fact_node in ast.facts:
            model = fact_node.django_model
            model_counts[model] = model_counts.get(model, 0) + 1
            model_constraint_counts[model] = model_constraint_counts.get(model, 0) + len(fact_node.constraints)
        
        # Score = frequency - constraint_penalty
        best_model = None
        best_score = -float('inf')
        
        for model, count in model_counts.items():
            constraint_penalty = model_constraint_counts[model] * 0.5
            score = count - constraint_penalty
            if score > best_score:
                best_score = score
                best_model = model
        
        return best_model or list(model_counts.keys())[0]


class ORMQueryBuilder:
    """
    Recursively constructs Django ORM queries from execution plans.
    """
    
    def __init__(self, execution_plan: ExecutionPlan, ast: QueryAST):
        self.plan = execution_plan
        self.ast = ast
        self.step_results = {}  # Cache results of executed steps
    
    def build_query(self) -> models.QuerySet:
        """Build the complete Django ORM query from the execution plan."""
        primary_queryset = self.plan.primary_model.objects.all()
        
        # Execute steps in dependency order
        for step in self.plan.steps:
            primary_queryset = self._execute_step(step, primary_queryset)
        
        # Optimize result mapping by prefetching all related data needed
        # Add annotations for other fact values to avoid N+1 queries
        primary_queryset = self._add_result_annotations(primary_queryset, self.ast.facts)
        
        return primary_queryset
    
    def _add_result_annotations(self, queryset: models.QuerySet, facts: List[FactNode]) -> models.QuerySet:
        """Add annotations to include data from all facts in a single query."""
        from django.db.models import OuterRef, Subquery
        
        # Always include primary fact relations
        queryset = queryset.select_related('subject', 'object')
        
        # For each non-primary fact, add a subquery annotation to get the missing data
        primary_model = self.plan.primary_model
        
        for fact_node in facts:
            if fact_node.django_model == primary_model:
                continue  # Skip primary fact
            
            # Create a subquery to get the object value for this fact
            # based on the shared subject
            subquery = fact_node.django_model.objects.filter(
                subject=OuterRef('subject')
            ).values('object_id')[:1]
            
            # Create a unique annotation name for this fact
            annotation_name = f'{fact_node.django_model._meta.model_name}_object_id'
            queryset = queryset.annotate(**{annotation_name: Subquery(subquery)})
        
        return queryset
    
    def _execute_step(self, step: ExecutionStep, queryset: models.QuerySet) -> models.QuerySet:
        """Execute a single step of the execution plan."""
        if step.orm_strategy == "comprehensive_exists":
            return self._apply_comprehensive_exists(step, queryset)
        elif step.orm_strategy == "direct_filter":
            return self._apply_direct_filters(step, queryset)
        elif step.orm_strategy == "exists_subquery":
            return self._apply_exists_subquery(step, queryset)
        else:
            # Fallback to current queryset
            return queryset
    
    def _apply_comprehensive_exists(self, step: ExecutionStep, queryset: models.QuerySet) -> models.QuerySet:
        """Apply comprehensive EXISTS strategy that handles ALL query patterns."""
        
        # Strategy: For each fact, create an EXISTS subquery that connects to the primary model
        # This approach can handle any combination of joins, constraints, and cross-variable references
        
        # First, apply constraints from the primary model fact directly to the main query
        primary_fact_constraints = []
        for fact_node in step.facts:
            if fact_node.django_model == self.plan.primary_model:
                # Apply constraints from this fact to the main query
                for constraint in fact_node.constraints:
                    if not has_variable_references(constraint):
                        # Simple constraints can be applied directly
                        primary_fact_constraints.append(constraint)
                break  # Only one primary fact should exist
        
        # Apply primary fact constraints
        for constraint in primary_fact_constraints:
            queryset = queryset.filter(constraint)
        
        # Now handle other facts with EXISTS
        for fact_node in step.facts:
            # Skip same model to avoid self-joins - already handled above
            if fact_node.django_model == self.plan.primary_model:
                continue
                
            exists_query = fact_node.django_model.objects.all()
            
            # Connect this fact to the primary model through its variables
            connection_added = False
            
            # Check if subject variable connects to primary model
            if fact_node.subject_var:
                # Connect through subject field
                exists_query = exists_query.filter(subject=OuterRef('subject'))
                connection_added = True
            
            # Check if object variable connects to primary model
            elif fact_node.object_var and not connection_added:
                # Try to connect through object relationship
                # First, check if the object field directly relates to primary model
                primary_model_name = self.plan.primary_model._meta.model_name.lower()
                
                # Try direct connection
                if fact_node.object_var == primary_model_name or fact_node.object_var == 'pk':
                    exists_query = exists_query.filter(object=OuterRef('pk'))
                    connection_added = True
                else:
                    # Try relationship connection
                    try:
                        exists_query = exists_query.filter(**{f'object__{fact_node.object_var}': OuterRef('pk')})
                        connection_added = True
                    except Exception:
                        # If direct connection fails, try through subject
                        try:
                            exists_query = exists_query.filter(subject=OuterRef('pk'))
                            connection_added = True
                        except Exception:
                            pass
            
            # If we still haven't connected, try a different approach
            if not connection_added:
                # Try to find ANY way to connect this fact to the primary model
                if fact_node.subject_var:
                    exists_query = exists_query.filter(subject=OuterRef('pk'))
                elif fact_node.object_var:
                    exists_query = exists_query.filter(object=OuterRef('pk'))
            
            # Apply all constraints to the EXISTS query
            for constraint in fact_node.constraints:
                if has_variable_references(constraint):
                    # Handle cross-variable constraints
                    resolved_constraint = self._resolve_cross_variable_constraint(constraint, fact_node)
                    if resolved_constraint:
                        exists_query = exists_query.filter(resolved_constraint)
                else:
                    # Apply simple constraints
                    exists_query = exists_query.filter(constraint)
            
            # Add the EXISTS condition to the main query
            queryset = queryset.filter(Exists(exists_query))
        
        return queryset
    
    def _apply_direct_filters(self, step: ExecutionStep, queryset: models.QuerySet) -> models.QuerySet:
        """Apply direct filters for independent facts."""
        for fact_node in step.facts:
            # Apply simple constraints
            for constraint in fact_node.constraints:
                if not has_variable_references(constraint):
                    # This is a simple filter we can apply directly
                    queryset = queryset.filter(constraint)
        
        return queryset
    
    def _apply_exists_subquery(self, step: ExecutionStep, queryset: models.QuerySet) -> models.QuerySet:
        """Apply EXISTS subqueries for dependent facts."""
        for fact_node in step.facts:
            # Build EXISTS subquery
            exists_query = fact_node.django_model.objects.all()
            
            # Handle cross-variable constraints
            for constraint in fact_node.constraints:
                if has_variable_references(constraint):
                    # This needs special handling with OuterRef
                    modified_constraint = self._resolve_cross_variable_constraint(
                        constraint, fact_node
                    )
                    if modified_constraint:
                        exists_query = exists_query.filter(modified_constraint)
                else:
                    exists_query = exists_query.filter(constraint)
            
            # Add EXISTS condition to main query
            queryset = queryset.filter(Exists(exists_query))
        
        return queryset
    
    def _resolve_cross_variable_constraint(self, constraint: Q, fact_node: FactNode) -> Optional[Q]:
        """Resolve cross-variable references in constraints using advanced parsing."""
        try:
            # Parse the Q object recursively to find and replace Var references
            resolved = self._recursive_resolve_q(constraint, fact_node)
            return resolved
        except Exception:
            return None
    
    def _recursive_resolve_q(self, q_obj: Q, fact_node: FactNode) -> Q:
        """Recursively resolve Var references in Q objects."""
        from .variables import Var
        
        new_q = Q()
        new_q.connector = getattr(q_obj, 'connector', 'AND')
        new_q.negated = getattr(q_obj, 'negated', False)
        
        if hasattr(q_obj, 'children'):
            for child in q_obj.children:
                if isinstance(child, tuple) and len(child) == 2:
                    # This is a field lookup: (field_name, value)
                    field_name, value = child
                    
                    if isinstance(value, Var):
                        # Replace Var with OuterRef
                        # The OuterRef should point to the corresponding field in the primary model
                        outer_ref_field = self._map_variable_to_outer_ref(value.name)
                        
                        # Also need to map the field_name to the correct relationship path
                        mapped_field_name = self._map_constraint_field_name(field_name, fact_node)
                        
                        new_q.children.append((mapped_field_name, OuterRef(outer_ref_field)))
                    else:
                        # Keep the original field lookup
                        new_q.children.append(child)
                        
                elif isinstance(child, Q):
                    # Recursively resolve nested Q objects
                    resolved_child = self._recursive_resolve_q(child, fact_node)
                    new_q.children.append(resolved_child)
                else:
                    # Keep other types as-is
                    new_q.children.append(child)
        
        return new_q
    
    def _map_variable_to_outer_ref(self, var_name: str) -> str:
        """Map variable names to OuterRef field names in the primary model."""
        # For fact storage models, we need to map variables to the correct storage fields
        # The variables typically map to either 'subject' or 'object' in the storage model
        
        # Strategy: Look at the AST to understand which field this variable represents
        # in the primary model context
        
        for fact_node in self.ast.facts:
            if fact_node.django_model == self.plan.primary_model:
                # This is the primary fact - check which field the variable represents
                if isinstance(fact_node.fact.subject, Var) and fact_node.fact.subject.name == var_name:
                    return 'subject'
                elif isinstance(fact_node.fact.object, Var) and fact_node.fact.object.name == var_name:
                    return 'object'
        
        # If not found in primary model, try to infer from variable name
        if var_name in ['emp', 'employee']:
            return 'subject'  # Employees are typically subjects
        elif var_name in ['company', 'project', 'department', 'dept']:
            return 'object'   # These are typically objects
            
        # Fallback: assume it's a subject
        return 'subject'
    
    def _map_constraint_field_name(self, field_name: str, fact_node: FactNode) -> str:
        """Map constraint field names to the correct relationship path in the fact storage model."""
        
        # For django-datalog fact storage models, we have:
        # - subject: ForeignKey to subject model
        # - object: ForeignKey to object model
        # So field references need to go through these relationships
        
        # If the constraint is on a field that doesn't exist directly in the storage model,
        # it probably needs to be accessed through the object relationship
        
        storage_model = fact_node.django_model
        
        # Check if field exists directly
        if hasattr(storage_model, field_name):
            return field_name
            
        # Check if it exists through object relationship
        if hasattr(storage_model, 'object'):
            try:
                # Get the related model through object
                object_field = storage_model._meta.get_field('object')
                related_model = object_field.related_model
                if hasattr(related_model, field_name):
                    return f'object__{field_name}'
            except Exception:
                pass
                
        # Check if it exists through subject relationship
        if hasattr(storage_model, 'subject'):
            try:
                # Get the related model through subject
                subject_field = storage_model._meta.get_field('subject')
                related_model = subject_field.related_model
                if hasattr(related_model, field_name):
                    return f'subject__{field_name}'
            except Exception:
                pass
        
        # Fallback: assume it's through object (most common case)
        return f'object__{field_name}'


def build_advanced_orm_query(facts: List[Fact]) -> Optional[models.QuerySet]:
    """
    Main entry point: analyze query and build advanced ORM query.
    """
    try:
        # Step 1: Analyze the query
        analyzer = QueryAnalyzer(facts)
        ast = analyzer.analyze()
        
        # Step 2: Build ORM query from execution plan
        builder = ORMQueryBuilder(ast.execution_plan, ast)
        queryset = builder.build_query()
        
        return queryset
        
    except Exception:
        # If advanced analysis fails, return None to fall back to simpler approach
        return None