"""
Call Graph Integrity Analyzer
Validates call graph integrity: dead code, unreachable functions, recursion
"""

from typing import Set, List, Dict, Tuple, Optional


class DeadCodeError(Exception):
    """Raised when dead code is detected"""
    pass


class RecursionError(Exception):
    """Raised when problematic recursion is detected"""
    pass


class CallGraphAnalyzer:
    """Analyzes call graph for integrity issues"""
    
    def __init__(self, symbol_validator):
        self.symbol_validator = symbol_validator
        self.indexer = symbol_validator.indexer
    
    def validate_call_graph_integrity(
        self,
        modified_files: Set[str],
        check_dead_code: bool = True,
        check_recursion: bool = True,
        check_unreachable: bool = True
    ) -> Tuple[bool, List[str]]:
        """
        Validate call graph integrity
        
        Args:
            modified_files: Set of modified file paths
            check_dead_code: Check for dead code
            check_recursion: Check for recursion issues
            check_unreachable: Check for unreachable functions
        
        Returns:
            (is_valid, issues) - True if valid, list of issue descriptions
        """
        issues = []
        
        # Build call graph for modified files
        call_graphs = {}
        for file_path in modified_files:
            call_graphs[file_path] = self.symbol_validator.build_call_graph(file_path)
        
        if check_dead_code:
            dead_code_issues = self._check_dead_code(modified_files, call_graphs)
            issues.extend(dead_code_issues)
        
        if check_recursion:
            recursion_issues = self._check_recursion(modified_files, call_graphs)
            issues.extend(recursion_issues)
        
        if check_unreachable:
            unreachable_issues = self._check_unreachable_code(modified_files, call_graphs)
            issues.extend(unreachable_issues)
        
        return (len(issues) == 0, issues)
    
    def _check_dead_code(
        self,
        modified_files: Set[str],
        call_graphs: Dict[str, Dict[str, List[str]]]
    ) -> List[str]:
        """
        Check for dead code (functions never called)
        
        Returns:
            List of dead code warnings
        """
        warnings = []
        
        # Get all functions defined in modified files
        defined_functions = set()
        for file_path in modified_files:
            symbols = self.symbol_validator._get_symbols_in_file(file_path)
            for symbol_name, symbol_type in symbols:
                if symbol_type == 'function':
                    defined_functions.add((symbol_name, file_path))
        
        # Get all function calls in the project
        all_calls = self._get_all_function_calls()
        
        # Check for functions that are never called
        for func_name, file_path in defined_functions:
            # Skip entry points and special functions
            if func_name in ['main', 'WinMain', 'DllMain', 'wmain']:
                continue
            
            # Skip constructors/destructors (simple heuristic)
            if func_name.startswith('~') or func_name[0].isupper():
                continue
            
            if func_name not in all_calls:
                warnings.append(
                    f"Warning: Dead code - function '{func_name}' in {file_path} is never called"
                )
        
        return warnings
    
    def _check_recursion(
        self,
        modified_files: Set[str],
        call_graphs: Dict[str, Dict[str, List[str]]]
    ) -> List[str]:
        """
        Check for recursion issues
        
        Returns:
            List of recursion issues
        """
        issues = []
        
        for file_path, call_graph in call_graphs.items():
            for func_name, called_funcs in call_graph.items():
                # Check for direct recursion
                if func_name in called_funcs:
                    issues.append(
                        f"Direct recursion detected: '{func_name}' in {file_path} calls itself"
                    )
                
                # Check for indirect recursion (cycles in call graph)
                cycle = self._find_recursion_cycle(func_name, call_graph)
                if cycle:
                    cycle_str = " → ".join(cycle)
                    issues.append(
                        f"Indirect recursion detected in {file_path}: {cycle_str}"
                    )
        
        return issues
    
    def _check_unreachable_code(
        self,
        modified_files: Set[str],
        call_graphs: Dict[str, Dict[str, List[str]]]
    ) -> List[str]:
        """
        Check for unreachable code (functions not reachable from entry points)
        
        Returns:
            List of unreachable code warnings
        """
        warnings = []
        
        # Find entry points (main, etc.)
        entry_points = self._find_entry_points(modified_files)
        
        if not entry_points:
            # No entry points in modified files, skip check
            return warnings
        
        # Build reachability set from entry points
        reachable = set()
        for entry_point, file_path in entry_points:
            if file_path in call_graphs:
                self._mark_reachable(
                    entry_point,
                    call_graphs[file_path],
                    reachable,
                    visited=set()
                )
        
        # Check for unreachable functions
        for file_path, call_graph in call_graphs.items():
            for func_name in call_graph.keys():
                if func_name not in reachable:
                    # Skip special functions
                    if func_name in ['main', 'WinMain', 'DllMain']:
                        continue
                    
                    warnings.append(
                        f"Warning: Unreachable code - function '{func_name}' in {file_path} "
                        f"is not reachable from any entry point"
                    )
        
        return warnings
    
    def _get_all_function_calls(self) -> Set[str]:
        """
        Get all function calls in the entire project
        
        Returns:
            Set of called function names
        """
        all_calls = set()
        
        cursor = self.indexer.conn.cursor()
        cursor.execute("SELECT path FROM files")
        
        for row in cursor.fetchall():
            file_path = row[0]
            call_graph = self.symbol_validator.build_call_graph(file_path)
            
            # Add all called functions
            for called_funcs in call_graph.values():
                all_calls.update(called_funcs)
        
        return all_calls
    
    def _find_recursion_cycle(
        self,
        func_name: str,
        call_graph: Dict[str, List[str]],
        path: Optional[List[str]] = None,
        visited: Optional[Set[str]] = None
    ) -> Optional[List[str]]:
        """
        Find recursion cycle starting from func_name
        
        Returns:
            List representing cycle, or None if no cycle
        """
        if path is None:
            path = []
        if visited is None:
            visited = set()
        
        if func_name in path:
            # Found cycle
            cycle_start = path.index(func_name)
            return path[cycle_start:] + [func_name]
        
        if func_name in visited:
            return None
        
        visited.add(func_name)
        path.append(func_name)
        
        # Check all called functions
        if func_name in call_graph:
            for called_func in call_graph[func_name]:
                if called_func in call_graph:  # Only check functions in this file
                    cycle = self._find_recursion_cycle(
                        called_func,
                        call_graph,
                        path.copy(),
                        visited
                    )
                    if cycle:
                        return cycle
        
        return None
    
    def _find_entry_points(self, modified_files: Set[str]) -> List[Tuple[str, str]]:
        """
        Find entry points (main, WinMain, etc.) in modified files
        
        Returns:
            List of (function_name, file_path) tuples
        """
        entry_points = []
        entry_point_names = ['main', 'WinMain', 'DllMain', 'wmain']
        
        for file_path in modified_files:
            symbols = self.symbol_validator._get_symbols_in_file(file_path)
            for symbol_name, symbol_type in symbols:
                if symbol_type == 'function' and symbol_name in entry_point_names:
                    entry_points.append((symbol_name, file_path))
        
        return entry_points
    
    def _mark_reachable(
        self,
        func_name: str,
        call_graph: Dict[str, List[str]],
        reachable: Set[str],
        visited: Set[str]
    ):
        """
        Mark all functions reachable from func_name
        
        Args:
            func_name: Starting function
            call_graph: Call graph for the file
            reachable: Set to add reachable functions to
            visited: Set of already visited functions
        """
        if func_name in visited:
            return
        
        visited.add(func_name)
        reachable.add(func_name)
        
        # Mark all called functions as reachable
        if func_name in call_graph:
            for called_func in call_graph[func_name]:
                self._mark_reachable(called_func, call_graph, reachable, visited)
    
    def analyze_call_depth(
        self,
        file_path: str,
        func_name: str,
        max_depth: int = 100
    ) -> Tuple[int, List[str]]:
        """
        Analyze maximum call depth from a function
        
        Args:
            file_path: File containing the function
            func_name: Function to analyze
            max_depth: Maximum depth to check
        
        Returns:
            (max_depth, deepest_path) - Maximum depth and path to deepest call
        """
        call_graph = self.symbol_validator.build_call_graph(file_path)
        
        if func_name not in call_graph:
            return (0, [func_name])
        
        max_depth_found = 0
        deepest_path = [func_name]
        
        def dfs(current_func: str, depth: int, path: List[str]):
            nonlocal max_depth_found, deepest_path
            
            if depth > max_depth:
                return  # Prevent infinite recursion
            
            if depth > max_depth_found:
                max_depth_found = depth
                deepest_path = path.copy()
            
            if current_func in call_graph:
                for called_func in call_graph[current_func]:
                    if called_func not in path:  # Avoid cycles
                        dfs(called_func, depth + 1, path + [called_func])
        
        dfs(func_name, 0, [func_name])
        
        return (max_depth_found, deepest_path)
    
    def get_call_chain(
        self,
        from_func: str,
        to_func: str,
        file_path: str
    ) -> Optional[List[str]]:
        """
        Find call chain from one function to another
        
        Args:
            from_func: Starting function
            to_func: Target function
            file_path: File containing the functions
        
        Returns:
            List representing call chain, or None if no path exists
        """
        call_graph = self.symbol_validator.build_call_graph(file_path)
        
        if from_func not in call_graph:
            return None
        
        # BFS to find shortest path
        from collections import deque
        
        queue = deque([(from_func, [from_func])])
        visited = {from_func}
        
        while queue:
            current_func, path = queue.popleft()
            
            if current_func == to_func:
                return path
            
            if current_func in call_graph:
                for called_func in call_graph[current_func]:
                    if called_func not in visited:
                        visited.add(called_func)
                        queue.append((called_func, path + [called_func]))
        
        return None
    
    def get_call_graph_stats(self, file_path: str) -> Dict[str, any]:
        """
        Get statistics about the call graph
        
        Returns:
            Dictionary with call graph statistics
        """
        call_graph = self.symbol_validator.build_call_graph(file_path)
        
        total_functions = len(call_graph)
        total_calls = sum(len(calls) for calls in call_graph.values())
        
        # Find functions with most calls
        most_calls = sorted(
            call_graph.items(),
            key=lambda x: len(x[1]),
            reverse=True
        )[:5]
        
        # Find functions called most often
        call_counts = {}
        for called_funcs in call_graph.values():
            for func in called_funcs:
                call_counts[func] = call_counts.get(func, 0) + 1
        
        most_called = sorted(
            call_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]
        
        return {
            'total_functions': total_functions,
            'total_calls': total_calls,
            'avg_calls_per_function': total_calls / total_functions if total_functions > 0 else 0,
            'functions_with_most_calls': most_calls,
            'most_called_functions': most_called
        }
