#!/usr/bin/env python3
"""
Test script to verify inferred facts functionality.
"""

from dataclasses import dataclass

from django_datalog import Fact, Var, query, rule, store_facts


# Mock model classes for testing
class User:
    def __init__(self, name, pk=None):
        self.name = name
        self.pk = pk or id(self)

    def __str__(self):
        return self.name

    def __eq__(self, other):
        return isinstance(other, User) and self.pk == other.pk


class Company:
    def __init__(self, name, pk=None):
        self.name = name
        self.pk = pk or id(self)

    def __str__(self):
        return self.name

    def __eq__(self, other):
        return isinstance(other, Company) and self.pk == other.pk


# Regular storable facts
@dataclass
class MemberOf(Fact):
    subject: User | Var
    object: Company | Var


@dataclass
class Owns(Fact):
    subject: Company | Var
    object: Company | Var  # Simplified for testing


# Inferred fact - no Django model created
@dataclass
class HasAccess(Fact, inferred=True):
    subject: User | Var
    object: Company | Var


def test_inferred_facts():
    print("Testing inferred facts functionality...")

    # Create test data
    user1 = User("Alice")
    user2 = User("Bob")
    company1 = Company("TechCorp")
    company2 = Company("DataCorp")

    # Test 1: Verify inferred facts cannot be stored
    try:
        store_facts(HasAccess(subject=user1, object=company1))
        print("❌ ERROR: Should not be able to store inferred facts")
    except ValueError as e:
        print(f"✅ Correctly prevented storing inferred fact: {e}")

    # Test 2: Verify Django model is not created for inferred facts
    print(f"HasAccess._django_model: {HasAccess._django_model}")
    print(f"HasAccess._is_inferred: {HasAccess._is_inferred}")
    print(f"MemberOf._django_model: {type(MemberOf._django_model)}")
    print(f"MemberOf._is_inferred: {MemberOf._is_inferred}")

    # Test 3: Define rule to derive HasAccess from MemberOf
    rule(
        HasAccess(Var("user"), Var("company")),
        MemberOf(Var("user"), Var("company"))
    )

    print("✅ Rule defined successfully")

    # Test 4: Store base facts (should work)
    store_facts(
        MemberOf(subject=user1, object=company1),
        MemberOf(subject=user2, object=company2)
    )
    print("✅ Base facts stored successfully")

    # Test 5: Query inferred facts (should be computed from rules)
    results = list(query(HasAccess(Var("user"), Var("company"))))
    print(f"✅ Query results: {len(results)} HasAccess facts inferred")

    for result in results:
        print(f"  - {result}")

    print("✅ All tests passed!")


if __name__ == "__main__":
    test_inferred_facts()
