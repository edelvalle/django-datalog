#!/usr/bin/env python3
"""
Simple test for FactConjunction functionality.
"""

import os
import sys

# Add the current directory to the path for importing django_datalog
sys.path.insert(0, ".")

# Configure Django settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "test_project.testsite.settings")

# Setup Django
import django
django.setup()

from dataclasses import dataclass

from django_datalog.facts import Fact, FactConjunction
from django_datalog.variables import Var


@dataclass
class TestFact(Fact, inferred=True):
    subject: str | Var
    object: str | Var


def test_fact_conjunction():
    """Test that FactConjunction works properly."""
    
    # Create some test facts
    fact1 = TestFact(subject="A", object="B")
    fact2 = TestFact(subject="B", object="C")
    fact3 = TestFact(subject="C", object="D")
    
    # Test & operator creates FactConjunction
    conjunction = fact1 & fact2
    print(f"fact1 & fact2 = {conjunction}")
    print(f"Type: {type(conjunction)}")
    print(f"Is FactConjunction: {isinstance(conjunction, FactConjunction)}")
    print(f"Is tuple: {isinstance(conjunction, tuple)}")
    print(f"Length: {len(conjunction)}")
    print()
    
    # Test chaining & operators
    triple_conjunction = fact1 & fact2 & fact3
    print(f"fact1 & fact2 & fact3 = {triple_conjunction}")
    print(f"Type: {type(triple_conjunction)}")
    print(f"Length: {len(triple_conjunction)}")
    print()
    
    # Test | operator with FactConjunction
    disjunction = fact1 | conjunction
    print(f"fact1 | (fact1 & fact2) = {disjunction}")
    print(f"Type: {type(disjunction)}")
    print()
    
    # Test that FactConjunction behaves like a tuple
    print("FactConjunction behaves like a tuple:")
    print(f"conjunction[0] = {conjunction[0]}")
    print(f"conjunction[1] = {conjunction[1]}")
    print(f"list(conjunction) = {list(conjunction)}")
    print()
    
    # Test FactConjunction operators
    print("Testing FactConjunction operators:")
    
    # Test FactConjunction | Fact
    conj_or_fact = conjunction | fact3
    print(f"(fact1 & fact2) | fact3 = {conj_or_fact}")
    print(f"Type: {type(conj_or_fact)}")
    print()
    
    # Test FactConjunction & Fact
    conj_and_fact = conjunction & fact3
    print(f"(fact1 & fact2) & fact3 = {conj_and_fact}")
    print(f"Type: {type(conj_and_fact)}")
    print(f"Length: {len(conj_and_fact)}")
    print()
    
    # Test Fact | FactConjunction (reverse)
    fact_or_conj = fact3 | conjunction
    print(f"fact3 | (fact1 & fact2) = {fact_or_conj}")
    print(f"Type: {type(fact_or_conj)}")
    print()
    
    # Test FactConjunction & FactConjunction
    another_conjunction = fact2 & fact3
    conj_and_conj = conjunction & another_conjunction
    print(f"(fact1 & fact2) & (fact2 & fact3) = {conj_and_conj}")
    print(f"Type: {type(conj_and_conj)}")
    print(f"Length: {len(conj_and_conj)}")
    print()
    
    print("✅ FactConjunction tests passed!")


if __name__ == "__main__":
    test_fact_conjunction()