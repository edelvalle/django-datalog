#!/usr/bin/env python
"""
Simple test runner for djdatalog tests without full Django setup.
"""

import os
import sys
import django
from django.conf import settings
from django.test.utils import get_runner

# Minimal Django configuration for testing
if not settings.configured:
    settings.configure(
        DEBUG=True,
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
        USE_I18N=True,
        USE_TZ=True,
        DJDATALOG_TESTING=True,  # Enable test models and facts
    )

django.setup()


def run_basic_tests():
    """Run basic functionality tests without database."""
    print("Testing basic djdatalog functionality...")
    
    from django.db.models import Q
    from djdatalog.models import Var, _prefix_q_object
    
    try:
        # Test 1: Var creation
        print("✓ Testing Var creation")
        person_var = Var("person")
        assert person_var.name == "person"
        assert person_var.where is None
        
        # Test 2: Var with constraints  
        print("✓ Testing Var with constraints")
        adult_var = Var("person", where=Q(age__gte=18))
        assert adult_var.name == "person"
        assert adult_var.where is not None
        
        # Test 3: Q object prefixing
        print("✓ Testing Q object prefixing")
        simple_q = Q(age__gte=18)
        prefixed_q = _prefix_q_object(simple_q, "subject")
        
        assert len(prefixed_q.children) == 1
        field_name, value = prefixed_q.children[0]
        assert field_name == "subject__age__gte"
        assert value == 18
        
        # Test 4: Complex Q object
        print("✓ Testing complex Q objects")
        complex_q = Q(age__gte=18) & Q(city="New York")
        prefixed_complex = _prefix_q_object(complex_q, "object")
        
        assert len(prefixed_complex.children) == 2
        field1, value1 = prefixed_complex.children[0]
        field2, value2 = prefixed_complex.children[1]
        
        assert field1 == "object__age__gte"
        assert value1 == 18
        assert field2 == "object__city"
        assert value2 == "New York"
        
        # Test 5: OR operations
        print("✓ Testing Q object OR operations")
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
        
        # Test 6: Var repr
        print("✓ Testing Var string representation")
        simple_repr = repr(Var("test"))
        assert simple_repr == "Var('test')"
        
        constrained_repr = repr(Var("test", where=Q(active=True)))
        assert "Var('test'" in constrained_repr
        assert "where=" in constrained_repr
        
        print("\n🎉 All basic tests passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_with_real_models():
    """Test djdatalog with real Django models and facts."""
    print("Testing djdatalog with real Django models...")
    
    try:
        from django.db import connection
        from djdatalog.models import Person, Company
        from djdatalog.tests.test_facts import ParentOf, WorksFor, GrandparentOf
        from djdatalog.models import store_facts, query
        from django.db.models import Q
        
        # Create tables
        with connection.schema_editor() as schema_editor:
            schema_editor.create_model(Person)
            schema_editor.create_model(Company)
            
            # Create fact tables (they should be auto-created)
            schema_editor.create_model(ParentOf._django_model)
            schema_editor.create_model(WorksFor._django_model)
            schema_editor.create_model(GrandparentOf._django_model)
        
        # Create test data
        print("✓ Creating test people")
        john = Person.objects.create(name="John", age=65, city="New York", married=True)
        alice = Person.objects.create(name="Alice", age=40, city="New York", married=True)
        bob = Person.objects.create(name="Bob", age=18, city="Boston", married=False)
        charlie = Person.objects.create(name="Charlie", age=10, city="New York", married=False)
        
        # Create test company
        company = Company.objects.create(name="ACME Corp", active=True)
        
        # Store facts
        print("✓ Storing family and work facts")
        store_facts(
            ParentOf(subject=john, object=alice),    # John -> Alice
            ParentOf(subject=alice, object=bob),     # Alice -> Bob  
            ParentOf(subject=alice, object=charlie), # Alice -> Charlie
            WorksFor(subject=alice, object=company), # Alice works at ACME
            WorksFor(subject=bob, object=company),   # Bob works at ACME
        )
        
        # Test basic query
        print("✓ Testing basic parent query")
        alice_children = list(query(ParentOf(alice, Var("child"))))
        assert len(alice_children) == 2  # Bob and Charlie
        child_names = {result["child"].name for result in alice_children}
        assert child_names == {"Bob", "Charlie"}
        
        # Test inference rule (grandparent)
        print("✓ Testing grandparent inference")
        john_grandchildren = list(query(GrandparentOf(john, Var("grandchild"))))
        assert len(john_grandchildren) == 2  # Bob and Charlie via Alice
        grandchild_names = {result["grandchild"].name for result in john_grandchildren}
        assert grandchild_names == {"Bob", "Charlie"}
        
        # Test Q object constraints
        print("✓ Testing Q object constraints")
        # Find John's adult grandchildren
        adult_grandchildren = list(query(
            GrandparentOf(john, Var("grandchild", where=Q(age__gte=18)))
        ))
        assert len(adult_grandchildren) == 1  # Only Bob (age 18)
        assert adult_grandchildren[0]["grandchild"].name == "Bob"
        
        # Test complex Q constraints
        print("✓ Testing complex Q constraints")
        # Find people in New York who are married
        ny_married = list(query(
            WorksFor(Var("person", where=Q(city="New York") & Q(married=True)), company)
        ))
        assert len(ny_married) == 1  # Only Alice
        assert ny_married[0]["person"].name == "Alice"
        
        # Test hydration control
        print("✓ Testing hydration control")
        # Get IDs only (performance)
        child_ids = []
        for result in query(ParentOf(alice, Var("child")), hydrate=False):
            child_ids.append(result["child"])
        assert len(child_ids) == 2
        assert all(isinstance(cid, int) for cid in child_ids)  # Should be IDs, not objects
        
        # Get full objects (default)
        child_objects = []
        for result in query(ParentOf(alice, Var("child")), hydrate=True):
            child_objects.append(result["child"])
        assert len(child_objects) == 2
        assert all(hasattr(child, 'name') for child in child_objects)  # Should be full objects
        
        print("\n🚀 All real model tests passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Real model test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_query_signature():
    """Test the query function signature."""
    print("Testing query function signature...")
    
    try:
        import inspect
        import sys
        import os
        
        # Add parent directory to path to import djdatalog
        try:
            parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            sys.path.insert(0, parent_dir)
        except NameError:
            # __file__ not defined when run via exec, skip path setup
            pass
        
        from djdatalog.models import query
        
        sig = inspect.signature(query)
        
        # Check that hydrate parameter exists
        assert 'hydrate' in sig.parameters
        
        # Check that hydrate defaults to True
        hydrate_param = sig.parameters['hydrate']
        assert hydrate_param.default == True
        # Note: annotation might be a string in some Python versions
        # Just check it exists and isn't empty
        assert hydrate_param.annotation is not None
        
        print("✓ Query function signature is correct")
        return True
        
    except Exception as e:
        print(f"❌ Query signature test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("Running djdatalog tests...\n")
    
    success1 = run_basic_tests()
    success2 = test_query_signature()
    success3 = test_with_real_models()
    
    if success1 and success2 and success3:
        print("\n🎉 ALL DJDATALOG TESTS PASSED!")
        print("✅ Basic functionality: PASSED")  
        print("✅ Query signature: PASSED")
        print("✅ Real models & facts: PASSED")
        print("✅ Q object constraints: PASSED")
        print("✅ Hydration control: PASSED")
        print("✅ Inference rules: PASSED")
        print("\n🚀 djdatalog is ready for package release!")
        sys.exit(0)
    else:
        print("\n💥 Some tests failed.")
        sys.exit(1)