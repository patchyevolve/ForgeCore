"""
Language Detector - Identifies programming language and appropriate validation tools
"""

import os
from typing import Dict, List, Optional


class LanguageDetector:
    """
    Detects programming language and suggests validation tools.
    """
    
    LANGUAGE_PATTERNS = {
        'cpp': {
            'extensions': ['.cpp', '.cc', '.cxx', '.hpp', '.h', '.hxx'],
            'build_files': ['CMakeLists.txt', 'Makefile', '*.sln', '*.vcxproj'],
            'validators': ['compiler', 'clang-tidy', 'cppcheck'],
            'compilers': ['g++', 'clang++', 'cl', 'msvc']
        },
        'python': {
            'extensions': ['.py'],
            'build_files': ['setup.py', 'pyproject.toml', 'requirements.txt'],
            'validators': ['pylint', 'flake8', 'mypy', 'black'],
            'interpreters': ['python', 'python3']
        },
        'javascript': {
            'extensions': ['.js', '.jsx', '.mjs'],
            'build_files': ['package.json', 'webpack.config.js', 'tsconfig.json'],
            'validators': ['eslint', 'prettier', 'node'],
            'runtimes': ['node', 'deno', 'bun']
        },
        'typescript': {
            'extensions': ['.ts', '.tsx'],
            'build_files': ['tsconfig.json', 'package.json'],
            'validators': ['tsc', 'eslint', 'prettier'],
            'compilers': ['tsc']
        },
        'rust': {
            'extensions': ['.rs'],
            'build_files': ['Cargo.toml', 'Cargo.lock'],
            'validators': ['cargo check', 'cargo clippy', 'rustfmt'],
            'compilers': ['rustc', 'cargo']
        },
        'go': {
            'extensions': ['.go'],
            'build_files': ['go.mod', 'go.sum'],
            'validators': ['go build', 'go vet', 'golint', 'gofmt'],
            'compilers': ['go']
        },
        'java': {
            'extensions': ['.java'],
            'build_files': ['pom.xml', 'build.gradle', 'build.xml'],
            'validators': ['javac', 'maven', 'gradle'],
            'compilers': ['javac']
        },
        'csharp': {
            'extensions': ['.cs'],
            'build_files': ['*.csproj', '*.sln'],
            'validators': ['dotnet build', 'msbuild'],
            'compilers': ['csc', 'dotnet']
        }
    }
    
    def __init__(self, project_path: str):
        self.project_path = project_path
        self.detected_languages = []
        self.primary_language = None
    
    def detect(self) -> Dict[str, any]:
        """
        Detect languages in project.
        
        Returns:
            Dict with detected languages and validation tools
        """
        language_counts = {}
        
        # Scan files
        for root, dirs, files in os.walk(self.project_path):
            # Skip common ignore directories
            dirs[:] = [d for d in dirs if d not in {
                '.git', '.vs', 'node_modules', '__pycache__', 
                'build', 'dist', 'target', 'bin', 'obj'
            }]
            
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                
                for lang, config in self.LANGUAGE_PATTERNS.items():
                    if ext in config['extensions']:
                        language_counts[lang] = language_counts.get(lang, 0) + 1
        
        # Determine primary language
        if language_counts:
            self.primary_language = max(language_counts, key=language_counts.get)
            self.detected_languages = list(language_counts.keys())
        
        # Check for build files
        build_system = self._detect_build_system()
        
        return {
            'primary_language': self.primary_language,
            'all_languages': self.detected_languages,
            'file_counts': language_counts,
            'build_system': build_system,
            'validators': self._get_validators(),
            'is_multi_language': len(self.detected_languages) > 1
        }
    
    def _detect_build_system(self) -> Optional[str]:
        """Detect build system from build files."""
        for root, dirs, files in os.walk(self.project_path):
            for file in files:
                file_lower = file.lower()
                
                # C++ build systems
                if file_lower.endswith('.sln'):
                    return 'msbuild'
                if file_lower == 'cmakelists.txt':
                    return 'cmake'
                if file_lower == 'makefile':
                    return 'make'
                
                # Python
                if file_lower == 'setup.py':
                    return 'setuptools'
                if file_lower == 'pyproject.toml':
                    return 'poetry'
                
                # JavaScript/TypeScript
                if file_lower == 'package.json':
                    return 'npm'
                
                # Rust
                if file_lower == 'cargo.toml':
                    return 'cargo'
                
                # Go
                if file_lower == 'go.mod':
                    return 'go'
                
                # Java
                if file_lower == 'pom.xml':
                    return 'maven'
                if file_lower == 'build.gradle':
                    return 'gradle'
        
        return None
    
    def _get_validators(self) -> List[str]:
        """Get available validators for detected languages."""
        if not self.primary_language:
            return []
        
        config = self.LANGUAGE_PATTERNS.get(self.primary_language, {})
        return config.get('validators', [])
    
    def get_validation_command(self) -> Optional[str]:
        """
        Get appropriate validation command for the project.
        
        Returns:
            Command string or None
        """
        if not self.primary_language:
            return None
        
        build_system = self._detect_build_system()
        
        # Language-specific validation
        if self.primary_language == 'cpp':
            if build_system == 'msbuild':
                return 'msbuild /t:Build /v:minimal'
            elif build_system == 'cmake':
                return 'cmake --build .'
            elif build_system == 'make':
                return 'make'
            else:
                return 'g++ -fsyntax-only *.cpp'
        
        elif self.primary_language == 'python':
            return 'python -m py_compile *.py'
        
        elif self.primary_language == 'javascript':
            if build_system == 'npm':
                return 'npm run build'
            else:
                return 'node --check *.js'
        
        elif self.primary_language == 'typescript':
            return 'tsc --noEmit'
        
        elif self.primary_language == 'rust':
            return 'cargo check'
        
        elif self.primary_language == 'go':
            return 'go build'
        
        elif self.primary_language == 'java':
            if build_system == 'maven':
                return 'mvn compile'
            elif build_system == 'gradle':
                return 'gradle build'
            else:
                return 'javac *.java'
        
        elif self.primary_language == 'csharp':
            if build_system == 'msbuild':
                return 'msbuild /t:Build'
            else:
                return 'dotnet build'
        
        return None
