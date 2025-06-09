import ast
import json
import re
import os
from pathlib import Path
from collections import defaultdict, Counter
from typing import Dict, List, Set, Tuple, Optional, Any, Generator
from dataclasses import dataclass, asdict
from datetime import datetime
import hashlib

@dataclass
class CodeRecommendation:
    """Represents a specific code recommendation for AI assistants"""
    id: str
    type: str  # "refactor", "optimize", "fix", "enhance", "test", "document"
    priority: str  # "high", "medium", "low"
    file_path: str
    function_name: Optional[str]
    line_range: Tuple[int, int]
    title: str
    description: str
    current_code: str
    suggested_approach: str
    cursor_prompt: str
    copilot_comment: str
    tags: List[str]
    estimated_effort: str  # "5min", "30min", "2hrs", etc.
    dependencies: List[str]  # Other functions/files that might be affected
    test_files: List[str]   # Related test files
    
@dataclass
class AIAssistantConfig:
    """Configuration for AI assistant integration"""
    cursor_enabled: bool = True
    copilot_enabled: bool = True
    include_context: bool = True
    max_context_lines: int = 50
    generate_tests: bool = True
    include_type_hints: bool = True
    follow_pep8: bool = True
    complexity_threshold: int = 8
    line_length_limit: int = 88

