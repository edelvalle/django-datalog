#!/usr/bin/env python
"""
Test core functionality of django-datalog package without complex model generation
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

def test_package_imports():
    """Test basic package functionality"""
    print("🧪 Testing django-datalog core functionality...")
    
    # Test basic package import
    import djdatalog
    assert djdatalog.__version__ == "0.1.0"
    print("✅ Package version:", djdatalog.__version__)
    
    # Test core imports
    from djdatalog.models import Var, _prefix_q_object
    from django.db.models import Q
    print("✅ Core imports successful")
    
    # Test Var functionality
    test_var = Var("test")
    assert test_var.name == "test"
    assert test_var.where is None
    print("✅ Basic Var creation works")
    
    # Test Var with constraints
    adult_var = Var("person", where=Q(age__gte=18))
    assert adult_var.name == "person"
    assert adult_var.where is not None
    print("✅ Var with Q constraints works")
    
    # Test Q object prefixing
    simple_q = Q(age__gte=18)
    prefixed_q = _prefix_q_object(simple_q, "subject")
    assert len(prefixed_q.children) == 1
    field_name, value = prefixed_q.children[0]
    assert field_name == "subject__age__gte"
    assert value == 18
    print("✅ Q object prefixing works")
    
    # Test complex Q objects
    complex_q = Q(age__gte=18) & Q(city="New York")
    prefixed_complex = _prefix_q_object(complex_q, "object")
    assert len(prefixed_complex.children) == 2
    print("✅ Complex Q objects work")
    
    # Test OR operations
    or_q = Q(age__gte=65) | Q(retired=True)
    prefixed_or = _prefix_q_object(or_q, "subject")
    assert prefixed_or.connector == Q.OR
    assert len(prefixed_or.children) == 2
    print("✅ Q object OR operations work")

def test_query_signature():
    """Test query function signature"""
    print("\n🔍 Testing query function signature...")
    
    import inspect
    from djdatalog.models import query
    
    sig = inspect.signature(query)
    assert 'hydrate' in sig.parameters
    hydrate_param = sig.parameters['hydrate']
    assert hydrate_param.default == True
    print("✅ Query function has correct signature with hydrate parameter")

def test_django_models():
    """Test that Django test models are available"""
    print("\n🗄️ Testing Django test models...")
    
    from djdatalog.models import Person, Company, Employee
    
    # Test that these are real Django models
    assert hasattr(Person, 'objects')
    assert hasattr(Company, 'objects')
    assert hasattr(Employee, 'objects')
    
    # Test model creation
    person = Person.objects.create(name="Test Person", age=25)
    assert person.name == "Test Person"
    assert person.age == 25
    print("✅ Django test models work correctly")

def test_rules_system():
    """Test rule system availability"""
    print("\n🔗 Testing rules system...")
    
    from djdatalog.models import rule, get_rules, clear_rules, Rule
    
    # Test that we can import rule functions
    assert callable(rule)
    assert callable(get_rules)
    assert callable(clear_rules)
    assert Rule is not None
    print("✅ Rules system imports successfully")

if __name__ == "__main__":
    try:
        test_package_imports()
        test_query_signature()
        test_django_models()
        test_rules_system()
        print("\n🎉 All core functionality tests passed!")
        print("🚀 django-datalog package is working correctly!")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        exit(1)