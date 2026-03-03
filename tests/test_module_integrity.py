"""Test module integrity check (circular dependencies, tier violations)"""

from core.dependency_validator import DependencyValidator, CircularDependencyError, TierViolationError
from core.indexer import ProjectIndexer
import json

TARGET_PROJECT_PATH = r"D:\codeWorks\graphicstics\graphicstuff"

def test_dependency_validator_initialization():
    """Test that dependency validator initializes correctly"""
    print("\n" + "="*60)
    print("TEST 1: Dependency Validator Initialization")
    print("="*60)
    
    indexer = ProjectIndexer(TARGET_PROJECT_PATH)
    indexer.index_project()
    
    with open("policy/tier_policy.json", 'r') as f:
        tier_policy = json.load(f)
    
    validator = DependencyValidator(indexer, tier_policy)
    
    print(f"PASS Validator initialized")
    print(f"  Tier mappings: {len(validator.file_to_tier)} prefixes")
    
    indexer.close()
    return True

def test_module_integrity_validation():
    """Test module integrity validation on actual files"""
    print("\n" + "="*60)
    print("TEST 2: Module Integrity Validation")
    print("="*60)
    
    indexer = ProjectIndexer(TARGET_PROJECT_PATH)
    indexer.index_project()
    
    with open("policy/tier_policy.json", 'r') as f:
        tier_policy = json.load(f)
    
    validator = DependencyValidator(indexer, tier_policy)
    
    # Test with main.cpp (should pass - no circular deps)
    modified_files = {"main.cpp"}
    is_valid, issues = validator.validate_module_integrity(modified_files)
    
    print(f"Validating: {modified_files}")
    print(f"Result: {'VALID' if is_valid else 'INVALID'}")
    
    if issues:
        print(f"Issues found:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print(f"PASS No issues found")
    
    indexer.close()
    return is_valid

def test_tier_level_mapping():
    """Test tier level mapping"""
    print("\n" + "="*60)
    print("TEST 3: Tier Level Mapping")
    print("="*60)
    
    indexer = ProjectIndexer(TARGET_PROJECT_PATH)
    
    with open("policy/tier_policy.json", 'r') as f:
        tier_policy = json.load(f)
    
    validator = DependencyValidator(indexer, tier_policy)
    
    # Test tier mappings
    test_cases = [
        ("engine/physics/test.cpp", 0),
        ("engine/public/test.cpp", 1),
        ("crypto/test.cpp", 2),
        ("unknown/test.cpp", 0),  # Default to tier0
    ]
    
    all_correct = True
    for file_path, expected_tier in test_cases:
        actual_tier = validator._get_file_tier(file_path)
        status = "PASS" if actual_tier == expected_tier else "FAIL"
        print(f"{status} {file_path} -> tier{actual_tier} (expected tier{expected_tier})")
        if actual_tier != expected_tier:
            all_correct = False
    
    indexer.close()
    return all_correct

def test_circular_dependency_detection():
    """Test circular dependency detection logic"""
    print("\n" + "="*60)
    print("TEST 4: Circular Dependency Detection (Logic)")
    print("="*60)
    
    indexer = ProjectIndexer(TARGET_PROJECT_PATH)
    
    with open("policy/tier_policy.json", 'r') as f:
        tier_policy = json.load(f)
    
    validator = DependencyValidator(indexer, tier_policy)
    
    # Create a mock circular dependency graph
    # A -> B -> C -> A (cycle)
    mock_graph = {
        "A.cpp": ["B.cpp"],
        "B.cpp": ["C.cpp"],
        "C.cpp": ["A.cpp"]
    }
    
    visited = set()
    rec_stack = set()
    path = []
    
    try:
        validator._has_cycle_dfs("A.cpp", mock_graph, visited, rec_stack, path)
        print("FAIL Circular dependency NOT detected (should have been)")
        indexer.close()
        return False
    except CircularDependencyError as e:
        print(f"PASS Circular dependency detected: {e}")
        indexer.close()
        return True

def main():
    print("\n" + "#"*60)
    print("# MODULE INTEGRITY CHECK TEST SUITE")
    print("#"*60)
    
    results = {}
    
    try:
        results['Validator Init'] = test_dependency_validator_initialization()
    except Exception as e:
        print(f"FAIL Exception: {e}")
        import traceback
        traceback.print_exc()
        results['Validator Init'] = False
    
    try:
        results['Module Validation'] = test_module_integrity_validation()
    except Exception as e:
        print(f"FAIL Exception: {e}")
        import traceback
        traceback.print_exc()
        results['Module Validation'] = False
    
    try:
        results['Tier Mapping'] = test_tier_level_mapping()
    except Exception as e:
        print(f"FAIL Exception: {e}")
        import traceback
        traceback.print_exc()
        results['Tier Mapping'] = False
    
    try:
        results['Circular Detection'] = test_circular_dependency_detection()
    except Exception as e:
        print(f"FAIL Exception: {e}")
        import traceback
        traceback.print_exc()
        results['Circular Detection'] = False
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, success in results.items():
        status = "PASS PASS" if success else "FAIL FAIL"
        print(f"{status} - {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    print("#"*60)
    
    return all(results.values())

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)


