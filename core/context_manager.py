"""
Context Manager - Smart context summarization for large codebases

Prevents token limit issues by:
1. Extracting signatures only for large files
2. Summarizing module structure
3. Including only relevant sections
4. Limiting context size
"""

import os
import re
from typing import Dict, List, Optional, Tuple


class ContextManager:
    """
    Manages context size and summarization for LLM interactions.
    """
    
    # Token limits (conservative estimates)
    MAX_TOKENS_PER_FILE = 2000  # ~8000 chars
    MAX_TOTAL_TOKENS = 8000     # ~32000 chars
    CHARS_PER_TOKEN = 4         # Average
    
    def __init__(self, indexer):
        self.indexer = indexer
    
    def get_smart_context(
        self,
        files: List[str],
        focus_file: Optional[str] = None
    ) -> Dict[str, str]:
        """
        Get smart context for files, summarizing large ones.
        
        Args:
            files: List of file paths
            focus_file: File to include in full (if small enough)
            
        Returns:
            Dict of file -> content (full or summarized)
        """
        context = {}
        total_size = 0
        max_size = self.MAX_TOTAL_TOKENS * self.CHARS_PER_TOKEN
        
        # Prioritize focus file
        if focus_file and focus_file in files:
            files = [focus_file] + [f for f in files if f != focus_file]
        
        for file in files:
            # Check if we're approaching limit
            if total_size >= max_size * 0.9:  # 90% threshold
                context[file] = "[File omitted - context limit]"
                continue
            
            # Get file content
            try:
                full_content = self._read_file(file)
                file_size = len(full_content)
                
                # Decide: full or summarized
                if file == focus_file and file_size < self.MAX_TOKENS_PER_FILE * self.CHARS_PER_TOKEN:
                    # Include focus file in full
                    context[file] = full_content
                    total_size += file_size
                
                elif file_size > self.MAX_TOKENS_PER_FILE * self.CHARS_PER_TOKEN:
                    # Summarize large file
                    summary = self._summarize_file(file, full_content)
                    context[file] = summary
                    total_size += len(summary)
                
                else:
                    # Include small file in full
                    context[file] = full_content
                    total_size += file_size
            
            except Exception as e:
                context[file] = f"[Error reading file: {e}]"
        
        return context
    
    def _read_file(self, file_path: str) -> str:
        """Read file content."""
        if self.indexer:
            full_path = os.path.join(self.indexer.project_root, file_path)
        else:
            full_path = file_path
        
        with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()
    
    def _summarize_file(self, file_path: str, content: str) -> str:
        """
        Summarize large file by extracting signatures.
        
        Returns:
            Summarized content with signatures only
        """
        ext = os.path.splitext(file_path)[1].lower()
        
        if ext in ['.cpp', '.cc', '.cxx', '.c']:
            return self._summarize_cpp(content)
        elif ext in ['.h', '.hpp', '.hxx']:
            return self._summarize_header(content)
        elif ext == '.py':
            return self._summarize_python(content)
        elif ext in ['.js', '.ts', '.jsx', '.tsx']:
            return self._summarize_javascript(content)
        else:
            # Generic summarization
            return self._summarize_generic(content)
    
    def _summarize_cpp(self, content: str) -> str:
        """Summarize C++ implementation file."""
        lines = content.splitlines()
        summary = []
        
        # Include headers
        for line in lines:
            if line.strip().startswith('#include'):
                summary.append(line)
        
        if summary:
            summary.append("")
        
        # Extract function signatures
        summary.append("// Function signatures:")
        
        in_function = False
        brace_count = 0
        
        for line in lines:
            stripped = line.strip()
            
            # Skip includes and comments
            if stripped.startswith('#') or stripped.startswith('//'):
                continue
            
            # Detect function definition
            if not in_function and '(' in line and '{' in line:
                # Single-line function start
                summary.append(line.split('{')[0].strip() + ';')
                in_function = True
                brace_count = line.count('{') - line.count('}')
            
            elif not in_function and '(' in line:
                # Multi-line function start
                summary.append(line)
                in_function = True
            
            elif in_function:
                if '{' in line:
                    brace_count += line.count('{')
                    summary.append("{ /* ... */ }")
                if '}' in line:
                    brace_count -= line.count('}')
                    if brace_count == 0:
                        in_function = False
        
        return '\n'.join(summary)
    
    def _summarize_header(self, content: str) -> str:
        """Summarize C++ header file."""
        # Headers are usually declarations, include most of it
        lines = content.splitlines()
        summary = []
        
        in_function_body = False
        brace_count = 0
        
        for line in lines:
            stripped = line.strip()
            
            # Always include preprocessor directives
            if stripped.startswith('#'):
                summary.append(line)
                continue
            
            # Include class/struct declarations
            if any(keyword in stripped for keyword in ['class ', 'struct ', 'enum ', 'namespace ']):
                summary.append(line)
                continue
            
            # Skip function bodies in inline functions
            if '{' in line:
                brace_count += line.count('{')
                if brace_count > 0:
                    in_function_body = True
                    summary.append(line.split('{')[0] + '{ /* ... */ }')
                    continue
            
            if '}' in line:
                brace_count -= line.count('}')
                if brace_count == 0:
                    in_function_body = False
                continue
            
            if not in_function_body:
                summary.append(line)
        
        return '\n'.join(summary)
    
    def _summarize_python(self, content: str) -> str:
        """Summarize Python file."""
        lines = content.splitlines()
        summary = []
        
        # Include imports
        for line in lines:
            if line.strip().startswith(('import ', 'from ')):
                summary.append(line)
        
        if summary:
            summary.append("")
        
        # Extract class and function signatures
        in_function = False
        indent_level = 0
        
        for line in lines:
            stripped = line.strip()
            
            # Class definition
            if stripped.startswith('class '):
                summary.append(line)
                indent_level = len(line) - len(line.lstrip())
                continue
            
            # Function/method definition
            if stripped.startswith('def '):
                summary.append(line)
                # Add docstring if present
                in_function = True
                continue
            
            # Include docstrings
            if in_function and stripped.startswith(('"""', "'''")):
                summary.append(line)
                if stripped.count('"""') == 2 or stripped.count("'''") == 2:
                    in_function = False
                continue
            
            if in_function and stripped.endswith(('"""', "'''")):
                summary.append(line)
                in_function = False
                continue
        
        return '\n'.join(summary)
    
    def _summarize_javascript(self, content: str) -> str:
        """Summarize JavaScript/TypeScript file."""
        lines = content.splitlines()
        summary = []
        
        # Include imports/requires
        for line in lines:
            stripped = line.strip()
            if any(keyword in stripped for keyword in ['import ', 'require(', 'export ']):
                summary.append(line)
        
        if summary:
            summary.append("")
        
        # Extract function/class signatures
        for line in lines:
            stripped = line.strip()
            
            # Class definition
            if stripped.startswith('class '):
                summary.append(line)
                continue
            
            # Function definition
            if any(pattern in stripped for pattern in ['function ', 'const ', 'let ', 'var ']) and '=>' in stripped:
                summary.append(line.split('{')[0].strip() + ' { /* ... */ }')
                continue
            
            if stripped.startswith('function '):
                summary.append(line.split('{')[0].strip() + ' { /* ... */ }')
                continue
        
        return '\n'.join(summary)
    
    def _summarize_generic(self, content: str) -> str:
        """Generic summarization - first and last N lines."""
        lines = content.splitlines()
        
        if len(lines) <= 50:
            return content
        
        summary = []
        summary.extend(lines[:25])
        summary.append("")
        summary.append("// ... [middle section omitted] ...")
        summary.append("")
        summary.extend(lines[-25:])
        
        return '\n'.join(summary)
    
    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text."""
        return len(text) // self.CHARS_PER_TOKEN
    
    def truncate_to_limit(self, text: str, max_tokens: int) -> str:
        """Truncate text to token limit."""
        max_chars = max_tokens * self.CHARS_PER_TOKEN
        
        if len(text) <= max_chars:
            return text
        
        return text[:max_chars] + "\n\n[... truncated ...]"
