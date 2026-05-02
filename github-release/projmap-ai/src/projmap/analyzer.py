"""依赖分析模块

本模块负责分析文件间的依赖关系，提取导入导出信息。
设计原则：
1. 使用正则表达式进行轻量级解析（MVP阶段避免AST复杂性）
2. 支持多种编程语言
3. 将相对导入映射到实际文件路径
4. 提取函数/类定义作为导出信息
"""

import os
import re
from dataclasses import dataclass, field
from typing import Optional


PYTHON_IMPORT_PATTERNS = [
    re.compile(r'^import\s+([a-zA-Z0-9_.]+)', re.MULTILINE),
    re.compile(r'^from\s+([a-zA-Z0-9_.]+)\s+import', re.MULTILINE),
]

PYTHON_EXPORT_PATTERNS = [
    re.compile(r'^def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(', re.MULTILINE),
    re.compile(r'^class\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*[:\(]', re.MULTILINE),
    re.compile(r'^([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*', re.MULTILINE),
]

JS_IMPORT_PATTERNS = [
    re.compile(r'import\s+.*?from\s+[\'"]([^\'"]+)[\'"]', re.MULTILINE),
    re.compile(r'import\s+[\'"]([^\'"]+)[\'"]', re.MULTILINE),
    re.compile(r'require\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)', re.MULTILINE),
]

JS_EXPORT_PATTERNS = [
    re.compile(r'export\s+(?:default\s+)?function\s+([a-zA-Z_][a-zA-Z0-9_]*)', re.MULTILINE),
    re.compile(r'export\s+(?:default\s+)?class\s+([a-zA-Z_][a-zA-Z0-9_]*)', re.MULTILINE),
    re.compile(r'export\s+(?:const|let|var)\s+([a-zA-Z_][a-zA-Z0-9_]*)', re.MULTILINE),
    re.compile(r'export\s+\{\s*([^}]+)\s*\}', re.MULTILINE),
]

GO_IMPORT_PATTERNS = [
    re.compile(r'import\s+(?:\(\s*)?"([^"]+)"', re.MULTILINE),
]

RUST_USE_PATTERNS = [
    re.compile(r'use\s+([a-zA-Z0-9_:]+)', re.MULTILINE),
]

JAVA_IMPORT_PATTERNS = [
    re.compile(r'import\s+([a-zA-Z0-9_.]+);', re.MULTILINE),
]


@dataclass
class ImportInfo:
    module: str
    is_relative: bool = False
    line_number: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "module": self.module,
            "is_relative": self.is_relative,
            "line_number": self.line_number,
        }


@dataclass
class ExportInfo:
    name: str
    type: str  # function, class, variable
    line_number: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.type,
            "line_number": self.line_number,
        }


@dataclass
class DependencyInfo:
    file_path: str
    imports: list[ImportInfo] = field(default_factory=list)
    exports: list[ExportInfo] = field(default_factory=list)
    file_reads: list[str] = field(default_factory=list)
    file_writes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "file_path": self.file_path,
            "imports": [i.to_dict() for i in self.imports],
            "exports": [e.to_dict() for e in self.exports],
            "file_reads": self.file_reads,
            "file_writes": self.file_writes,
        }


@dataclass
class DependencyEdge:
    source_file: str
    target_file: str
    import_module: str
    is_internal: bool = False

    def to_dict(self) -> dict:
        return {
            "source_file": self.source_file,
            "target_file": self.target_file,
            "import_module": self.import_module,
            "is_internal": self.is_internal,
        }


