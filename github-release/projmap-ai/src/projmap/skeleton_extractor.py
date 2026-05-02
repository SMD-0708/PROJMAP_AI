"""骨架提取器模块

核心功能：用Python程序100%扫描所有文件，提取足够线索供AI理解。
设计原则：避免AI选择性阅读导致的遗漏，程序保证完整性。

支持的文件类型：
- .py: Python源码
- .ipynb: Jupyter Notebook
- .csv: 数据文件
- .md: Markdown文档
- .json: JSON配置
- .yaml/.yml: YAML配置
"""

import ast
import json
import os
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, Any
from pathlib import Path
from enum import Enum


class FileType(Enum):
    PYTHON = "python"
    JUPYTER = "jupyter"
    CSV = "csv"
    MARKDOWN = "markdown"
    JSON = "json"
    YAML = "yaml"
    UNKNOWN = "unknown"


@dataclass
class FunctionSignature:
    name: str
    parameters: list[dict]
    return_type: Optional[str] = None
    docstring: Optional[str] = None
    line_start: int = 0
    line_end: int = 0
    decorators: list[str] = field(default_factory=list)


@dataclass
class ClassDefinition:
    name: str
    bases: list[str]
    methods: list[FunctionSignature]
    docstring: Optional[str] = None
    line_start: int = 0
    line_end: int = 0
    decorators: list[str] = field(default_factory=list)


@dataclass
class ImportInfo:
    module: str
    names: list[str]
    alias: Optional[str] = None
    is_from_import: bool = False
    line_number: int = 0


@dataclass
class FileReadOperation:
    target: str
    method: str
    line_number: int


@dataclass
class FileWriteOperation:
    target: str
    method: str
    line_number: int


@dataclass
class PythonSkeleton:
    file_path: str
    file_name: str
    file_size: int
    line_count: int
    language: str = "python"
    
    imports: list[dict] = field(default_factory=list)
    exports: list[str] = field(default_factory=list)
    
    functions: list[dict] = field(default_factory=list)
    classes: list[dict] = field(default_factory=list)
    module_variables: list[str] = field(default_factory=list)
    
    file_reads: list[dict] = field(default_factory=list)
    file_writes: list[dict] = field(default_factory=list)
    
    top_level_docstring: Optional[str] = None
    todos: list[dict] = field(default_factory=list)
    
    call_graph: dict = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)


@dataclass
class JupyterSkeleton:
    file_path: str
    file_name: str
    file_size: int
    
    cell_count: int = 0
    code_cells: list[dict] = field(default_factory=list)
    markdown_cells: list[dict] = field(default_factory=list)
    
    imports: list[dict] = field(default_factory=list)
    functions: list[dict] = field(default_factory=list)
    classes: list[dict] = field(default_factory=list)
    
    outputs: list[dict] = field(default_factory=list)


@dataclass
class CSVSkeleton:
    file_path: str
    file_name: str
    file_size: int
    
    column_names: list[str] = field(default_factory=list)
    row_count: int = 0
    column_count: int = 0
    sample_rows: list[dict] = field(default_factory=list)
    dtypes_guess: dict = field(default_factory=dict)
    has_header: bool = True
    delimiter: str = ","


@dataclass
class MarkdownSkeleton:
    file_path: str
    file_name: str
    file_size: int
    
    headings: list[dict] = field(default_factory=list)
    code_blocks: list[dict] = field(default_factory=list)
    links: list[dict] = field(default_factory=list)
    images: list[dict] = field(default_factory=list)
    todos: list[dict] = field(default_factory=list)
    
    word_count: int = 0
    reading_time_minutes: int = 0


@dataclass
class JSONSkeleton:
    file_path: str
    file_name: str
    file_size: int
    
    top_level_keys: list[str] = field(default_factory=list)
    structure_depth: int = 0
    array_lengths: dict = field(default_factory=dict)
    value_types: dict = field(default_factory=dict)
    sample_values: dict = field(default_factory=dict)


@dataclass
class ProjectSkeleton:
    project_root: str
    scan_time: str
    total_files: int = 0
    total_directories: int = 0
    
    python_files: list[dict] = field(default_factory=list)
    jupyter_files: list[dict] = field(default_factory=list)
    csv_files: list[dict] = field(default_factory=list)
    markdown_files: list[dict] = field(default_factory=list)
    json_files: list[dict] = field(default_factory=list)
    other_files: list[dict] = field(default_factory=list)
    
    summary: dict = field(default_factory=dict)


