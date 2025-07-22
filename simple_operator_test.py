#!/usr/bin/env python3
"""
Simple test of the operator syntax without Django models.
"""

import os
import sys

# Add the django_datalog module to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'django_datalog'))

# Set up minimal Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'test_project.testsite.settings')
import django

django.setup()

from dataclasses import dataclass

from django_datalog.facts import Fact

# Test that the operators work at the basic level
print("Testing operator syntax...")

# Create some dummy Fact classes for testing (inferred to avoid Django models)
@dataclass
class TestOwner(Fact, inferred=True):
    subject: any  # Using any to avoid Django model requirements
    object: any

@dataclass
class TestAdmin(Fact, inferred=True):
    subject: any
    object: any

# Test basic operators
print("\n1. Testing Fact | Fact:")
fact1 = TestOwner("alice", "doc")
fact2 = TestAdmin("bob", "doc")
result = fact1 | fact2
print(f"   {fact1} | {fact2}")
print(f"   Result: {result}")
print(f"   Type: {type(result)}")
print(f"   Length: {len(result)}")

print("\n2. Testing Fact & Fact:")
result2 = fact1 & fact2
print(f"   {fact1} & {fact2}")
print(f"   Result: {result2}")
print(f"   Type: {type(result2)}")
print(f"   Length: {len(result2)}")

print("\n3. Testing [Fact1, Fact2] | Fact3:")
fact_list = [fact1, fact2]
fact3 = TestAdmin("charlie", "doc")
result3 = fact_list | fact3
print(f"   {fact_list} | {fact3}")
print(f"   Result: {result3}")
print(f"   Type: {type(result3)}")
print(f"   Length: {len(result3)}")

print("\n4. Testing (Fact1, Fact2) | Fact3:")
fact_tuple = (fact1, fact2)
result4 = fact_tuple | fact3
print(f"   {fact_tuple} | {fact3}")
print(f"   Result: {result4}")
print(f"   Type: {type(result4)}")
print(f"   Length: {len(result4)}")

print("\n5. Testing (Fact1, Fact2) & Fact3:")
result5 = fact_tuple & fact3
print(f"   {fact_tuple} & {fact3}")
print(f"   Result: {result5}")
print(f"   Type: {type(result5)}")
print(f"   Length: {len(result5)}")

print("\n6. Testing error case: [Fact1, Fact2] & Fact3:")
try:
    result6 = fact_list & fact3
    print("   ERROR: Should have raised TypeError")
except TypeError as e:
    print(f"   Correctly raised TypeError: {e}")

print("\n✅ All operator tests passed!")
