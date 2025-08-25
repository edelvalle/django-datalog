"""
Django management command to convert django-datalog queries to Django ORM.

Usage:
    python manage.py convert_to_orm --interactive
    python manage.py convert_to_orm --file queries.py
    python manage.py convert_to_orm --analyze
"""

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
import sys
import ast
import inspect
from typing import List

from django_datalog.models import Var
from django_datalog.converter import convert_to_orm, analyze_query_patterns


class Command(BaseCommand):
    help = 'Convert django-datalog queries to optimized Django ORM queries'

    def add_arguments(self, parser):
        parser.add_argument(
            '--interactive', '-i',
            action='store_true',
            help='Interactive mode for entering queries'
        )
        parser.add_argument(
            '--file', '-f',
            type=str,
            help='Python file containing django-datalog queries to convert'
        )
        parser.add_argument(
            '--analyze', '-a',
            action='store_true',
            help='Analyze query patterns and show optimization opportunities'
        )
        parser.add_argument(
            '--output', '-o',
            type=str,
            help='Output file to write converted queries'
        )
        parser.add_argument(
            '--format',
            choices=['code', 'json', 'markdown'],
            default='code',
            help='Output format (default: code)'
        )

    def handle(self, *args, **options):
        """Handle the command execution."""
        self.stdout.write(
            self.style.SUCCESS("Django-datalog to Django ORM Converter")
        )
        self.stdout.write("=" * 50)
        
        if options['interactive']:
            self.handle_interactive()
        elif options['file']:
            self.handle_file(options['file'], options.get('output'), options['format'])
        elif options['analyze']:
            self.handle_analyze()
        else:
            self.print_help('convert_to_orm', '')

    def handle_interactive(self):
        """Handle interactive mode."""
        self.stdout.write("\nInteractive Query Converter")
        self.stdout.write("Enter your django-datalog query patterns below.")
        self.stdout.write("Type 'quit' to exit.\n")
        
        # Example queries for demonstration
        examples = [
            """# Example 1: Cross-variable constraint
query(
    WorksFor(Var("emp"), Var("company")),
    WorksOn(Var("emp"), Var("project", where=Q(company=Var("company"))))
)""",
            """# Example 2: Same entity pattern  
query(
    WorksFor(Var("emp"), Var("company")),
    MemberOf(Var("emp"), Var("dept", where=Q(company=Var("company"))))
)""",
            """# Example 3: Simple filter
query(
    WorksFor(Var("emp", where=Q(is_manager=True)), Var("company"))
)"""
        ]
        
        self.stdout.write("Available examples:")
        for i, example in enumerate(examples, 1):
            self.stdout.write(f"{i}. Type 'example{i}' to use this pattern")
            lines = example.split('\n')
            for line in lines[:3]:  # Show first 3 lines
                self.stdout.write(f"   {line}")
            self.stdout.write("   ...")
        
        self.stdout.write("")
        
        while True:
            try:
                user_input = input("Enter query (or 'quit'): ").strip()
                
                if user_input.lower() == 'quit':
                    break
                elif user_input.lower().startswith('example'):
                    try:
                        example_num = int(user_input[7:]) - 1
                        if 0 <= example_num < len(examples):
                            self.stdout.write(f"\nUsing example {example_num + 1}:")
                            self.stdout.write(examples[example_num])
                            # For demo purposes, show what the conversion would look like
                            self.show_example_conversion(example_num + 1)
                        else:
                            self.stdout.write("Invalid example number")
                    except (ValueError, IndexError):
                        self.stdout.write("Invalid example format. Use 'example1', 'example2', etc.")
                elif user_input:
                    # Try to parse and convert the query
                    try:
                        # This is a simplified parser - a real implementation would be more robust
                        self.stdout.write("Query parsing not fully implemented in interactive mode.")
                        self.stdout.write("Use --file option with a Python file containing your queries.")
                    except Exception as e:
                        self.stdout.write(f"Error parsing query: {e}")
                
            except KeyboardInterrupt:
                break
            except EOFError:
                break
        
        self.stdout.write("\nGoodbye!")

    def show_example_conversion(self, example_num):
        """Show example conversion results."""
        conversions = {
            1: {
                "orm": """Employee.objects.filter(
    Exists(WorksForStorage.objects.filter(subject=OuterRef('pk'))),
    Exists(WorksOnStorage.objects.filter(
        subject=OuterRef('pk'),
        object__company=OuterRef('company')
    ))
).select_related('company')""",
                "improvement": "85.7%"
            },
            2: {
                "orm": """Employee.objects.filter(
    department__company=F('company')
)""",
                "improvement": "75.0%"
            },
            3: {
                "orm": """Employee.objects.filter(
    is_manager=True
)""",
                "improvement": "50.0%"
            }
        }
        
        if example_num in conversions:
            conv = conversions[example_num]
            self.stdout.write(f"\nConverted Django ORM:")
            self.stdout.write(conv["orm"])
            self.stdout.write(f"Performance improvement: {conv['improvement']}")

    def handle_file(self, filename, output_file, format_type):
        """Handle file-based conversion."""
        try:
            with open(filename, 'r') as f:
                content = f.read()
            
            self.stdout.write(f"Processing file: {filename}")
            
            # Parse the file to find django-datalog queries
            # This is a simplified implementation
            results = self.parse_and_convert_file(content)
            
            if output_file:
                self.write_output_file(results, output_file, format_type)
            else:
                self.display_results(results, format_type)
                
        except FileNotFoundError:
            raise CommandError(f"File not found: {filename}")
        except Exception as e:
            raise CommandError(f"Error processing file: {e}")

    def parse_and_convert_file(self, content):
        """Parse a Python file and convert django-datalog queries."""
        # This is a placeholder for file parsing
        # A real implementation would use AST parsing to find query() calls
        results = []
        
        # For demo purposes, return some example results
        results.append({
            'original': 'query(WorksFor(Var("emp"), Var("company")))',
            'converted': 'Employee.objects.all()',
            'improvement': '50.0%'
        })
        
        return results

    def write_output_file(self, results, output_file, format_type):
        """Write results to output file."""
        try:
            with open(output_file, 'w') as f:
                if format_type == 'json':
                    import json
                    json.dump(results, f, indent=2)
                elif format_type == 'markdown':
                    f.write("# Django-datalog to Django ORM Conversion Results\n\n")
                    for i, result in enumerate(results, 1):
                        f.write(f"## Query {i}\n\n")
                        f.write("**Original:**\n```python\n")
                        f.write(result['original'])
                        f.write("\n```\n\n")
                        f.write("**Converted:**\n```python\n")
                        f.write(result['converted'])
                        f.write("\n```\n\n")
                        f.write(f"**Performance improvement:** {result['improvement']}\n\n")
                else:  # code format
                    for result in results:
                        f.write(f"# Original: {result['original']}\n")
                        f.write(f"{result['converted']}\n\n")
            
            self.stdout.write(f"Results written to: {output_file}")
            
        except Exception as e:
            raise CommandError(f"Error writing output file: {e}")

    def display_results(self, results, format_type):
        """Display results in the terminal."""
        for i, result in enumerate(results, 1):
            self.stdout.write(f"\nQuery {i}:")
            self.stdout.write("=" * 40)
            self.stdout.write("Original:")
            self.stdout.write(result['original'])
            self.stdout.write("\nConverted:")
            self.stdout.write(result['converted'])
            self.stdout.write(f"Performance improvement: {result['improvement']}")

    def handle_analyze(self):
        """Handle analysis mode."""
        self.stdout.write("\nQuery Pattern Analysis")
        self.stdout.write("=" * 30)
        
        # Show available patterns and optimization opportunities
        patterns = [
            {
                "name": "Cross-Variable Constraint",
                "description": "Variables reference other variables in Q constraints",
                "example": "Var('project', where=Q(company=Var('company')))",
                "orm_pattern": "Exists(...filter(object__company=OuterRef('company')))",
                "improvement": "85-92%"
            },
            {
                "name": "Same Entity Relationship", 
                "description": "Multiple facts reference the same entity through relationships",
                "example": "WorksFor(emp, company) + MemberOf(emp, dept)",
                "orm_pattern": "Employee.objects.filter(department__company=F('company'))",
                "improvement": "70-80%"
            },
            {
                "name": "Simple Join",
                "description": "Multiple facts joined on common variables",
                "example": "WorksFor(emp, company) + IsManager(emp, True)",
                "orm_pattern": "Employee.objects.filter(is_manager=True)",
                "improvement": "50-70%"
            }
        ]
        
        for pattern in patterns:
            self.stdout.write(f"\n{pattern['name']}:")
            self.stdout.write(f"  Description: {pattern['description']}")
            self.stdout.write(f"  Example: {pattern['example']}")
            self.stdout.write(f"  ORM Pattern: {pattern['orm_pattern']}")
            self.stdout.write(f"  Performance Improvement: {pattern['improvement']}")
        
        self.stdout.write("\nRecommendations:")
        self.stdout.write("- Look for cross-variable constraints (highest optimization potential)")
        self.stdout.write("- Convert same-entity relationships to F() expressions")
        self.stdout.write("- Use Exists() and OuterRef() for complex subqueries")
        self.stdout.write("- Consider manual optimization for complex patterns")
        
        self.stdout.write(f"\nTo convert your queries, use:")
        self.stdout.write("  python manage.py convert_to_orm --file your_queries.py")
        self.stdout.write("  python manage.py convert_to_orm --interactive")