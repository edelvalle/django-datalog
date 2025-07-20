"""
Fact system for djdatalog - handles fact definitions, storage, and retrieval.
"""

from dataclasses import dataclass, fields
from typing import Any, ClassVar
import uuid6

from django.db import models


@dataclass
class Fact:
    """Base class for all datalog facts."""
    
    subject: Any
    object: Any
    _django_model: ClassVar[type[models.Model]]
    
    def __init_subclass__(cls, **kwargs):
        """Automatically generate Django models for fact storage."""
        super().__init_subclass__(**kwargs)
        cls._django_model = cls._generate_django_model()
    
    @classmethod
    def _generate_django_model(cls):
        """Generate a Django model for storing this fact type."""
        model_name = f"Fact{cls.__name__}"
        
        # Create model fields
        model_fields = {
            'id': models.UUIDField(primary_key=True, default=uuid6.uuid7, editable=False),
            'subject': cls._create_django_field_for_name('subject'),
            'object': cls._create_django_field_for_name('object'),
            '__module__': cls.__module__,
            'Meta': type('Meta', (), {
                'app_label': 'djdatalog',
                'unique_together': (('subject', 'object'),),
            })
        }
        
        # Create and register the model
        django_model = type(model_name, (models.Model,), model_fields)
        
        return django_model
    
    @classmethod
    def _create_django_field_for_name(cls, field_name: str):
        """Create a Django field for a fact field based on type annotations."""
        fact_fields = fields(cls)
        field_obj = next((f for f in fact_fields if f.name == field_name), None)
        
        if not field_obj:
            raise ValueError(f"Field {field_name} not found in {cls.__name__}")
        
        # Extract Django model types from Union annotations
        model_type = cls._extract_model_type(field_obj.type)
        
        if model_type:
            return models.ForeignKey(
                model_type, 
                on_delete=models.CASCADE,
                related_name='+'
            )
        else:
            raise ValueError(f"Could not create Django field for {cls.__name__}.{field_name}")
    
    @classmethod
    def _extract_model_type(cls, type_annotation):
        """Extract Django model type from type annotation like 'User | Var'."""
        if hasattr(type_annotation, '__args__'):
            # Handle Union types (User | Var)
            for arg_type in type_annotation.__args__:
                if (hasattr(arg_type, '_meta') and 
                    hasattr(arg_type._meta, 'app_label')):
                    # This looks like a Django model
                    return arg_type
        elif (hasattr(type_annotation, '_meta') and 
              hasattr(type_annotation._meta, 'app_label')):
            # Direct Django model reference
            return type_annotation
        
        return None


def store_facts(*facts: Fact) -> None:
    """Store facts in the database."""
    if not facts:
        return
    
    # Group facts by type for batch operations
    facts_by_type = {}
    for fact in facts:
        fact_type = type(fact)
        if fact_type not in facts_by_type:
            facts_by_type[fact_type] = []
        facts_by_type[fact_type].append(fact)
    
    # Bulk create for each fact type
    for fact_type, fact_list in facts_by_type.items():
        django_model = fact_type._django_model
        model_instances = []
        
        for fact in fact_list:
            model_instances.append(django_model(
                subject=fact.subject,
                object=fact.object
            ))
        
        # Use ignore_conflicts to handle duplicates
        django_model.objects.bulk_create(model_instances, ignore_conflicts=True)


def retract_facts(*facts: Fact) -> None:
    """Remove facts from the database."""
    if not facts:
        return
    
    # Group facts by type for batch operations
    facts_by_type = {}
    for fact in facts:
        fact_type = type(fact)
        if fact_type not in facts_by_type:
            facts_by_type[fact_type] = []
        facts_by_type[fact_type].append(fact)
    
    # Batch delete for each fact type
    for fact_type, fact_list in facts_by_type.items():
        django_model = fact_type._django_model
        
        for fact in fact_list:
            django_model.objects.filter(
                subject=fact.subject,
                object=fact.object
            ).delete()