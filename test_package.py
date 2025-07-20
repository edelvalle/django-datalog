#!/usr/bin/env python
"""
Simple test to verify the django-datalog package works correctly
"""

import pytest
import django
from django.conf import settings

def test_package_imports():
    """Test that the package imports work correctly"""
    
    # Test basic imports
    import djdatalog
    assert djdatalog.__version__ == "0.1.0"
    
    # Test lazy imports
    from djdatalog import Fact, Var, query, store_facts, retract_facts
    
    # Test Var functionality
    from django.db.models import Q
    
    test_var = Var("test")
    assert test_var.name == "test"
    
    # Test Var with constraints
    adult_var = Var("person", where=Q(age__gte=18))
    assert adult_var.name == "person"
    assert adult_var.where is not None
    
    # Test Q object prefixing
    from djdatalog.models import _prefix_q_object
    simple_q = Q(age__gte=18)
    prefixed_q = _prefix_q_object(simple_q, "subject")
    assert len(prefixed_q.children) == 1
    field_name, value = prefixed_q.children[0]
    assert field_name == "subject__age__gte"
    assert value == 18

def test_query_signature():
    """Test that query function has correct signature"""
    from djdatalog import query
    import inspect
    
    sig = inspect.signature(query)
    assert 'hydrate' in sig.parameters
    hydrate_param = sig.parameters['hydrate']
    assert hydrate_param.default == True

if __name__ == "__main__":
    # Allow running as standalone script
    try:
        test_package_imports()
        test_query_signature()
        print("\n🚀 django-datalog package is working correctly!")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        exit(1)