class PythonSkeletonExtractor:
    """Python文件骨架提取器"""
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.content = ""
        self.tree = None
    
    def extract(self) -> PythonSkeleton:
        with open(self.file_path, "r", encoding="utf-8", errors="ignore") as f:
            self.content = f.read()
        
        file_name = os.path.basename(self.file_path)
        file_size = os.path.getsize(self.file_path)
        line_count = len(self.content.splitlines())
        
        skeleton = PythonSkeleton(
            file_path=self.file_path,
            file_name=file_name,
            file_size=file_size,
            line_count=line_count,
        )
        
        try:
            self.tree = ast.parse(self.content)
        except SyntaxError:
            return skeleton
        
        skeleton.top_level_docstring = ast.get_docstring(self.tree)
        
        for node in ast.iter_child_nodes(self.tree):
            if isinstance(node, ast.FunctionDef):
                skeleton.functions.append(self._extract_function(node))
            elif isinstance(node, ast.AsyncFunctionDef):
                skeleton.functions.append(self._extract_function(node))
            elif isinstance(node, ast.ClassDef):
                skeleton.classes.append(self._extract_class(node))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    skeleton.imports.append({
                        "module": alias.name,
                        "alias": alias.asname,
                        "is_from_import": False,
                        "line_number": node.lineno,
                    })
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    skeleton.imports.append({
                        "module": module,
                        "name": alias.name,
                        "alias": alias.asname,
                        "is_from_import": True,
                        "line_number": node.lineno,
                    })
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        skeleton.module_variables.append(target.id)
        
        skeleton.exports = self._find_exports()
        skeleton.file_reads = self._find_file_reads()
        skeleton.file_writes = self._find_file_writes()
        skeleton.todos = self._extract_todos()
        skeleton.call_graph = self._build_call_graph()
        skeleton.dependencies = self._extract_dependencies()
        
        return skeleton
    
    def _extract_function(self, node) -> dict:
        params = []
        
        for arg in node.args.args:
            param = {"name": arg.arg}
            if arg.annotation:
                param["type"] = self._get_annotation_string(arg.annotation)
            params.append(param)
        
        if node.args.vararg:
            params.append({"name": f"*{node.args.vararg.arg}"})
        if node.args.kwarg:
            params.append({"name": f"**{node.args.kwarg.arg}"})
        
        decorators = []
        for d in node.decorator_list:
            if isinstance(d, ast.Name):
                decorators.append(d.id)
            elif isinstance(d, ast.Attribute):
                decorators.append(f"{d.value.id}.{d.attr}" if isinstance(d.value, ast.Name) else d.attr)
        
        return_type = None
        if node.returns:
            return_type = self._get_annotation_string(node.returns)
        
        return {
            "name": node.name,
            "parameters": params,
            "return_type": return_type,
            "docstring": ast.get_docstring(node),
            "line_start": node.lineno,
            "line_end": node.end_lineno or node.lineno,
            "decorators": decorators,
            "is_async": isinstance(node, ast.AsyncFunctionDef),
        }
    
    def _extract_class(self, node) -> dict:
        bases = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                bases.append(base.id)
            elif isinstance(base, ast.Attribute):
                bases.append(f"{base.value.id}.{base.attr}" if isinstance(base.value, ast.Name) else base.attr)
        
        methods = []
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods.append(self._extract_function(item))
        
        decorators = []
        for d in node.decorator_list:
            if isinstance(d, ast.Name):
                decorators.append(d.id)
        
        return {
            "name": node.name,
            "bases": bases,
            "methods": methods,
            "docstring": ast.get_docstring(node),
            "line_start": node.lineno,
            "line_end": node.end_lineno or node.lineno,
            "decorators": decorators,
        }
    
    def _get_annotation_string(self, annotation) -> str:
        if isinstance(annotation, ast.Name):
            return annotation.id
        elif isinstance(annotation, ast.Constant):
            return str(annotation.value)
        elif isinstance(annotation, ast.Subscript):
            if isinstance(annotation.value, ast.Name):
                return f"{annotation.value.id}[...]"
        return "Any"
    
    def _find_exports(self) -> list[str]:
        exports = []
        
        if "__all__" in self.content:
            match = re.search(r"__all__\s*=\s*\[([^\]]+)\]", self.content)
            if match:
                exports = re.findall(r"['\"]([^'\"]+)['\"]", match.group(1))
        
        for node in ast.iter_child_nodes(self.tree):
            if isinstance(node, ast.FunctionDef):
                if not node.name.startswith("_"):
                    exports.append(node.name)
            elif isinstance(node, ast.ClassDef):
                if not node.name.startswith("_"):
                    exports.append(node.name)
        
        return list(set(exports))
    
    def _find_file_reads(self) -> list[dict]:
        reads = []
        patterns = [
            (r'read_csv\s*\(\s*["\']([^"\']+)["\']', "pandas.read_csv"),
            (r'read_excel\s*\(\s*["\']([^"\']+)["\']', "pandas.read_excel"),
            (r'read_json\s*\(\s*["\']([^"\']+)["\']', "pandas.read_json"),
            (r'open\s*\(\s*["\']([^"\']+)["\']', "open"),
            (r'load\s*\(\s*["\']([^"\']+)["\']', "load"),
        ]
        
        for pattern, method in patterns:
            for match in re.finditer(pattern, self.content):
                reads.append({
                    "target": match.group(1),
                    "method": method,
                    "line_number": self.content[:match.start()].count("\n") + 1,
                })
        
        return reads
    
    def _find_file_writes(self) -> list[dict]:
        writes = []
        patterns = [
            (r'to_csv\s*\(\s*["\']([^"\']+)["\']', "pandas.to_csv"),
            (r'to_excel\s*\(\s*["\']([^"\']+)["\']', "pandas.to_excel"),
            (r'to_json\s*\(\s*["\']([^"\']+)["\']', "pandas.to_json"),
            (r'save\s*\(\s*["\']([^"\']+)["\']', "save"),
        ]
        
        for pattern, method in patterns:
            for match in re.finditer(pattern, self.content):
                writes.append({
                    "target": match.group(1),
                    "method": method,
                    "line_number": self.content[:match.start()].count("\n") + 1,
                })
        
        return writes
    
    def _extract_todos(self) -> list[dict]:
        todos = []
        todo_pattern = r"#\s*(TODO|FIXME|XXX|HACK):\s*(.+)"
        
        for i, line in enumerate(self.content.splitlines(), 1):
            match = re.search(todo_pattern, line, re.IGNORECASE)
            if match:
                todos.append({
                    "type": match.group(1).upper(),
                    "content": match.group(2).strip(),
                    "line_number": i,
                })
        
        return todos
    
    def _build_call_graph(self) -> dict:
        call_graph = {}
        
        for node in ast.walk(self.tree):
            if isinstance(node, ast.FunctionDef):
                calls = []
                for child in ast.walk(node):
                    if isinstance(child, ast.Call):
                        if isinstance(child.func, ast.Name):
                            calls.append(child.func.id)
                        elif isinstance(child.func, ast.Attribute):
                            calls.append(child.func.attr)
                call_graph[node.name] = list(set(calls))
        
        return call_graph
    
    def _extract_dependencies(self) -> list[str]:
        deps = set()
        
        for imp in ast.walk(self.tree):
            if isinstance(imp, ast.Import):
                for alias in imp.names:
                    deps.add(alias.name.split(".")[0])
            elif isinstance(imp, ast.ImportFrom):
                if imp.module:
                    deps.add(imp.module.split(".")[0])
        
        stdlib = {"os", "sys", "re", "json", "datetime", "collections", "typing", "pathlib", "functools", "itertools", "math", "random", "time", "copy", "dataclasses", "enum", "abc", "io", "logging", "warnings", "contextlib", "threading", "multiprocessing", "subprocess", "argparse", "configparser", "tempfile", "shutil", "glob", "pickle", "sqlite3", "http", "urllib", "email", "html", "xml", "csv"}
        
        return sorted(deps - stdlib)


