"""
Datalog system for Django - main module with public API and test models.

This module provides the public interface for djdatalog, importing from
specialized modules for facts, queries, and rules. It also includes
test models that are only loaded when DJDATALOG_TESTING is True.
"""

from django.conf import settings
from django.db import models

# Public API imports
from djdatalog.facts import Fact, store_facts, retract_facts
from djdatalog.query import Var, query, _prefix_q_object, _fact_to_django_query
from djdatalog.rules import rule, Rule, get_rules, clear_rules


# Only create models when in testing mode
if getattr(settings, 'DJDATALOG_TESTING', False):
    
    class Person(models.Model):
        """Example Person model for family relationship tests."""
        name = models.CharField(max_length=100)
        age = models.PositiveIntegerField(null=True, blank=True)
        city = models.CharField(max_length=100, blank=True)
        married = models.BooleanField(default=False)
        retired = models.BooleanField(default=False)
        
        class Meta:
            app_label = 'djdatalog'
            
        def __str__(self):
            return self.name

    
    class Company(models.Model):
        """Example Company model for business relationship tests."""
        name = models.CharField(max_length=100)
        active = models.BooleanField(default=True)
        
        class Meta:
            app_label = 'djdatalog'
            
        def __str__(self):
            return self.name

    
    class Employee(models.Model):
        """Example Employee model for organizational hierarchy tests."""
        person = models.OneToOneField(Person, on_delete=models.CASCADE)
        company = models.ForeignKey(Company, on_delete=models.CASCADE)
        position = models.CharField(max_length=100)
        
        class Meta:
            app_label = 'djdatalog'
            
        def __str__(self):
            return f"{self.person.name} at {self.company.name}"

else:
    # When not in testing mode, create dummy classes to prevent import errors
    class Person:
        pass
    
    class Company:
        pass
        
    class Employee:
        pass


# Re-export for backward compatibility and public API
__all__ = [
    # Core classes
    'Fact',
    'Var', 
    'Rule',
    
    # Core functions
    'query',
    'store_facts',
    'retract_facts',
    'rule',
    'get_rules',
    'clear_rules',
    
    # Test models (when DJDATALOG_TESTING=True)
    'Person',
    'Company',
    'Employee',
    
    # Internal functions (exposed for testing)
    '_prefix_q_object',
    '_fact_to_django_query',
]