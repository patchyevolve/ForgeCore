"""Run all ForgeCore tests"""

import subprocess
import sys
import os
import glob

# Add parent directory to path so tests can import core modules
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(TEST_DIR)
sys.path.insert(0, PARENT_DIR)

# Auto-discover all test files in the tests directory
TEST_FILES = sorted([
    os.path.basename(f) for f in glob.glob(os.path.join(TEST_DIR, "test_*.py"))
])

def run_test(test_file):
    """Run a single test file"""
    print("\n" + "="*70)
    print(f"RUNNING: {test_file}")
    print("="*70)
    
    test_path = os.path.join(TEST_DIR, test_file)
    
    try:
        # Set PYTHONPATH to include parent directory
        env = os.environ.copy()
        env['PYTHONPATH'] = PARENT_DIR + os.pathsep + env.get('PYTHONPATH', '')
        # Disable LLM for tests to speed them up
        env['FORGECORE_USE_LLM'] = 'false'
        
        result = subprocess.run(
            [sys.executable, test_path],
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
            cwd=PARENT_DIR  # Run from parent directory
        )
        
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print(f"FAIL TIMEOUT - {test_file} took too long")
        return False
    except Exception as e:
        print(f"FAIL ERROR - {e}")
        return False

def cleanup_between_tests():
    """Clean up test artifacts between test suites"""
    print("\n" + "-"*70)
    print("CLEANUP BETWEEN TESTS")
    print("-"*70)
    try:
        import cleanup_test_artifacts
        cleanup_test_artifacts.clean_main_cpp()
        print("✓ Cleanup complete")
        # Add a small delay to ensure file handles are released
        import time
        time.sleep(0.5)
    except Exception as e:
        print(f"Cleanup failed: {e}")

def main():
    print("\n" + "#"*70)
    print("# FORGECORE COMPREHENSIVE TEST SUITE")
    print("#"*70)
    print(f"\nRunning {len(TEST_FILES)} test suites...\n")
    
    # Clean up test artifacts before running tests
    print("="*70)
    print("CLEANING TEST ARTIFACTS")
    print("="*70)
    try:
        # Import from parent directory
        import cleanup_test_artifacts
        cleanup_test_artifacts.clean_main_cpp()
        print("Cleanup complete\n")
    except Exception as e:
        print(f"Warning: Cleanup failed: {e}\n")
    
    results = {}
    
    for i, test_file in enumerate(TEST_FILES):
        success = run_test(test_file)
        results[test_file] = success
        
        # Clean up between tests (except after the last test)
        if i < len(TEST_FILES) - 1:
            cleanup_between_tests()
    
    # Summary
    print("\n" + "="*70)
    print("FINAL SUMMARY")
    print("="*70)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_file, success in results.items():
        status = "PASS" if success else "FAIL"
        print(f"{status} - {test_file}")
    
    print(f"\nTotal: {passed}/{total} test suites passed")
    print(f"Pass rate: {passed/total*100:.1f}%")
    
    if all(results.values()):
        print("\n" + "="*70)
        print("ALL TESTS PASSED!")
        print("="*70)
    else:
        print("\nWARN: Some tests failed. Review output above.")
    
    print("\n" + "#"*70)
    
    return all(results.values())

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
