"""
Symbol-Level Dependency Validator
Validates symbol usage: function calls, variable references, undefined symbols
"""

import re
from typing import Set, List, Tuple, Dict, Optional, Any


class UndefinedSymbolError(Exception):
    """Raised when undefined symbol is detected"""
    pass


class UnusedSymbolWarning(Exception):
    """Raised when unused symbol is detected"""
    pass


class SymbolValidator:
    """Validates symbol-level dependencies and usage"""
    
    # Patterns for detecting symbol usage
    FUNCTION_CALL_PATTERN = re.compile(r'\b(\w+)\s*\(')
    VARIABLE_USAGE_PATTERN = re.compile(r'\b(\w+)\b')
    
    # C++ keywords to exclude from symbol checks
    CPP_KEYWORDS = {
        'if', 'else', 'while', 'for', 'do', 'switch', 'case', 'default',
        'break', 'continue', 'return', 'goto', 'try', 'catch', 'throw',
        'class', 'struct', 'enum', 'union', 'namespace', 'using',
        'public', 'private', 'protected', 'virtual', 'override', 'final',
        'static', 'const', 'constexpr', 'volatile', 'mutable',
        'int', 'char', 'float', 'double', 'void', 'bool', 'long', 'short',
        'unsigned', 'signed', 'auto', 'decltype', 'typename', 'template',
        'new', 'delete', 'this', 'nullptr', 'true', 'false',
        'sizeof', 'alignof', 'typeid', 'static_cast', 'dynamic_cast',
        'const_cast', 'reinterpret_cast', 'operator', 'friend', 'typedef',
        'explicit', 'inline', 'extern', 'register', 'asm', 'export'
    }
    
    def __init__(self, indexer):
        self.indexer = indexer
    
    def validate_symbol_usage(
        self,
        modified_files: Set[str],
        check_undefined: bool = True,
        check_unused: bool = False
    ) -> Tuple[bool, List[str]]:
        """
        Validate symbol usage in modified files
        
        Args:
            modified_files: Set of modified file paths
            check_undefined: Check for undefined symbols
            check_unused: Check for unused symbols (warning only)
        
        Returns:
            (is_valid, issues) - True if valid, list of issue descriptions
        """
        issues = []
        
        if check_undefined:
            undefined_issues = self._check_undefined_symbols(modified_files)
            issues.extend(undefined_issues)
        
        if check_unused:
            unused_issues = self._check_unused_symbols(modified_files)
            # Unused symbols are warnings, not errors
            issues.extend([f"Warning: {issue}" for issue in unused_issues])
        
        return (len([i for i in issues if not i.startswith("Warning:")]) == 0, issues)
    
    def _check_undefined_symbols(self, modified_files: Set[str]) -> List[str]:
        """
        Check for undefined symbols (function calls to non-existent functions)
        
        Returns:
            List of undefined symbol issues
        """
        issues = []
        
        for file_path in modified_files:
            # Get all symbols used in this file
            used_symbols = self._extract_used_symbols(file_path)
            
            # Get all symbols defined in project
            defined_symbols = self._get_all_defined_symbols()
            
            # Get symbols accessible from this file (via includes)
            accessible_symbols = self._get_accessible_symbols(file_path)
            
            # Check for undefined symbols
            for symbol in used_symbols:
                if symbol in self.CPP_KEYWORDS:
                    continue
                
                # Check if symbol is defined anywhere
                if symbol not in defined_symbols:
                    # Could be from standard library or external
                    # Only flag if it looks like a user-defined symbol
                    if self._looks_like_user_symbol(symbol):
                        issues.append(
                            f"Undefined symbol '{symbol}' in {file_path}"
                        )
                elif symbol not in accessible_symbols:
                    # Symbol exists but not accessible from this file
                    issues.append(
                        f"Symbol '{symbol}' used in {file_path} but not accessible "
                        f"(missing include or forward declaration)"
                    )
        
        return issues
    
    def _check_unused_symbols(self, modified_files: Set[str]) -> List[str]:
        """
        Check for unused symbols (defined but never called)
        
        Returns:
            List of unused symbol warnings
        """
        warnings = []
        
        for file_path in modified_files:
            # Get symbols defined in this file
            defined_symbols = self._get_symbols_in_file(file_path)
            
            # Get all symbol usages in project
            all_usages = self._get_all_symbol_usages()
            
            for symbol_name, symbol_type in defined_symbols:
                if symbol_type == 'function':
                    # Check if function is ever called
                    if symbol_name not in all_usages:
                        # Exclude main and special functions
                        if symbol_name not in ['main', 'WinMain', 'DllMain']:
                            warnings.append(
                                f"Unused function '{symbol_name}' in {file_path}"
                            )
        
        return warnings
    
    def _extract_used_symbols(self, file_path: str) -> Set[str]:
        """
        Extract all symbols used in a file (function calls, variable refs)
        
        Returns:
            Set of symbol names
        """
        used_symbols = set()
        
        full_path = self.indexer.project_root + "/" + file_path
        
        try:
            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # Remove comments
            content = self._remove_comments(content)
            
            # Remove string literals
            content = self._remove_strings(content)
            
            # Extract function calls
            for match in self.FUNCTION_CALL_PATTERN.finditer(content):
                symbol = match.group(1)
                if symbol and not symbol.startswith('_'):
                    used_symbols.add(symbol)
            
        except Exception as e:
            # File read error - skip
            pass
        
        return used_symbols
    
    def _get_all_defined_symbols(self) -> Set[str]:
        """Get all symbols defined in the project"""
        cursor = self.indexer.conn.cursor()
        cursor.execute("SELECT DISTINCT name FROM symbols")
        return {row[0] for row in cursor.fetchall()}
    
    def _get_symbols_in_file(self, file_path: str) -> List[Tuple[str, str]]:
        """Get symbols defined in a specific file"""
        cursor = self.indexer.conn.cursor()
        cursor.execute(
            "SELECT name, type FROM symbols WHERE file = ?",
            (file_path,)
        )
        return cursor.fetchall()
    
    def _get_accessible_symbols(self, file_path: str) -> Set[str]:
        """
        Get symbols accessible from a file (defined in file or included files)
        
        Returns:
            Set of accessible symbol names
        """
        accessible = set()
        
        # Symbols defined in this file
        cursor = self.indexer.conn.cursor()
        cursor.execute(
            "SELECT name FROM symbols WHERE file = ?",
            (file_path,)
        )
        accessible.update(row[0] for row in cursor.fetchall())
        
        # Symbols from included files
        includes = self._get_file_includes_recursive(file_path)
        for included_file in includes:
            cursor.execute(
                "SELECT name FROM symbols WHERE file = ?",
                (included_file,)
            )
            accessible.update(row[0] for row in cursor.fetchall())
        
        return accessible
    
    def _get_file_includes_recursive(
        self,
        file_path: str,
        visited: Optional[Set[str]] = None
    ) -> Set[str]:
        """
        Get all files included by this file (recursively)
        
        Returns:
            Set of included file paths
        """
        if visited is None:
            visited = set()
        
        if file_path in visited:
            return set()
        
        visited.add(file_path)
        includes = set()
        
        cursor = self.indexer.conn.cursor()
        cursor.execute(
            "SELECT included_file FROM includes WHERE source_file = ?",
            (file_path,)
        )
        
        for row in cursor.fetchall():
            included = row[0]
            
            # Try to resolve to actual file
            resolved = self._resolve_include(included)
            if resolved:
                includes.add(resolved)
                # Recursively get includes from this file
                includes.update(
                    self._get_file_includes_recursive(resolved, visited)
                )
        
        return includes
    
    def _resolve_include(self, include_path: str) -> Optional[str]:
        """Resolve include path to actual file in index"""
        cursor = self.indexer.conn.cursor()
        
        # Try exact match
        cursor.execute("SELECT path FROM files WHERE path = ?", (include_path,))
        result = cursor.fetchone()
        if result:
            return result[0]
        
        # Try matching filename
        import os
        filename = os.path.basename(include_path)
        cursor.execute("SELECT path FROM files WHERE path LIKE ?", (f"%{filename}",))
        result = cursor.fetchone()
        if result:
            return result[0]
        
        return None
    
    def _get_all_symbol_usages(self) -> Set[str]:
        """
        Get all symbols used anywhere in the project
        
        Returns:
            Set of used symbol names
        """
        all_usages = set()
        
        cursor = self.indexer.conn.cursor()
        cursor.execute("SELECT path FROM files")
        
        for row in cursor.fetchall():
            file_path = row[0]
            usages = self._extract_used_symbols(file_path)
            all_usages.update(usages)
        
        return all_usages
    
    def _looks_like_user_symbol(self, symbol: str) -> bool:
        """
        Check if symbol looks like a user-defined symbol
        (vs standard library or compiler intrinsic)
        
        Returns:
            True if likely user-defined
        """
        # Standard library prefixes
        std_prefixes = ['std', 'std_', '__', '_']
        
        for prefix in std_prefixes:
            if symbol.startswith(prefix):
                return False
        
        # Common external library prefixes (OpenGL, GLFW, etc.)
        external_prefixes = ['gl', 'glfw', 'glad', 'GL', 'GLFW', 'GLAD']
        
        for prefix in external_prefixes:
            if symbol.startswith(prefix):
                return False
        
        # Common standard library functions
        std_functions = {
            'printf', 'scanf', 'malloc', 'free', 'memcpy', 'memset',
            'strlen', 'strcpy', 'strcmp', 'strcat', 'atoi', 'atof',
            'exit', 'abort', 'assert', 'sizeof'
        }
        
        if symbol in std_functions:
            return False
        
        return True
    
    def _remove_comments(self, content: str) -> str:
        """Remove C++ comments from content"""
        # Remove single-line comments
        content = re.sub(r'//.*?$', '', content, flags=re.MULTILINE)
        # Remove multi-line comments
        content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
        return content
    
    def _remove_strings(self, content: str) -> str:
        """Remove string literals from content"""
        # Remove double-quoted strings
        content = re.sub(r'"(?:[^"\\]|\\.)*"', '""', content)
        # Remove single-quoted chars
        content = re.sub(r"'(?:[^'\\]|\\.)*'", "''", content)
        return content
    
    def get_symbol_info(self, symbol_name: str) -> List[Dict[str, Any]]:
        """
        Get information about a symbol
        
        Returns:
            List of symbol definitions with file, line, type
        """
        cursor = self.indexer.conn.cursor()
        cursor.execute(
            "SELECT file, line, type FROM symbols WHERE name = ?",
            (symbol_name,)
        )
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'file': row[0],
                'line': row[1],
                'type': row[2]
            })
        
        return results
    
    def build_call_graph(self, file_path: str) -> Dict[str, List[str]]:
        """
        Build a call graph for functions in a file
        
        Returns:
            Dict mapping function names to list of called functions
        """
        call_graph = {}
        
        # Get functions defined in this file
        functions = self._get_symbols_in_file(file_path)
        
        full_path = self.indexer.project_root + "/" + file_path
        
        try:
            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            
            current_function = None
            brace_depth = 0
            
            for line_num, line in enumerate(lines, start=1):
                # Check if we're entering a function
                for func_name, func_type in functions:
                    if func_type == 'function' and func_name in line and '(' in line:
                        # Check if this is the function definition
                        cursor = self.indexer.conn.cursor()
                        cursor.execute(
                            "SELECT line FROM symbols WHERE name = ? AND file = ? AND type = 'function'",
                            (func_name, file_path)
                        )
                        result = cursor.fetchone()
                        if result and result[0] == line_num:
                            current_function = func_name
                            call_graph[func_name] = []
                            brace_depth = 0
                
                # Track brace depth
                brace_depth += line.count('{') - line.count('}')
                
                # If we're inside a function, track calls
                if current_function and brace_depth > 0:
                    # Extract function calls
                    for match in self.FUNCTION_CALL_PATTERN.finditer(line):
                        called_func = match.group(1)
                        if called_func != current_function and called_func not in self.CPP_KEYWORDS:
                            if called_func not in call_graph[current_function]:
                                call_graph[current_function].append(called_func)
                
                # If we've exited the function
                if current_function and brace_depth == 0:
                    current_function = None
        
        except Exception as e:
            pass
        
        return call_graph
