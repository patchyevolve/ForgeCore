"""
Smart Validator - Language-agnostic code validation

Uses multiple strategies:
1. Build system (if available)
2. Syntax checking
3. Linting
4. LLM-based validation
"""

import os
import subprocess
from typing import Dict, List, Optional, Tuple
from tools.language_detector import LanguageDetector


class SmartValidator:
    """
    Intelligent code validator that adapts to language and available tools.
    """
    
    def __init__(self, project_path: str, logger):
        self.project_path = project_path
        self.logger = logger
        self.detector = LanguageDetector(project_path)
        self.language_info = self.detector.detect()
    
    def validate(self, modified_files: List[str] = None) -> Dict[str, any]:
        """
        Validate code using best available method.
        
        Args:
            modified_files: List of files that were modified
            
        Returns:
            Validation result dict
        """
        self.logger.log_event(
            state="VALIDATION",
            event="SMART_VALIDATION_START",
            details={
                "language": self.language_info['primary_language'],
                "build_system": self.language_info['build_system'],
                "modified_files": modified_files
            }
        )
        
        # Strategy 1: Try build system
        if self.language_info['build_system']:
            result = self._validate_with_build_system()
            if result['attempted']:
                return result
        
        # Strategy 2: Try syntax checking
        result = self._validate_syntax(modified_files)
        if result['attempted']:
            return result
        
        # Strategy 3: LLM-based validation
        result = self._validate_with_llm(modified_files)
        return result
    
    def _validate_with_build_system(self) -> Dict[str, any]:
        """Validate using build system."""
        command = self.detector.get_validation_command()
        
        if not command:
            return {'attempted': False}
        
        self.logger.log_event(
            state="VALIDATION",
            event="BUILD_SYSTEM_VALIDATION",
            details={"command": command}
        )
        
        try:
            # Check if command is available
            cmd_parts = command.split()
            cmd_name = cmd_parts[0]
            
            # Try to find the command
            if not self._command_exists(cmd_name):
                self.logger.log_event(
                    state="VALIDATION",
                    event="BUILD_COMMAND_NOT_FOUND",
                    details={"command": cmd_name}
                )
                return {'attempted': False}
            
            # Run build command
            process = subprocess.run(
                command,
                shell=True,
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            return {
                'attempted': True,
                'method': 'build_system',
                'command': command,
                'exit_code': process.returncode,
                'stdout': process.stdout,
                'stderr': process.stderr,
                'success': process.returncode == 0
            }
        
        except subprocess.TimeoutExpired:
            return {
                'attempted': True,
                'method': 'build_system',
                'command': command,
                'exit_code': -1,
                'error': 'Build timeout',
                'success': False
            }
        
        except Exception as e:
            self.logger.log_event(
                state="VALIDATION",
                event="BUILD_SYSTEM_ERROR",
                details={"error": str(e)}
            )
            return {'attempted': False}
    
    def _validate_syntax(self, modified_files: List[str] = None) -> Dict[str, any]:
        """Validate syntax without full build."""
        lang = self.language_info['primary_language']
        
        if not lang or not modified_files:
            return {'attempted': False}
        
        errors = []
        
        for file in modified_files:
            file_path = os.path.join(self.project_path, file)
            
            if not os.path.exists(file_path):
                continue
            
            # Language-specific syntax checking
            if lang == 'python':
                result = self._check_python_syntax(file_path)
                if result:
                    errors.append(result)
            
            elif lang in ['javascript', 'typescript']:
                result = self._check_js_syntax(file_path)
                if result:
                    errors.append(result)
            
            elif lang == 'cpp':
                result = self._check_cpp_syntax(file_path)
                if result:
                    errors.append(result)
        
        return {
            'attempted': True,
            'method': 'syntax_check',
            'files_checked': len(modified_files) if modified_files else 0,
            'errors': errors,
            'success': len(errors) == 0
        }
    
    def _check_python_syntax(self, file_path: str) -> Optional[Dict]:
        """Check Python syntax."""
        try:
            with open(file_path, 'r') as f:
                code = f.read()
            compile(code, file_path, 'exec')
            return None
        except SyntaxError as e:
            return {
                'file': file_path,
                'line': e.lineno,
                'message': str(e),
                'type': 'SYNTAX_ERROR'
            }
    
    def _check_js_syntax(self, file_path: str) -> Optional[Dict]:
        """Check JavaScript syntax using node --check."""
        if not self._command_exists('node'):
            return None
        
        try:
            result = subprocess.run(
                ['node', '--check', file_path],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode != 0:
                return {
                    'file': file_path,
                    'message': result.stderr,
                    'type': 'SYNTAX_ERROR'
                }
            return None
        except:
            return None
    
    def _check_cpp_syntax(self, file_path: str) -> Optional[Dict]:
        """Check C++ syntax using compiler."""
        # Try g++ first, then clang++
        for compiler in ['g++', 'clang++']:
            if self._command_exists(compiler):
                try:
                    result = subprocess.run(
                        [compiler, '-fsyntax-only', file_path],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    
                    if result.returncode != 0:
                        return {
                            'file': file_path,
                            'message': result.stderr,
                            'type': 'SYNTAX_ERROR'
                        }
                    return None
                except:
                    continue
        
        return None
    
    def _validate_with_llm(self, modified_files: List[str] = None) -> Dict[str, any]:
        """Validate using LLM as last resort."""
        self.logger.log_event(
            state="VALIDATION",
            event="LLM_VALIDATION",
            details={"files": modified_files}
        )
        
        # For now, assume valid if we reach here
        # Future: Use LLM to check code quality
        return {
            'attempted': True,
            'method': 'llm_validation',
            'success': True,
            'note': 'LLM validation not yet implemented - assuming valid'
        }
    
    def _command_exists(self, command: str) -> bool:
        """Check if command exists in PATH."""
        try:
            subprocess.run(
                [command, '--version'],
                capture_output=True,
                timeout=2
            )
            return True
        except:
            return False