class JupyterSkeletonExtractor:
    """Jupyter Notebook骨架提取器"""
    
    def __init__(self, file_path: str):
        self.file_path = file_path
    
    def extract(self) -> JupyterSkeleton:
        with open(self.file_path, "r", encoding="utf-8") as f:
            nb = json.load(f)
        
        file_name = os.path.basename(self.file_path)
        file_size = os.path.getsize(self.file_path)
        
        skeleton = JupyterSkeleton(
            file_path=self.file_path,
            file_name=file_name,
            file_size=file_size,
            cell_count=len(nb.get("cells", [])),
        )
        
        for i, cell in enumerate(nb.get("cells", [])):
            cell_type = cell.get("cell_type", "")
            source = "".join(cell.get("source", []))
            
            if cell_type == "code":
                code_cell = {
                    "index": i,
                    "source_preview": source[:200] + "..." if len(source) > 200 else source,
                    "line_count": source.count("\n") + 1,
                    "execution_count": cell.get("execution_count"),
                }
                
                if cell.get("outputs"):
                    code_cell["has_output"] = True
                    code_cell["output_types"] = [
                        o.get("output_type") for o in cell["outputs"]
                    ]
                    skeleton.outputs.append({
                        "cell_index": i,
                        "output_types": code_cell["output_types"],
                    })
                
                skeleton.code_cells.append(code_cell)
                
                try:
                    import_result = self._extract_from_code(source)
                    skeleton.imports.extend(import_result["imports"])
                    skeleton.functions.extend(import_result["functions"])
                    skeleton.classes.extend(import_result["classes"])
                except:
                    pass
            
            elif cell_type == "markdown":
                headings = re.findall(r"^#+\s+(.+)$", source, re.MULTILINE)
                skeleton.markdown_cells.append({
                    "index": i,
                    "headings": headings,
                    "word_count": len(source.split()),
                })
        
        skeleton.imports = self._deduplicate(skeleton.imports, "module")
        skeleton.functions = self._deduplicate(skeleton.functions, "name")
        skeleton.classes = self._deduplicate(skeleton.classes, "name")
        
        return skeleton
    
    def _extract_from_code(self, code: str) -> dict:
        result = {"imports": [], "functions": [], "classes": []}
        
        try:
            tree = ast.parse(code)
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        result["imports"].append({"module": alias.name})
                elif isinstance(node, ast.ImportFrom):
                    result["imports"].append({"module": node.module or "", "is_from_import": True})
                elif isinstance(node, ast.FunctionDef):
                    result["functions"].append({"name": node.name})
                elif isinstance(node, ast.ClassDef):
                    result["classes"].append({"name": node.name})
        except:
            pass
        
        return result
    
    def _deduplicate(self, items: list, key: str) -> list:
        seen = set()
        result = []
        for item in items:
            if item.get(key) not in seen:
                seen.add(item.get(key))
                result.append(item)
        return result


