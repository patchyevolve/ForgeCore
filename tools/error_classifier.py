"""
Enhanced Error Classifier - Multi-language error parsing
"""

import re
from typing import List, Dict, Any


class BuildErrorClassifier:
    """
    Classifies build/validation errors from multiple languages and tools.
    """
    
    # C++ MSVC/Clang error pattern
    CPP_PATTERN = re.compile(
        r'^(?P<file>.+)\((?P<line>\d+),(?P<column>\d+)\):\s+'
        r'(?P<level>error|warning)\s+'
        r'(?P<code>[A-Z0-9]+):\s+'
        r'(?P<message>.+)$'
    )
    
    # GCC/Clang error pattern
    GCC_PATTERN = re.compile(
        r'^(?P<file>.+):(?P<line>\d+):(?P<column>\d+):\s+'
        r'(?P<level>error|warning):\s+'
        r'(?P<message>.+)$'
    )
    
    # Python error pattern
    PYTHON_PATTERN = re.compile(
        r'File "(?P<file>.+)", line (?P<line>\d+)'
    )
    
    # JavaScript/Node error pattern
    JS_PATTERN = re.compile(
        r'^(?P<file>.+):(?P<line>\d+):(?P<column>\d+)\s+-\s+'
        r'(?P<level>error|warning):\s+'
        r'(?P<message>.+)$'
    )
    
    # Rust cargo error pattern
    RUST_PATTERN = re.compile(
        r'^(?P<level>error|warning)(?:\[(?P<code>[^\]]+)\])?\s*:\s*(?P<message>.+)$'
    )
    
    # Error type mappings
    ERROR_TYPES = {
        # C++ errors
        'C2065': 'UNDEFINED_SYMBOL',
        'C2146': 'SYNTAX_ERROR',
        'C2059': 'SYNTAX_ERROR',
        'C2143': 'SYNTAX_ERROR',
        'C2061': 'SYNTAX_ERROR',
        'C2660': 'TYPE_MISMATCH',
        'C2664': 'TYPE_MISMATCH',
        'C2679': 'TYPE_MISMATCH',
        'C2039': 'MISSING_MEMBER',
        'C2027': 'UNDEFINED_TYPE',
        'C1083': 'MISSING_INCLUDE',
        'LNK': 'LINKER_ERROR',
        
        # Python errors
        'SyntaxError': 'SYNTAX_ERROR',
        'NameError': 'UNDEFINED_SYMBOL',
        'TypeError': 'TYPE_MISMATCH',
        'ImportError': 'MISSING_INCLUDE',
        'AttributeError': 'MISSING_MEMBER',
        'IndentationError': 'SYNTAX_ERROR',
        
        # JavaScript errors
        'SyntaxError': 'SYNTAX_ERROR',
        'ReferenceError': 'UNDEFINED_SYMBOL',
        'TypeError': 'TYPE_MISMATCH',
        
        # Rust errors
        'E0425': 'UNDEFINED_SYMBOL',
        'E0433': 'MISSING_INCLUDE',
        'E0308': 'TYPE_MISMATCH',
        'E0277': 'TYPE_MISMATCH',
    }
    
    def classify(self, build_output: str) -> List[Dict[str, Any]]:
        """
        Classify errors from build output.
        
        Args:
            build_output: Raw build/validation output
            
        Returns:
            List of structured error dicts
        """
        errors = []
        
        for line in build_output.splitlines():
            line = line.strip()
            if not line:
                continue
            
            # Try each pattern
            error = (
                self._try_cpp_pattern(line) or
                self._try_gcc_pattern(line) or
                self._try_python_pattern(line, build_output) or
                self._try_js_pattern(line) or
                self._try_rust_pattern(line)
            )
            
            if error:
                errors.append(error)
        
        return errors
    
    def _try_cpp_pattern(self, line: str) -> Dict[str, Any]:
        """Try C++ MSVC/Clang pattern."""
        match = self.CPP_PATTERN.match(line)
        if match:
            data = match.groupdict()
            return {
                "file": data["file"],
                "line": int(data["line"]),
                "column": int(data["column"]),
                "level": data["level"],
                "code": data["code"],
                "message": data["message"],
                "type": self._map_error_type(data["code"])
            }
        return None
    
    def _try_gcc_pattern(self, line: str) -> Dict[str, Any]:
        """Try GCC/Clang pattern."""
        match = self.GCC_PATTERN.match(line)
        if match:
            data = match.groupdict()
            return {
                "file": data["file"],
                "line": int(data["line"]),
                "column": int(data["column"]),
                "level": data["level"],
                "message": data["message"],
                "type": self._infer_type_from_message(data["message"])
            }
        return None
    
    def _try_python_pattern(self, line: str, full_output: str) -> Dict[str, Any]:
        """Try Python error pattern."""
        match = self.PYTHON_PATTERN.search(line)
        if match:
            data = match.groupdict()
            
            # Extract error type from next lines
            error_type = "UNKNOWN"
            message = ""
            
            lines = full_output.splitlines()
            for i, l in enumerate(lines):
                if line in l and i + 1 < len(lines):
                    next_line = lines[i + 1]
                    for err_name in ['SyntaxError', 'NameError', 'TypeError', 'ImportError', 'AttributeError']:
                        if err_name in next_line:
                            error_type = self.ERROR_TYPES.get(err_name, "UNKNOWN")
                            message = next_line
                            break
            
            return {
                "file": data["file"],
                "line": int(data["line"]),
                "level": "error",
                "message": message,
                "type": error_type
            }
        return None
    
    def _try_js_pattern(self, line: str) -> Dict[str, Any]:
        """Try JavaScript/Node pattern."""
        match = self.JS_PATTERN.match(line)
        if match:
            data = match.groupdict()
            return {
                "file": data["file"],
                "line": int(data["line"]),
                "column": int(data["column"]),
                "level": data["level"],
                "message": data["message"],
                "type": self._infer_type_from_message(data["message"])
            }
        return None
    
    def _try_rust_pattern(self, line: str) -> Dict[str, Any]:
        """Try Rust cargo pattern."""
        match = self.RUST_PATTERN.match(line)
        if match:
            data = match.groupdict()
            code = data.get("code", "")
            return {
                "level": data["level"],
                "code": code,
                "message": data["message"],
                "type": self._map_error_type(code) if code else "UNKNOWN"
            }
        return None
    
    def _map_error_type(self, code: str) -> str:
        """Map error code to type."""
        if not code:
            return "UNKNOWN"
        
        # Check exact match
        if code in self.ERROR_TYPES:
            return self.ERROR_TYPES[code]
        
        # Check prefix match
        for prefix, error_type in self.ERROR_TYPES.items():
            if code.startswith(prefix):
                return error_type
        
        return "UNKNOWN"
    
    def _infer_type_from_message(self, message: str) -> str:
        """Infer error type from message content."""
        message_lower = message.lower()
        
        if any(word in message_lower for word in ['undefined', 'undeclared', 'not defined']):
            return "UNDEFINED_SYMBOL"
        
        if any(word in message_lower for word in ['syntax', 'expected', 'unexpected']):
            return "SYNTAX_ERROR"
        
        if any(word in message_lower for word in ['type', 'cannot convert', 'mismatch']):
            return "TYPE_MISMATCH"
        
        if any(word in message_lower for word in ['include', 'import', 'module', 'package']):
            return "MISSING_INCLUDE"
        
        if any(word in message_lower for word in ['member', 'attribute', 'property']):
            return "MISSING_MEMBER"
        
        if 'link' in message_lower or 'undefined reference' in message_lower:
            return "LINKER_ERROR"
        
        return "UNKNOWN"


