#!/usr/bin/env python
"""
Working test for django-datalog package
"""

import os
import django
from django.conf import settings

# Configure Django first, before any djdatalog imports
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'test_settings') 

# Additional configuration to ensure django setup works
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

def test_basic_functionality():
    """Test basic django-datalog functionality"""
    print("Testing django-datalog basic functionality...")
    
    # Test basic imports after Django setup
    import djdatalog
    print(f"✅ Package version: {djdatalog.__version__}")
    
    # Test imports work
    from djdatalog.models import Fact, Var, query, store_facts, retract_facts
    print("✅ Main API imports successful")
    
    # Test Var functionality
    from django.db.models import Q
    
    test_var = Var("test")
    assert test_var.name == "test"
    print("✅ Var creation works")
    
    # Test Var with constraints
    adult_var = Var("person", where=Q(age__gte=18))
    assert adult_var.name == "person"
    assert adult_var.where is not None
    print("✅ Var with Q constraints works")
    
    # Test Q object prefixing
    from djdatalog.models import _prefix_q_object
    simple_q = Q(age__gte=18)
    prefixed_q = _prefix_q_object(simple_q, "subject")
    assert len(prefixed_q.children) == 1
    field_name, value = prefixed_q.children[0]
    assert field_name == "subject__age__gte"  
    assert value == 18
    print("✅ Q object prefixing works")
    
    # Test query function signature
    import inspect
    from djdatalog.models import query as query_func
    sig = inspect.signature(query_func)
    assert 'hydrate' in sig.parameters
    hydrate_param = sig.parameters['hydrate'] 
    assert hydrate_param.default == True
    print("✅ Query function signature is correct")
    
    print("\n🎉 All basic functionality tests passed!")

def test_imports_only():
    """Test that imports work without using models"""
    print("Testing imports without Django models...")
    
    # Test that we can import without issues
    from djdatalog.models import Var, _prefix_q_object
    from django.db.models import Q
    
    # Basic Var test
    v = Var("test")
    assert v.name == "test"
    
    # Q object test
    q = Q(name="test")
    prefixed = _prefix_q_object(q, "subject")
    assert len(prefixed.children) == 1
    
    print("✅ Import-only tests passed!")

if __name__ == "__main__":
    try:
        test_imports_only()
        test_basic_functionality()
        print("\n🚀 django-datalog package is working correctly!")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        exit(1)