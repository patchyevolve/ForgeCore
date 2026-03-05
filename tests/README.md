# Tests Module Handbook

The `tests/` directory contains unit and integration tests to ensure ForgeCore's stability and reliability.

## Test Structure

- **[run_all_tests.py](file:///d:/codeWorks/ForgeCore/tests/run_all_tests.py)**: Main entry point for running the entire test suite.
- **`test_*.py`**: Specialized test files covering different aspects of the system:
    - `test_controller_reuse.py`: Tests the engine's ability to handle sequential tasks.
    - `test_symbol_validation.py`: Verifies the symbol tracking logic.
    - `test_critic.py`: Mocks/Tests the critic's review capabilities.
    - `test_stagnation.py`: Ensures the system detects and breaks infinite refinement loops.

## Running Tests

To run all tests:
```bash
python tests/run_all_tests.py
```

## Writing Tests

Always ensure new features include corresponding integration tests that exercise the `TransactionContext` and at least one safety layer.
