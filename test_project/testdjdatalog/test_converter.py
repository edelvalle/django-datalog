"""
Test the automatic django-datalog to Django ORM converter.
"""

from django.db.models import Q
from django.test import TestCase

from django_datalog.converter import analyze_query_patterns, convert_to_orm
from django_datalog.models import Var

from .models import (
    MemberOf,
    WorksFor,
    WorksOn,
)


class ConverterTest(TestCase):
    """Test the automatic query converter."""

    def test_cross_variable_constraint_conversion(self):
        """Test conversion of cross-variable constraint queries."""

        # Django-datalog query with cross-variable constraint
        conditions = [
            WorksFor(Var("emp"), Var("company")),
            WorksOn(Var("emp"), Var("project", where=Q(company=Var("company"))))
        ]

        # Convert to Django ORM
        result = convert_to_orm(conditions)

        print("\n" + "="*70)
        print("AUTOMATIC QUERY CONVERSION RESULTS")
        print("="*70)
        print("Original django-datalog query:")
        print("query(")
        print("    WorksFor(Var('emp'), Var('company')),")
        print("    WorksOn(Var('emp'), Var('project', where=Q(company=Var('company'))))")
        print(")")
        print()
        print("Generated Django ORM code:")
        print(result.orm_code)
        print()
        print("Performance Analysis:")
        print(f"- Original query count: {result.original_query_count}")
        print(f"- Optimized query count: {result.optimized_query_count}")
        print(f"- Performance improvement: {result.improvement_percentage:.1f}%")
        print()
        print("Patterns detected:")
        for pattern in result.patterns_used:
            print(f"- {pattern.name}: {pattern.description}")
            print(f"  Improvement: {pattern.query_count_improvement}")

        if result.warnings:
            print()
            print("Warnings:")
            for warning in result.warnings:
                print(f"- {warning}")

        # Verify the conversion looks reasonable
        self.assertIn("Employee.objects.filter", result.orm_code)
        self.assertIn("Exists", result.orm_code)
        self.assertIn("OuterRef", result.orm_code)
        self.assertGreater(result.improvement_percentage, 80)  # Should be very high improvement
        self.assertGreater(len(result.patterns_used), 0)

    def test_simple_join_conversion(self):
        """Test conversion of simple join queries."""

        conditions = [
            WorksFor(Var("emp", where=Q(is_manager=True)), Var("company")),
            MemberOf(Var("emp"), Var("dept"))
        ]

        result = convert_to_orm(conditions)

        print("\n" + "="*70)
        print("SIMPLE JOIN CONVERSION")
        print("="*70)
        print("Generated Django ORM code:")
        print(result.orm_code)
        print(f"Performance improvement: {result.improvement_percentage:.1f}%")

        # Should generate reasonable ORM code
        self.assertIn("objects.filter", result.orm_code)
        self.assertGreater(result.improvement_percentage, 0)

    def test_same_entity_pattern_conversion(self):
        """Test conversion of same-entity patterns."""

        conditions = [
            WorksFor(Var("emp"), Var("company")),
            MemberOf(Var("emp"), Var("dept", where=Q(company=Var("company"))))
        ]

        result = convert_to_orm(conditions)

        print("\n" + "="*70)
        print("SAME ENTITY PATTERN CONVERSION")
        print("="*70)
        print("Generated Django ORM code:")
        print(result.orm_code)
        print(f"Performance improvement: {result.improvement_percentage:.1f}%")

        # Should recognize the pattern and use F() expressions
        self.assertIn("objects.filter", result.orm_code)

    def test_query_pattern_analysis(self):
        """Test the query pattern analysis functionality."""

        conditions = [
            WorksFor(Var("emp"), Var("company")),
            WorksOn(Var("emp"), Var("project", where=Q(company=Var("company"))))
        ]

        analysis = analyze_query_patterns(conditions)

        print("\n" + "="*70)
        print("QUERY PATTERN ANALYSIS")
        print("="*70)
        print("Variables detected:")
        for var_name, usages in analysis['variables'].items():
            print(f"- {var_name}: used in {len(usages)} facts")
            for fact, role in usages:
                print(f"  - {type(fact).__name__}.{role}")

        print()
        print("Cross-variable constraints:")
        for fact, field, constraint in analysis['cross_variable_constraints']:
            print(f"- {type(fact).__name__}.{field}: {constraint}")

        print()
        print("Join variables:", analysis['join_variables'])
        print("Primary model:", analysis['primary_model'])
        print("Complexity score:", analysis['complexity_score'])
        print("Optimization potential:", analysis['optimization_potential'])

        # Verify analysis results
        self.assertIn('emp', analysis['variables'])
        self.assertIn('company', analysis['variables'])
        self.assertGreater(len(analysis['cross_variable_constraints']), 0)
        self.assertIn('emp', analysis['join_variables'])
        self.assertEqual(analysis['optimization_potential'], 'HIGH')

    def test_converter_comprehensive_patterns(self):
        """Test the converter with various query patterns."""

        test_cases = [
            {
                "name": "Cross-Variable Constraint",
                "conditions": [
                    WorksFor(Var("emp"), Var("company")),
                    WorksOn(Var("emp"), Var("project", where=Q(company=Var("company"))))
                ],
                "expected_patterns": ["Cross-Variable Constraint"]
            },
            {
                "name": "Simple Filter",
                "conditions": [
                    WorksFor(Var("emp", where=Q(is_manager=True)), Var("company"))
                ],
                "expected_patterns": []  # Should use simple join pattern
            },
            {
                "name": "Multiple Joins",
                "conditions": [
                    WorksFor(Var("emp"), Var("company")),
                    MemberOf(Var("emp"), Var("dept")),
                    WorksOn(Var("emp"), Var("project"))
                ],
                "expected_patterns": []  # Complex pattern
            }
        ]

        print("\n" + "="*70)
        print("COMPREHENSIVE PATTERN TESTING")
        print("="*70)

        for i, test_case in enumerate(test_cases, 1):
            print(f"\n{i}. {test_case['name']}:")
            result = convert_to_orm(test_case['conditions'])
            print(f"   Query improvement: {result.improvement_percentage:.1f}%")
            print(f"   Patterns used: {[p.name for p in result.patterns_used]}")
            print(f"   Warnings: {len(result.warnings)}")

            # Code should be generated for all cases
            self.assertIsNotNone(result.orm_code)
            self.assertGreater(len(result.orm_code), 0)

    def test_converter_error_handling(self):
        """Test converter error handling with edge cases."""

        # Empty conditions
        result = convert_to_orm([])
        self.assertIsNotNone(result.orm_code)

        # Single condition
        result = convert_to_orm([WorksFor(Var("emp"), Var("company"))])
        self.assertIsNotNone(result.orm_code)
        self.assertGreater(result.improvement_percentage, 0)

    def test_performance_estimation_accuracy(self):
        """Test that performance estimations are reasonable."""

        # Simple query should have lower original cost
        simple_conditions = [WorksFor(Var("emp"), Var("company"))]
        simple_result = convert_to_orm(simple_conditions)

        # Complex query should have higher original cost
        complex_conditions = [
            WorksFor(Var("emp"), Var("company")),
            WorksOn(Var("emp"), Var("project", where=Q(company=Var("company")))),
            MemberOf(Var("emp"), Var("dept", where=Q(company=Var("company"))))
        ]
        complex_result = convert_to_orm(complex_conditions)

        print("\n" + "="*70)
        print("PERFORMANCE ESTIMATION ACCURACY")
        print("="*70)
        print(f"Simple query original cost: {simple_result.original_query_count}")
        print(f"Complex query original cost: {complex_result.original_query_count}")
        print(f"Simple query improvement: {simple_result.improvement_percentage:.1f}%")
        print(f"Complex query improvement: {complex_result.improvement_percentage:.1f}%")

        # Complex queries should have higher original cost
        self.assertGreater(complex_result.original_query_count, simple_result.original_query_count)
        # Both should have significant improvements
        self.assertGreater(simple_result.improvement_percentage, 50)
        self.assertGreater(complex_result.improvement_percentage, 80)
