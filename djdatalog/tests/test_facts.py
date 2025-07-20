"""
Test facts for djdatalog - only available when DJDATALOG_TESTING is True.
These provide example facts using the test models for demonstration and testing.
"""

from dataclasses import dataclass
from django.conf import settings

from djdatalog.models import Fact, Var

# Only create facts when in testing mode
if getattr(settings, 'DJDATALOG_TESTING', False):
    from djdatalog.models import Person, Company, Employee
    
    @dataclass
    class ParentOf(Fact):
        """Person is parent of another person"""
        subject: Person | Var  # Parent
        object: Person | Var   # Child

    @dataclass
    class MarriedTo(Fact):
        """Person is married to another person"""
        subject: Person | Var  # Spouse 1
        object: Person | Var   # Spouse 2

    @dataclass
    class GrandparentOf(Fact):
        """Person is grandparent of another person (inferred)"""
        subject: Person | Var  # Grandparent
        object: Person | Var   # Grandchild

    @dataclass
    class SiblingOf(Fact):
        """Person is sibling of another person"""
        subject: Person | Var  # Sibling 1
        object: Person | Var   # Sibling 2

    @dataclass
    class WorksFor(Fact):
        """Person works for a company"""
        subject: Person | Var  # Employee
        object: Company | Var  # Company

    @dataclass
    class EmployeeOf(Fact):
        """Employee relationship with company"""
        subject: Employee | Var  # Employee record
        object: Company | Var    # Company

    @dataclass
    class ColleaguesOf(Fact):
        """Two people are colleagues (work at same company)"""
        subject: Person | Var  # Person 1
        object: Person | Var   # Person 2

else:
    # When not in testing mode, create dummy classes
    class ParentOf:
        pass
    
    class MarriedTo:
        pass
        
    class GrandparentOf:
        pass
        
    class SiblingOf:
        pass
        
    class WorksFor:
        pass
        
    class EmployeeOf:
        pass
        
    class ColleaguesOf:
        pass