class DependencyAnalyzer:
    def __init__(self, root_path: str, file_list: list[str]):
        self.root_path = os.path.abspath(root_path)
        self.file_list = file_list
        self._file_index = self._build_file_index()

    def _build_file_index(self) -> dict[str, str]:
        index = {}
        for file_path in self.file_list:
            rel_path = os.path.relpath(file_path, self.root_path)
            rel_path = rel_path.replace("\\", "/")
            
            index[rel_path] = file_path
            
            base_name = os.path.splitext(rel_path)[0]
            index[base_name] = file_path
            
            if rel_path.endswith("/__init__.py"):
                package_path = os.path.dirname(rel_path)
                index[package_path] = file_path
        
        return index

    def _find_line_number(self, content: str, match_start: int) -> int:
        return content[:match_start].count("\n") + 1

    def _parse_python_imports(self, content: str) -> list[ImportInfo]:
        imports = []
        for pattern in PYTHON_IMPORT_PATTERNS:
            for match in pattern.finditer(content):
                module = match.group(1)
                is_relative = module.startswith(".")
                line_number = self._find_line_number(content, match.start())
                imports.append(ImportInfo(
                    module=module,
                    is_relative=is_relative,
                    line_number=line_number,
                ))
        return imports

    def _parse_python_exports(self, content: str) -> list[ExportInfo]:
        exports = []
        for i, match in enumerate(PYTHON_EXPORT_PATTERNS):
            for m in match.finditer(content):
                name = m.group(1)
                line_number = self._find_line_number(content, m.start())
                export_type = ["function", "class", "variable"][i] if i < 3 else "unknown"
                exports.append(ExportInfo(
                    name=name,
                    type=export_type,
                    line_number=line_number,
                ))
        return exports

    def _parse_js_imports(self, content: str) -> list[ImportInfo]:
        imports = []
        for pattern in JS_IMPORT_PATTERNS:
            for match in pattern.finditer(content):
                module = match.group(1)
                is_relative = module.startswith(".") or module.startswith("/")
                line_number = self._find_line_number(content, match.start())
                imports.append(ImportInfo(
                    module=module,
                    is_relative=is_relative,
                    line_number=line_number,
                ))
        return imports

    def _parse_js_exports(self, content: str) -> list[ExportInfo]:
        exports = []
        for i, pattern in enumerate(JS_EXPORT_PATTERNS):
            for match in pattern.finditer(content):
                if i == 3:
                    names = match.group(1)
                    for name in names.split(","):
                        name = name.strip().split(" as ")[-1].strip()
                        if name:
                            exports.append(ExportInfo(name=name, type="variable"))
                else:
                    name = match.group(1)
                    export_type = ["function", "class", "variable"][i] if i < 3 else "variable"
                    line_number = self._find_line_number(content, match.start())
                    exports.append(ExportInfo(
                        name=name,
                        type=export_type,
                        line_number=line_number,
                    ))
        return exports

    def _parse_go_imports(self, content: str) -> list[ImportInfo]:
        imports = []
        for match in GO_IMPORT_PATTERNS[0].finditer(content):
            module = match.group(1)
            line_number = self._find_line_number(content, match.start())
            imports.append(ImportInfo(
                module=module,
                is_relative=False,
                line_number=line_number,
            ))
        return imports

    def _parse_rust_imports(self, content: str) -> list[ImportInfo]:
        imports = []
        for match in RUST_USE_PATTERNS[0].finditer(content):
            module = match.group(1).replace("::", "/")
            line_number = self._find_line_number(content, match.start())
            imports.append(ImportInfo(
                module=module,
                is_relative=False,
                line_number=line_number,
            ))
        return imports

    def _parse_java_imports(self, content: str) -> list[ImportInfo]:
        imports = []
        for match in JAVA_IMPORT_PATTERNS[0].finditer(content):
            module = match.group(1).replace(".", "/")
            line_number = self._find_line_number(content, match.start())
            imports.append(ImportInfo(
                module=module,
                is_relative=False,
                line_number=line_number,
            ))
        return imports

    def analyze_file(self, file_path: str, language: str) -> DependencyInfo:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except (IOError, OSError, UnicodeDecodeError):
            return DependencyInfo(file_path=file_path)

        rel_path = os.path.relpath(file_path, self.root_path).replace("\\", "/")
        dep_info = DependencyInfo(file_path=rel_path)

        if language == "python":
            dep_info.imports = self._parse_python_imports(content)
            dep_info.exports = self._parse_python_exports(content)
        elif language in ("javascript", "typescript"):
            dep_info.imports = self._parse_js_imports(content)
            dep_info.exports = self._parse_js_exports(content)
        elif language == "go":
            dep_info.imports = self._parse_go_imports(content)
        elif language == "rust":
            dep_info.imports = self._parse_rust_imports(content)
        elif language == "java":
            dep_info.imports = self._parse_java_imports(content)

        return dep_info

    def _resolve_relative_import(self, import_module: str, source_file: str) -> Optional[str]:
        source_dir = os.path.dirname(source_file)
        
        if import_module.startswith(".."):
            parts = import_module.split("/")
            up_count = sum(1 for p in parts if p == "..")
            remaining = "/".join(p for p in parts if p != "..")
            
            target_dir = source_dir
            for _ in range(up_count):
                target_dir = os.path.dirname(target_dir)
            
            if remaining:
                resolved = os.path.join(target_dir, remaining).replace("\\", "/")
            else:
                resolved = target_dir
        elif import_module.startswith("."):
            module_path = import_module.lstrip(".")
            if module_path:
                resolved = os.path.join(source_dir, module_path).replace("\\", "/")
            else:
                resolved = source_dir
        else:
            resolved = import_module

        for ext in ["", ".py", "/__init__.py", ".js", ".ts", ".tsx", ".jsx"]:
            test_path = resolved + ext
            if test_path in self._file_index:
                return self._file_index[test_path]

        return None

    def resolve_dependencies(self, dep_info: DependencyInfo) -> list[DependencyEdge]:
        edges = []
        source_file = dep_info.file_path

        for imp in dep_info.imports:
            if imp.is_relative:
                target_file = self._resolve_relative_import(imp.module, source_file)
                if target_file:
                    rel_target = os.path.relpath(target_file, self.root_path).replace("\\", "/")
                    edges.append(DependencyEdge(
                        source_file=source_file,
                        target_file=rel_target,
                        import_module=imp.module,
                        is_internal=True,
                    ))
            else:
                parts = imp.module.split(".")
                for i in range(len(parts), 0, -1):
                    test_module = "/".join(parts[:i])
                    if test_module in self._file_index:
                        target_file = self._file_index[test_module]
                        rel_target = os.path.relpath(target_file, self.root_path).replace("\\", "/")
                        edges.append(DependencyEdge(
                            source_file=source_file,
                            target_file=rel_target,
                            import_module=imp.module,
                            is_internal=True,
                        ))
                        break

        return edges


def analyze_dependencies(
    root_path: str,
    file_infos: list[dict],
) -> tuple[dict[str, DependencyInfo], list[DependencyEdge]]:
    file_list = [f["path"] for f in file_infos]
    analyzer = DependencyAnalyzer(root_path, file_list)

    dep_infos = {}
    all_edges = []

    for file_info in file_infos:
        file_path = file_info["path"]
        language = file_info.get("language")
        
        if language:
            dep_info = analyzer.analyze_file(file_path, language)
            dep_infos[dep_info.file_path] = dep_info
            
            edges = analyzer.resolve_dependencies(dep_info)
            all_edges.extend(edges)

    return dep_infos, all_edges
