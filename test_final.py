#!/usr/bin/env python
"""
Final comprehensive test for django-datalog package
Tests all functionality that doesn't require database tables
"""

import os
import django
from django.conf import settings

# Configure Django first
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'test_settings') 

if not settings.configured:
    settings.configure(
        DEBUG=True,
        SECRET_KEY='test-secret-key-for-django-datalog-tests',
        DATABASES={
            'default': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': ':memory:',
            }
        },
        INSTALLED_APPS=[
            'django.contrib.contenttypes',
            'django.contrib.auth',
            'djdatalog',
        ],
        USE_TZ=True,
        USE_I18N=True,
        DJDATALOG_TESTING=True,
    )

django.setup()

def test_package_structure():
    """Test package structure and imports"""
    print("📦 Testing package structure and imports...")
    
    # Test main package import
    import djdatalog
    assert djdatalog.__version__ == "0.1.0"
    print(f"✅ Package version: {djdatalog.__version__}")
    
    # Test module imports
    from djdatalog import models, facts, query, rules
    print("✅ All modules importable")
    
    # Test core imports from models
    from djdatalog.models import Var, _prefix_q_object, _fact_to_django_query
    print("✅ Core functionality imports successful")

def test_var_functionality():
    """Test Var class functionality"""
    print("\n🔧 Testing Var functionality...")
    
    from djdatalog.models import Var
    from django.db.models import Q
    
    # Basic Var creation
    test_var = Var("test")
    assert test_var.name == "test"
    assert test_var.where is None
    print("✅ Basic Var creation")
    
    # Var with constraints
    adult_var = Var("person", where=Q(age__gte=18))
    assert adult_var.name == "person"
    assert adult_var.where is not None
    print("✅ Var with Q constraints")
    
    # Var representation
    simple_repr = repr(Var("test"))
    assert simple_repr == "Var('test')"
    constrained_repr = repr(Var("test", where=Q(active=True)))
    assert "Var('test'" in constrained_repr
    assert "where=" in constrained_repr
    print("✅ Var string representation")

def test_q_object_functionality():
    """Test Q object manipulation"""
    print("\n🔍 Testing Q object functionality...")
    
    from djdatalog.models import _prefix_q_object
    from django.db.models import Q
    
    # Simple Q object prefixing
    simple_q = Q(age__gte=18)
    prefixed_q = _prefix_q_object(simple_q, "subject")
    assert len(prefixed_q.children) == 1
    field_name, value = prefixed_q.children[0]
    assert field_name == "subject__age__gte"
    assert value == 18
    print("✅ Simple Q object prefixing")
    
    # Complex Q objects with AND
    complex_q = Q(age__gte=18) & Q(city="New York")
    prefixed_complex = _prefix_q_object(complex_q, "object")
    assert len(prefixed_complex.children) == 2
    field1, value1 = prefixed_complex.children[0]
    field2, value2 = prefixed_complex.children[1]
    assert field1 == "object__age__gte"
    assert value1 == 18
    assert field2 == "object__city"
    assert value2 == "New York"
    print("✅ Complex Q objects with AND")
    
    # Q objects with OR
    or_q = Q(age__gte=65) | Q(retired=True)
    prefixed_or = _prefix_q_object(or_q, "subject")
    assert prefixed_or.connector == Q.OR
    assert len(prefixed_or.children) == 2
    field1, value1 = prefixed_or.children[0]
    field2, value2 = prefixed_or.children[1]
    assert field1 == "subject__age__gte"
    assert value1 == 65
    assert field2 == "subject__retired"
    assert value2 == True
    print("✅ Q objects with OR")

def test_query_function():
    """Test query function signature and basic functionality"""
    print("\n📝 Testing query function...")
    
    import inspect
    from djdatalog.models import query
    
    # Test function signature
    sig = inspect.signature(query)
    assert 'hydrate' in sig.parameters
    hydrate_param = sig.parameters['hydrate']
    assert hydrate_param.default == True
    print("✅ Query function signature correct")

def test_rules_system():
    """Test rules system imports and basic functionality"""
    print("\n🔗 Testing rules system...")
    
    from djdatalog.models import rule, get_rules, clear_rules, Rule
    
    # Test that rule functions are available
    assert callable(rule)
    assert callable(get_rules)
    assert callable(clear_rules)
    print("✅ Rule functions available")
    
    # Test Rule class
    assert Rule is not None
    print("✅ Rule class available")

def test_fact_system():
    """Test fact system imports"""
    print("\n📊 Testing fact system...")
    
    from djdatalog.models import Fact, store_facts, retract_facts
    
    # Test that Fact is available
    assert Fact is not None
    assert callable(store_facts)
    assert callable(retract_facts)
    print("✅ Fact system available")

def test_django_integration():
    """Test Django integration without database operations"""
    print("\n🌐 Testing Django integration...")
    
    # Test that test models are available when DJDATALOG_TESTING=True
    from djdatalog.models import Person, Company, Employee
    
    # Test that these are Django model classes
    assert hasattr(Person, '_meta')
    assert hasattr(Company, '_meta')
    assert hasattr(Employee, '_meta')
    
    # Test app labels
    assert Person._meta.app_label == 'djdatalog'
    assert Company._meta.app_label == 'djdatalog'
    assert Employee._meta.app_label == 'djdatalog'
    
    print("✅ Django test models available and properly configured")

def run_all_tests():
    """Run all tests and report results"""
    tests = [
        test_package_structure,
        test_var_functionality,
        test_q_object_functionality,
        test_query_function,
        test_rules_system,
        test_fact_system,
        test_django_integration,
    ]
    
    passed = 0
    failed = 0
    
    for test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            print(f"❌ {test_func.__name__} failed: {e}")
            failed += 1
    
    return passed, failed

if __name__ == "__main__":
    print("🧪 Running comprehensive django-datalog tests...\n")
    
    try:
        passed, failed = run_all_tests()
        
        print(f"\n📊 Test Results:")
        print(f"✅ Passed: {passed}")
        print(f"❌ Failed: {failed}")
        print(f"📈 Success Rate: {passed}/{passed + failed} ({100 * passed // (passed + failed)}%)")
        
        if failed == 0:
            print("\n🎉 ALL TESTS PASSED!")
            print("🚀 django-datalog package is working correctly!")
        else:
            print(f"\n⚠️ {failed} tests failed")
            exit(1)
            
    except Exception as e:
        print(f"\n💥 Test suite failed: {e}")
        import traceback
        traceback.print_exc()
        exit(1)