class CSVSkeletonExtractor:
    """CSV文件骨架提取器"""
    
    def __init__(self, file_path: str):
        self.file_path = file_path
    
    def extract(self) -> CSVSkeleton:
        file_name = os.path.basename(self.file_path)
        file_size = os.path.getsize(self.file_path)
        
        skeleton = CSVSkeleton(
            file_path=self.file_path,
            file_name=file_name,
            file_size=file_size,
        )
        
        import csv
        try:
            with open(self.file_path, "r", encoding="utf-8", errors="ignore") as f:
                reader = csv.reader(f)
                rows = list(reader)
                
                if rows:
                    skeleton.column_names = rows[0]
                    skeleton.column_count = len(rows[0])
                    skeleton.row_count = len(rows) - 1
                    
                    skeleton.sample_rows = [
                        dict(zip(skeleton.column_names, row))
                        for row in rows[1:4]
                        if len(row) == skeleton.column_count
                    ]
                    
                    if len(rows) > 1:
                        skeleton.dtypes_guess = self._guess_dtypes(rows[1:min(100, len(rows))])
        except Exception:
            pass
        
        return skeleton
    
    def _guess_dtypes(self, rows: list) -> dict:
        dtypes = {}
        if not rows or not rows[0]:
            return dtypes
        
        for i in range(len(rows[0])):
            col_name = f"col_{i}"
            values = [row[i] if i < len(row) else "" for row in rows]
            
            numeric_count = sum(1 for v in values if self._is_numeric(v))
            if numeric_count > len(values) * 0.8:
                dtypes[col_name] = "numeric"
            elif all(self._is_date(v) for v in values if v):
                dtypes[col_name] = "date"
            else:
                dtypes[col_name] = "string"
        
        return dtypes
    
    def _is_numeric(self, value: str) -> bool:
        try:
            float(value)
            return True
        except:
            return False
    
    def _is_date(self, value: str) -> bool:
        import re
        date_patterns = [
            r"\d{4}-\d{2}-\d{2}",
            r"\d{2}/\d{2}/\d{4}",
            r"\d{4}/\d{2}/\d{2}",
        ]
        return any(re.match(p, value) for p in date_patterns)


