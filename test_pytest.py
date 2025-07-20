"""
Pytest-compatible tests for django-datalog
"""

import pytest
from django.conf import settings
import django

# Configure Django before any djdatalog imports
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


def test_package_version():
    """Test that package version is correct"""
    import djdatalog
    assert djdatalog.__version__ == "0.1.0"


def test_core_imports():
    """Test that core functionality can be imported"""
    from djdatalog.models import Var, query, Fact, store_facts, retract_facts
    assert Var is not None
    assert query is not None
    assert Fact is not None
    assert store_facts is not None
    assert retract_facts is not None


def test_var_creation():
    """Test Var class functionality"""
    from djdatalog.models import Var
    from django.db.models import Q
    
    # Basic Var
    var = Var("test")
    assert var.name == "test"
    assert var.where is None
    
    # Var with constraints
    constrained_var = Var("person", where=Q(age__gte=18))
    assert constrained_var.name == "person"
    assert constrained_var.where is not None


def test_q_object_prefixing():
    """Test Q object manipulation"""
    from djdatalog.models import _prefix_q_object
    from django.db.models import Q
    
    simple_q = Q(age__gte=18)
    prefixed = _prefix_q_object(simple_q, "subject")
    assert len(prefixed.children) == 1
    field, value = prefixed.children[0]
    assert field == "subject__age__gte"
    assert value == 18


def test_query_signature():
    """Test query function signature"""
    import inspect
    from djdatalog.models import query
    
    sig = inspect.signature(query)
    assert 'hydrate' in sig.parameters
    assert sig.parameters['hydrate'].default == True


def test_django_models_available():
    """Test that Django test models are available"""
    from djdatalog.models import Person, Company, Employee
    
    assert hasattr(Person, '_meta')
    assert hasattr(Company, '_meta')
    assert hasattr(Employee, '_meta')
    assert Person._meta.app_label == 'djdatalog'