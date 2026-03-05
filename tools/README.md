# Tools Module Handbook

The `tools/` directory contains validation scripts and utility tools used during the execution of a task to ensure code quality and safety.

## Key Tools

- **[smart_validator.py](file:///d:/codeWorks/ForgeCore/tools/smart_validator.py)**: A language-agnostic tool that detects the programming language of a file and runs appropriate build/syntax checks.
- **[language_detector.py](file:///d:/codeWorks/ForgeCore/tools/language_detector.py)**: Utilities for identifying file types and programming languages based on extension and content.
- **[error_classifier.py](file:///d:/codeWorks/ForgeCore/tools/error_classifier.py)**: Parses build output to categorize errors (syntax, linker, etc.) for AI refinement loops.
- **[build_system_monitor.py](file:///d:/codeWorks/ForgeCore/tools/build_system_monitor.py)**: Watches for changes to build configuration files (like `CMakeLists.txt`) and triggers warnings.
- **[dispatcher.py](file:///d:/codeWorks/ForgeCore/tools/dispatcher.py)**: Internal utility for routing validation requests to the correct subsystem.

## Usage in Pipeline

Tools are generally called during the `VERIFYING` and `MODULE_INTEGRITY_CHECK` states of the controller to provide objective feedback on the generated code.