class MarkdownSkeletonExtractor:
    """Markdown文件骨架提取器"""
    
    def __init__(self, file_path: str):
        self.file_path = file_path
    
    def extract(self) -> MarkdownSkeleton:
        with open(self.file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        
        file_name = os.path.basename(self.file_path)
        file_size = os.path.getsize(self.file_path)
        
        skeleton = MarkdownSkeleton(
            file_path=self.file_path,
            file_name=file_name,
            file_size=file_size,
        )
        
        skeleton.headings = [
            {"level": len(m.group(1)), "text": m.group(2), "line_number": content[:m.start()].count("\n") + 1}
            for m in re.finditer(r"^(#{1,6})\s+(.+)$", content, re.MULTILINE)
        ]
        
        skeleton.code_blocks = [
            {"language": m.group(1) or "unknown", "line_count": m.group(2).count("\n") + 1}
            for m in re.finditer(r"```(\w*)\n(.*?)```", content, re.DOTALL)
        ]
        
        skeleton.links = [
            {"text": m.group(1), "url": m.group(2)}
            for m in re.finditer(r"\[([^\]]+)\]\(([^)]+)\)", content)
        ]
        
        skeleton.images = [
            {"alt": m.group(1), "src": m.group(2)}
            for m in re.finditer(r"!\[([^\]]*)\]\(([^)]+)\)", content)
        ]
        
        skeleton.todos = [
            {"checked": m.group(1) == "x", "text": m.group(2)}
            for m in re.finditer(r"- \[([ x])\]\s+(.+)$", content, re.MULTILINE)
        ]
        
        words = len(content.split())
        skeleton.word_count = words
        skeleton.reading_time_minutes = max(1, words // 200)
        
        return skeleton


class JSONSkeletonExtractor:
    """JSON文件骨架提取器"""
    
    def __init__(self, file_path: str):
        self.file_path = file_path
    
    def extract(self) -> JSONSkeleton:
        with open(self.file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        file_name = os.path.basename(self.file_path)
        file_size = os.path.getsize(self.file_path)
        
        skeleton = JSONSkeleton(
            file_path=self.file_path,
            file_name=file_name,
            file_size=file_size,
        )
        
        if isinstance(data, dict):
            skeleton.top_level_keys = list(data.keys())
            skeleton.structure_depth = self._get_depth(data)
            skeleton.value_types = {k: type(v).__name__ for k, v in list(data.items())[:10]}
            skeleton.sample_values = {k: self._sample_value(v) for k, v in list(data.items())[:5]}
        
        skeleton.array_lengths = self._find_array_lengths(data)
        
        return skeleton
    
    def _get_depth(self, obj, current: int = 1) -> int:
        if isinstance(obj, dict):
            if not obj:
                return current
            return max(self._get_depth(v, current + 1) for v in obj.values())
        elif isinstance(obj, list):
            if not obj:
                return current
            return max(self._get_depth(item, current + 1) for item in obj)
        return current
    
    def _find_array_lengths(self, obj, path: str = "") -> dict:
        lengths = {}
        if isinstance(obj, dict):
            for k, v in obj.items():
                new_path = f"{path}.{k}" if path else k
                if isinstance(v, list):
                    lengths[new_path] = len(v)
                lengths.update(self._find_array_lengths(v, new_path))
        elif isinstance(obj, list):
            for i, item in enumerate(obj[:10]):
                lengths.update(self._find_array_lengths(item, f"{path}[{i}]"))
        return lengths
    
    def _sample_value(self, value) -> Any:
        if isinstance(value, (str, int, float, bool, type(None))):
            return value
        elif isinstance(value, list):
            return f"[...{len(value)} items]"
        elif isinstance(value, dict):
            return f"{{...{len(value)} keys}}"
        return str(type(value).__name__)


class SkeletonExtractor:
    """项目骨架提取器主类"""
    
    def __init__(self, project_root: str):
        self.project_root = os.path.abspath(project_root)
        self.excludes = {
            "node_modules", "__pycache__", ".git", ".venv", "venv",
            "build", "dist", ".eggs", "*.egg-info", ".mypy_cache",
            ".pytest_cache", ".tox", ".nox", "htmlcov", ".hypothesis",
        }
    
    def extract(self, file_types: Optional[list[str]] = None) -> dict:
        skeleton = ProjectSkeleton(
            project_root=self.project_root,
            scan_time=datetime.now().isoformat(),
        )
        
        for root, dirs, files in os.walk(self.project_root):
            dirs[:] = [d for d in dirs if d not in self.excludes and not d.startswith(".")]
            
            for file in files:
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, self.project_root)
                
                file_skeleton = self._extract_file(file_path, file_types)
                if file_skeleton:
                    self._add_to_skeleton(skeleton, file_skeleton)
        
        skeleton.total_files = (
            len(skeleton.python_files) + len(skeleton.jupyter_files) +
            len(skeleton.csv_files) + len(skeleton.markdown_files) +
            len(skeleton.json_files) + len(skeleton.other_files)
        )
        
        skeleton.summary = self._generate_summary(skeleton)
        
        return asdict(skeleton)
    
    def _extract_file(self, file_path: str, file_types: Optional[list[str]]) -> Optional[dict]:
        ext = os.path.splitext(file_path)[1].lower()
        
        if file_types and ext not in file_types:
            return None
        
        try:
            if ext == ".py":
                extractor = PythonSkeletonExtractor(file_path)
                return {"type": "python", "data": asdict(extractor.extract())}
            elif ext == ".ipynb":
                extractor = JupyterSkeletonExtractor(file_path)
                return {"type": "jupyter", "data": asdict(extractor.extract())}
            elif ext == ".csv":
                extractor = CSVSkeletonExtractor(file_path)
                return {"type": "csv", "data": asdict(extractor.extract())}
            elif ext == ".md":
                extractor = MarkdownSkeletonExtractor(file_path)
                return {"type": "markdown", "data": asdict(extractor.extract())}
            elif ext == ".json":
                extractor = JSONSkeletonExtractor(file_path)
                return {"type": "json", "data": asdict(extractor.extract())}
            else:
                return {
                    "type": "other",
                    "data": {
                        "file_path": file_path,
                        "file_name": os.path.basename(file_path),
                        "file_size": os.path.getsize(file_path),
                        "extension": ext,
                    }
                }
        except Exception as e:
            return None
    
    def _add_to_skeleton(self, skeleton: ProjectSkeleton, file_skeleton: dict):
        file_type = file_skeleton["type"]
        data = file_skeleton["data"]
        
        if file_type == "python":
            skeleton.python_files.append(data)
        elif file_type == "jupyter":
            skeleton.jupyter_files.append(data)
        elif file_type == "csv":
            skeleton.csv_files.append(data)
        elif file_type == "markdown":
            skeleton.markdown_files.append(data)
        elif file_type == "json":
            skeleton.json_files.append(data)
        else:
            skeleton.other_files.append(data)
    
    def _generate_summary(self, skeleton: ProjectSkeleton) -> dict:
        all_imports = set()
        all_functions = []
        all_classes = []
        
        for py in skeleton.python_files:
            for imp in py.get("imports", []):
                all_imports.add(imp.get("module", ""))
            all_functions.extend([f["name"] for f in py.get("functions", [])])
            all_classes.extend([c["name"] for c in py.get("classes", [])])
        
        return {
            "total_python_files": len(skeleton.python_files),
            "total_jupyter_files": len(skeleton.jupyter_files),
            "total_csv_files": len(skeleton.csv_files),
            "total_markdown_files": len(skeleton.markdown_files),
            "total_json_files": len(skeleton.json_files),
            "unique_imports": sorted(all_imports)[:20],
            "total_functions": len(all_functions),
            "total_classes": len(all_classes),
        }


SKELETON_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "ProjMap Skeleton Schema",
    "description": "项目骨架JSON结构定义",
    "type": "object",
    "properties": {
        "project_root": {"type": "string"},
        "scan_time": {"type": "string", "format": "date-time"},
        "total_files": {"type": "integer"},
        "python_files": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "file_name": {"type": "string"},
                    "file_size": {"type": "integer"},
                    "line_count": {"type": "integer"},
                    "imports": {"type": "array"},
                    "exports": {"type": "array"},
                    "functions": {"type": "array"},
                    "classes": {"type": "array"},
                    "file_reads": {"type": "array"},
                    "file_writes": {"type": "array"},
                    "todos": {"type": "array"},
                    "dependencies": {"type": "array"},
                }
            }
        },
        "jupyter_files": {"type": "array"},
        "csv_files": {"type": "array"},
        "markdown_files": {"type": "array"},
        "json_files": {"type": "array"},
        "summary": {"type": "object"}
    }
}