class CursorCopilotIntegrator:
    """Main class for generating AI assistant recommendations"""
    
    def __init__(self, config: AIAssistantConfig = None):
        self.config = config or AIAssistantConfig()
        self.recommendations = []
        self.code_analysis = {}
        
    def analyze_codebase(self, repo_path: str) -> Dict[str, Any]:
        """Comprehensive codebase analysis for AI recommendations"""
        repo_path = Path(repo_path)
        analysis = {
            "files": [],
            "functions": [],
            "classes": [],
            "issues": [],
            "opportunities": [],
            "metrics": {}
        }
        
        exclude_dirs = {"venv", ".venv", "__pycache__", "node_modules", "site-packages", ".git", ".local"}
        python_files = [f for f in repo_path.rglob("*.py") if not any(p in exclude_dirs for p in f.parts)]

        print(f"🔍 Analyzing {len(python_files)} Python files...")
        
        for file_path in python_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                file_analysis = self._analyze_file(str(file_path), content)
                analysis["files"].append(file_analysis)
                analysis["functions"].extend(file_analysis["functions"])
                analysis["classes"].extend(file_analysis["classes"])
                analysis["issues"].extend(file_analysis["issues"])
                analysis["opportunities"].extend(file_analysis["opportunities"])
                
            except Exception as e:
                print(f"⚠️  Error analyzing {file_path}: {e}")
                continue
        
        analysis["metrics"] = self._calculate_metrics(analysis)
        self.code_analysis = analysis
        return analysis
    
    def _analyze_file(self, file_path: str, content: str) -> Dict[str, Any]:
        """Analyze a single Python file"""
        try:
            tree = ast.parse(content)
        except SyntaxError as e:
            return {
                "file_path": file_path,
                "functions": [],
                "classes": [],
                "issues": [{"type": "syntax_error", "message": str(e)}],
                "opportunities": []
            }
        
        analysis = {
            "file_path": file_path,
            "functions": [],
            "classes": [],
            "issues": [],
            "opportunities": [],
            "imports": [],
            "lines_of_code": len(content.splitlines()),
            "complexity_score": 0
        }
        
        # Extract imports
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    analysis["imports"].append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    analysis["imports"].append(f"{module}.{alias.name}")
        
        # Analyze functions and classes
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                func_analysis = self._analyze_function(node, content, file_path)
                analysis["functions"].append(func_analysis)
                analysis["complexity_score"] += func_analysis["complexity"]
                
            elif isinstance(node, ast.ClassDef):
                class_analysis = self._analyze_class(node, content, file_path)
                analysis["classes"].append(class_analysis)
        
        # Detect file-level issues and opportunities
        analysis["issues"].extend(self._detect_file_issues(content, file_path))
        analysis["opportunities"].extend(self._detect_file_opportunities(content, file_path, analysis))
        
        return analysis
    
    def _analyze_function(self, node: ast.FunctionDef, content: str, file_path: str) -> Dict[str, Any]:
        """Detailed function analysis"""
        lines = content.splitlines()
        start_line = node.lineno
        end_line = getattr(node, 'end_lineno', start_line + 10)
        
        func_content = '\n'.join(lines[start_line-1:end_line])
        
        analysis = {
            "name": node.name,
            "file_path": file_path,
            "start_line": start_line,
            "end_line": end_line,
            "args": [arg.arg for arg in node.args.args],
            "decorators": [ast.unparse(dec) if hasattr(ast, 'unparse') else str(dec) for dec in node.decorator_list],
            "docstring": ast.get_docstring(node),
            "complexity": self._calculate_complexity(node),
            "lines_of_code": end_line - start_line + 1,
            "has_type_hints": self._has_type_hints(node),
            "returns_value": self._has_return_statement(node),
            "content": func_content,
            "issues": [],
            "opportunities": []
        }
        
        # Detect function-specific issues
        analysis["issues"] = self._detect_function_issues(node, analysis)
        analysis["opportunities"] = self._detect_function_opportunities(node, analysis)
        
        return analysis
    
    def _analyze_class(self, node: ast.ClassDef, content: str, file_path: str) -> Dict[str, Any]:
        """Detailed class analysis"""
        lines = content.splitlines()
        start_line = node.lineno
        end_line = getattr(node, 'end_lineno', start_line + 20)
        
        methods = [n for n in node.body if isinstance(n, ast.FunctionDef)]
        
        return {
            "name": node.name,
            "file_path": file_path,
            "start_line": start_line,
            "end_line": end_line,
            "methods": [m.name for m in methods],
            "base_classes": [base.id if isinstance(base, ast.Name) else str(base) for base in node.bases],
            "docstring": ast.get_docstring(node),
            "has_init": any(m.name == "__init__" for m in methods),
            "method_count": len(methods)
        }
    
    def _calculate_complexity(self, node: ast.FunctionDef) -> int:
        """Calculate cyclomatic complexity"""
        complexity = 1
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor, ast.With, ast.Try)):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1
        return complexity
    
    def _has_type_hints(self, node: ast.FunctionDef) -> bool:
        """Check if function has type hints"""
        has_return_hint = node.returns is not None
        has_arg_hints = any(arg.annotation is not None for arg in node.args.args)
        return has_return_hint or has_arg_hints
    
    def _has_return_statement(self, node: ast.FunctionDef) -> bool:
        """Check if function has return statements"""
        for child in ast.walk(node):
            if isinstance(child, ast.Return):
                return True
        return False
    
    def _detect_function_issues(self, node: ast.FunctionDef, analysis: Dict) -> List[Dict]:
        """Detect issues in functions"""
        issues = []
        
        if analysis["complexity"] > self.config.complexity_threshold:
            issues.append({
                "type": "high_complexity",
                "severity": "medium",
                "message": f"Function has high complexity ({analysis['complexity']})"
            })
        
        if len(analysis["args"]) > 5:
            issues.append({
                "type": "too_many_parameters",
                "severity": "low",
                "message": f"Function has {len(analysis['args'])} parameters (consider refactoring)"
            })
        
        if not analysis["docstring"] and not node.name.startswith("_"):
            issues.append({
                "type": "missing_docstring",
                "severity": "low",
                "message": "Public function missing docstring"
            })
        
        if not analysis["has_type_hints"] and self.config.include_type_hints:
            issues.append({
                "type": "missing_type_hints",
                "severity": "low",
                "message": "Function missing type hints"
            })
        
        return issues
    
    def _detect_function_opportunities(self, node: ast.FunctionDef, analysis: Dict) -> List[Dict]:
        """Detect improvement opportunities in functions"""
        opportunities = []
        
        if analysis["complexity"] > 5:
            opportunities.append({
                "type": "refactor_complexity",
                "potential": "medium",
                "description": "Function could be broken down into smaller functions"
            })
        
        if analysis["lines_of_code"] > 30:
            opportunities.append({
                "type": "split_function",
                "potential": "medium", 
                "description": "Long function could be split for better readability"
            })
        
        # Check for potential async opportunities
        func_content = analysis["content"].lower()
        if any(keyword in func_content for keyword in ["requests.", "urllib", "http", "api"]):
            opportunities.append({
                "type": "async_potential",
                "potential": "high",
                "description": "Function might benefit from async/await pattern"
            })
        
        # Check for caching opportunities
        if not any("cache" in dec for dec in analysis["decorators"]):
            if analysis["returns_value"] and not any("random" in analysis["content"].lower() for _ in [1]):
                opportunities.append({
                    "type": "caching_potential",
                    "potential": "medium",
                    "description": "Function might benefit from caching"
                })
        
        return opportunities
    
    def _detect_file_issues(self, content: str, file_path: str) -> List[Dict]:
        """Detect file-level issues"""
        issues = []
        lines = content.splitlines()
        
        # Check line length
        for i, line in enumerate(lines, 1):
            if len(line) > self.config.line_length_limit:
                issues.append({
                    "type": "line_too_long",
                    "severity": "low",
                    "line": i,
                    "message": f"Line {i} exceeds {self.config.line_length_limit} characters"
                })
        
        # Check for TODO/FIXME comments
        for i, line in enumerate(lines, 1):
            if re.search(r'#.*\b(TODO|FIXME|HACK|XXX)\b', line, re.IGNORECASE):
                issues.append({
                    "type": "todo_comment",
                    "severity": "low",
                    "line": i,
                    "message": f"TODO/FIXME comment at line {i}"
                })
        
        return issues
    
    def _detect_file_opportunities(self, content: str, file_path: str, analysis: Dict) -> List[Dict]:
        """Detect file-level opportunities"""
        opportunities = []
        
        # Check for missing __init__.py
        if file_path.endswith("__init__.py") and not content.strip():
            opportunities.append({
                "type": "empty_init",
                "potential": "low",
                "description": "Empty __init__.py could include package documentation or imports"
            })
        
        # Check for test file opportunities
        if not file_path.endswith("test_") and "test" not in file_path.lower():
            test_file = file_path.replace(".py", "_test.py")
            if not os.path.exists(test_file):
                opportunities.append({
                    "type": "missing_tests",
                    "potential": "high",
                    "description": f"No test file found for {file_path}"
                })
        
        return opportunities
    
    def _calculate_metrics(self, analysis: Dict) -> Dict[str, Any]:
        """Calculate overall codebase metrics"""
        total_functions = len(analysis["functions"])
        total_classes = len(analysis["classes"])
        total_lines = sum(f["lines_of_code"] for f in analysis["files"])
        
        avg_complexity = sum(f["complexity"] for f in analysis["functions"]) / max(total_functions, 1)
        
        functions_with_docstrings = sum(1 for f in analysis["functions"] if f["docstring"])
        functions_with_type_hints = sum(1 for f in analysis["functions"] if f["has_type_hints"])
        
        return {
            "total_files": len(analysis["files"]),
            "total_functions": total_functions,
            "total_classes": total_classes,
            "total_lines_of_code": total_lines,
            "average_complexity": round(avg_complexity, 2),
            "docstring_coverage": round(functions_with_docstrings / max(total_functions, 1) * 100, 1),
            "type_hint_coverage": round(functions_with_type_hints / max(total_functions, 1) * 100, 1),
            "total_issues": len(analysis["issues"]),
            "total_opportunities": len(analysis["opportunities"])
        }
    
    def generate_recommendations(self) -> List[CodeRecommendation]:
        """Generate specific recommendations for Cursor/Copilot"""
        self.recommendations = []
        
        # Process functions
        for func in self.code_analysis["functions"]:
            self.recommendations.extend(self._generate_function_recommendations(func))
        
        # Process classes
        for cls in self.code_analysis["classes"]:
            self.recommendations.extend(self._generate_class_recommendations(cls))
        
        # Process file-level recommendations
        for file_analysis in self.code_analysis["files"]:
            self.recommendations.extend(self._generate_file_recommendations(file_analysis))
        
        # Sort by priority
        priority_order = {"high": 3, "medium": 2, "low": 1}
        self.recommendations.sort(key=lambda r: priority_order[r.priority], reverse=True)
        
        return self.recommendations
    
    def _generate_function_recommendations(self, func: Dict) -> List[CodeRecommendation]:
        """Generate recommendations for a specific function"""
        recommendations = []
        rec_id_base = f"{func['file_path']}:{func['name']}"
        
        # High complexity refactoring
        if func["complexity"] > self.config.complexity_threshold:
            recommendations.append(CodeRecommendation(
                id=hashlib.md5(f"{rec_id_base}:complexity".encode()).hexdigest()[:8],
                type="refactor",
                priority="high",
                file_path=func["file_path"],
                function_name=func["name"],
                line_range=(func["start_line"], func["end_line"]),
                title=f"Refactor high complexity function: {func['name']}",
                description=f"Function has complexity of {func['complexity']}, consider breaking it down",
                current_code=func["content"],
                suggested_approach="Break function into smaller, single-purpose functions",
                cursor_prompt=f"Refactor this function to reduce complexity from {func['complexity']} to under {self.config.complexity_threshold}. Break it into smaller functions with clear responsibilities.",
                copilot_comment=f"# TODO: Refactor {func['name']} - complexity {func['complexity']} is too high",
                tags=["refactor", "complexity", "maintainability"],
                estimated_effort="30min-1hr",
                dependencies=self._find_function_dependencies(func),
                test_files=self._find_related_test_files(func["file_path"])
            ))
        
        # Missing type hints
        if not func["has_type_hints"] and self.config.include_type_hints:
            recommendations.append(CodeRecommendation(
                id=hashlib.md5(f"{rec_id_base}:type_hints".encode()).hexdigest()[:8],
                type="enhance",
                priority="medium",
                file_path=func["file_path"],
                function_name=func["name"],
                line_range=(func["start_line"], func["start_line"]),
                title=f"Add type hints to {func['name']}",
                description="Function lacks type annotations for better code clarity",
                current_code=func["content"],
                suggested_approach="Add parameter and return type annotations",
                cursor_prompt=f"Add comprehensive type hints to this function. Include types for all parameters and return value.",
                copilot_comment=f"# Add type hints to {func['name']} for better IDE support",
                tags=["type-hints", "documentation", "maintainability"],
                estimated_effort="5-10min",
                dependencies=[],
                test_files=self._find_related_test_files(func["file_path"])
            ))
        
        # Missing docstring
        if not func["docstring"] and not func["name"].startswith("_"):
            recommendations.append(CodeRecommendation(
                id=hashlib.md5(f"{rec_id_base}:docstring".encode()).hexdigest()[:8],
                type="document",
                priority="medium",
                file_path=func["file_path"],
                function_name=func["name"],
                line_range=(func["start_line"], func["start_line"]),
                title=f"Add docstring to {func['name']}",
                description="Public function missing documentation",
                current_code=func["content"],
                suggested_approach="Add comprehensive docstring with parameters, returns, and examples",
                cursor_prompt=f"Write a comprehensive docstring for this function following Google/NumPy style. Include parameters, return value, and usage example.",
                copilot_comment=f'"""\nAdd docstring for {func["name"]}\n\nArgs:\n    # Add parameter descriptions\n\nReturns:\n    # Add return description\n"""',
                tags=["documentation", "docstring"],
                estimated_effort="10-15min",
                dependencies=[],
                test_files=self._find_related_test_files(func["file_path"])
            ))
        
        # Async opportunities
        for opp in func["opportunities"]:
            if opp["type"] == "async_potential":
                recommendations.append(CodeRecommendation(
                    id=hashlib.md5(f"{rec_id_base}:async".encode()).hexdigest()[:8],
                    type="optimize",
                    priority="high",
                    file_path=func["file_path"],
                    function_name=func["name"],
                    line_range=(func["start_line"], func["end_line"]),
                    title=f"Convert {func['name']} to async",
                    description="Function performs I/O operations and could benefit from async/await",
                    current_code=func["content"],
                    suggested_approach="Convert to async function and use aiohttp/asyncio",
                    cursor_prompt="Convert this function to use async/await pattern. Replace requests with aiohttp and add proper error handling.",
                    copilot_comment=f"# TODO: Convert {func['name']} to async for better performance",
                    tags=["async", "performance", "optimization"],
                    estimated_effort="45min-1hr",
                    dependencies=self._find_function_dependencies(func),
                    test_files=self._find_related_test_files(func["file_path"])
                ))
        
        return recommendations
    
    def _generate_class_recommendations(self, cls: Dict) -> List[CodeRecommendation]:
        """Generate recommendations for classes"""
        recommendations = []
        rec_id_base = f"{cls['file_path']}:{cls['name']}"
        
        # Missing __init__ method
        if not cls["has_init"] and cls["method_count"] > 0:
            recommendations.append(CodeRecommendation(
                id=hashlib.md5(f"{rec_id_base}:init".encode()).hexdigest()[:8],
                type="enhance",
                priority="medium",
                file_path=cls["file_path"],
                function_name=None,
                line_range=(cls["start_line"], cls["end_line"]),
                title=f"Add __init__ method to {cls['name']}",
                description="Class has methods but no constructor",
                current_code="",
                suggested_approach="Add __init__ method to properly initialize class instances",
                cursor_prompt=f"Add an __init__ method to the {cls['name']} class. Consider what attributes need to be initialized.",
                copilot_comment=f"# Add __init__ method to {cls['name']} class",
                tags=["class-design", "constructor"],
                estimated_effort="15-30min",
                dependencies=[],
                test_files=self._find_related_test_files(cls["file_path"])
            ))
        
        return recommendations
    
    def _generate_file_recommendations(self, file_analysis: Dict) -> List[CodeRecommendation]:
        """Generate file-level recommendations"""
        recommendations = []
        
        # Missing test files
        for opp in file_analysis["opportunities"]:
            if opp["type"] == "missing_tests":
                recommendations.append(CodeRecommendation(
                    id=hashlib.md5(f"{file_analysis['file_path']}:tests".encode()).hexdigest()[:8],
                    type="test",
                    priority="high",
                    file_path=file_analysis["file_path"],
                    function_name=None,
                    line_range=(1, file_analysis["lines_of_code"]),
                    title=f"Create test file for {Path(file_analysis['file_path']).name}",
                    description="File has no corresponding test file",
                    current_code="",
                    suggested_approach="Create comprehensive test suite covering all functions",
                    cursor_prompt=f"Create a comprehensive test file for {file_analysis['file_path']}. Include tests for all public functions with edge cases and error conditions.",
                    copilot_comment="# Create test file with pytest fixtures and comprehensive test cases",
                    tags=["testing", "pytest", "coverage"],
                    estimated_effort="1-2hrs",
                    dependencies=[],
                    test_files=[]
                ))
        
        return recommendations
    
    def _find_function_dependencies(self, func: Dict) -> List[str]:
        """Find dependencies for a function"""
        # This is a simplified version - in practice, you'd do AST analysis
        dependencies = []
        content = func["content"].lower()
        
        # Look for function calls in the same file
        for other_func in self.code_analysis["functions"]:
            if other_func["file_path"] == func["file_path"] and other_func["name"] != func["name"]:
                if other_func["name"].lower() in content:
                    dependencies.append(other_func["name"])
        
        return dependencies
    
    def _find_related_test_files(self, file_path: str) -> List[str]:
        """Find related test files"""
        test_files = []
        base_name = Path(file_path).stem
        
        possible_test_names = [
            f"test_{base_name}.py",
            f"{base_name}_test.py",
            f"tests/test_{base_name}.py",
            f"test/test_{base_name}.py"
        ]
        
        for test_name in possible_test_names:
            if os.path.exists(test_name):
                test_files.append(test_name)
        
        return test_files
    
    def export_cursor_config(self, output_path: str = ".cursor/rules"):
        """Export Cursor-specific configuration and rules"""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        cursor_rules = []
        
        # Add rules based on recommendations
        for rec in self.recommendations:
            if rec.priority == "high":
                cursor_rules.append(f"# {rec.title}")
                cursor_rules.append(f"# {rec.description}")
                cursor_rules.append(rec.cursor_prompt)
                cursor_rules.append("")
        
        # Add general coding standards
        cursor_rules.extend([
            "# General Coding Standards",
            "- Follow PEP 8 style guidelines",
            "- Add type hints to all functions",
            "- Include comprehensive docstrings",
            f"- Keep function complexity under {self.config.complexity_threshold}",
            f"- Limit line length to {self.config.line_length_limit} characters",
            "- Write unit tests for all new functions",
            "- Use async/await for I/O operations",
            "- Add error handling and logging",
            ""
        ])
        
        with open(output_path, 'w') as f:
            f.write('\n'.join(cursor_rules))
        
        print(f"📝 Cursor rules exported to {output_path}")
    
    def export_copilot_prompts(self, output_path: str = ".github/copilot-prompts.md"):
        """Export GitHub Copilot prompts and comments"""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        prompts = [
            "# GitHub Copilot Prompts and Comments",
            "",
            "Use these prompts and comments to guide Copilot suggestions:",
            ""
        ]
        
        # Group by type
        by_type = defaultdict(list)
        for rec in self.recommendations:
            by_type[rec.type].append(rec)
        
        for rec_type, recs in by_type.items():
            prompts.append(f"## {rec_type.title()} Recommendations")
            prompts.append("")
            
            for rec in recs[:5]:  # Top 5 per type
                prompts.append(f"### {rec.title}")
                prompts.append(f"**File:** `{rec.file_path}`")
                if rec.function_name:
                    prompts.append(f"**Function:** `{rec.function_name}`")
                prompts.append(f"**Priority:** {rec.priority}")
                prompts.append("")
                prompts.append("**Copilot Comment:**")
                prompts.append(f"```python")
                prompts.append(rec.copilot_comment)
                prompts.append("```")
                prompts.append("")
                prompts.append("**Cursor Prompt:**")
                prompts.append(f"> {rec.cursor_prompt}")
                prompts.append("")
                prompts.append("---")
                prompts.append("")
        
        with open(output_path, 'w') as f:
            f.write('\n'.join(prompts))
        
        print(f"🤖 Copilot prompts exported to {output_path}")
    
    def generate_vscode_tasks(self, output_path: str = ".vscode/tasks.json"):
        """Generate VS Code tasks for common improvements"""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        tasks = {
            "version": "2.0.0",
            "tasks": []
        }
        
        # Add linting task
        tasks["tasks"].append({
            "label": "Run Code Analysis",
            "type": "shell",
            "command": "python",
            "args": ["-m", "flake8", ".", "--max-line-length", str(self.config.line_length_limit)],
            "group": "test",
            "presentation": {
                "echo": True,
                "reveal": "always",
                "panel": "new"
            }
        })
        
        # Add type checking task
        tasks["tasks"].append({
            "label": "Type Check",
            "type": "shell", 
            "command": "mypy",
            "args": [".", "--ignore-missing-imports"],
            "group": "test"
        })
        
        # Add test task
        tasks["tasks"].append({
            "label": "Run Tests",
            "type": "shell",
            "command": "pytest",
            "args": ["-v", "--cov=.", "--cov-report=html"],
            "group": "test"
        })
        
        with open(output_path, 'w') as f:
            json.dump(tasks, f, indent=2)
        
        print(f"⚙️  VS Code tasks exported to {output_path}")


if __name__ == "__main__":
    import sys
    repo_path = sys.argv[1] if len(sys.argv) > 1 else "."
    integrator = CursorCopilotIntegrator()
    print(f"🔍 Analyzing codebase in: {repo_path}")
    integrator.analyze_codebase(repo_path)
    print("🧠 Generating AI Recommendations...")
    recommendations = integrator.generate_recommendations()
    print(f"📦 {len(recommendations)} recommendations generated.\n")
    for rec in recommendations[:10]:  # Print top 10
        print(f"🔧 {rec.title}")
        print(f"   ➤ File: {rec.file_path} | Function: {rec.function_name}")
        print(f"   ➤ Type: {rec.type} | Priority: {rec.priority}")
        print(f"   ➤ Desc: {rec.description}")
        print(f"   ➤ Tags: {', '.join(rec.tags)}")
        print(f"   ➤ Copilot: {rec.copilot_comment}")
        print(f"   ➤ Cursor Prompt: {rec.cursor_prompt}")
        print("---\n")