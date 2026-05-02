"""文件扫描模块

本模块负责扫描项目目录，收集文件信息，过滤不需要的文件。
设计原则：
1. 默认排除常见的非代码目录（.git, __pycache__, node_modules等）
2. 支持 .gitignore 规则
3. 识别多种编程语言
4. 提供可配置的排除规则
"""

import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import pathspec
    HAS_PATHSPEC = True
except ImportError:
    HAS_PATHSPEC = False


LANGUAGE_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".java": "java",
    ".c": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".rs": "rust",
    ".go": "go",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
    ".r": "r",
    ".R": "r",
    ".m": "matlab",
    ".jl": "julia",
    ".lua": "lua",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".ps1": "powershell",
    ".sql": "sql",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".less": "less",
    ".vue": "vue",
    ".svelte": "svelte",
}

DEFAULT_EXCLUDES = [
    ".git",
    ".svn",
    ".hg",
    "__pycache__",
    "node_modules",
    "venv",
    ".venv",
    "env",
    ".env",
    ".idea",
    ".vscode",
    "dist",
    "build",
    "*.egg-info",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    "*.pyc",
    "*.pyo",
    "*.pyd",
    ".DS_Store",
    "Thumbs.db",
    "*.log",
    "*.tmp",
    "*.temp",
    ".projmap",
]


@dataclass
class FileInfo:
    path: str
    relative_path: str
    name: str
    extension: str
    language: Optional[str]
    size: int
    modified_time: datetime
    is_text_file: bool = True

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "relative_path": self.relative_path,
            "name": self.name,
            "extension": self.extension,
            "language": self.language,
            "size": self.size,
            "modified_time": self.modified_time.isoformat(),
            "is_text_file": self.is_text_file,
        }


@dataclass
class ScanResult:
    root_path: str
    files: list[FileInfo] = field(default_factory=list)
    directories: list[str] = field(default_factory=list)
    total_files: int = 0
    total_directories: int = 0
    scan_time: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "root_path": self.root_path,
            "files": [f.to_dict() for f in self.files],
            "directories": self.directories,
            "total_files": self.total_files,
            "total_directories": self.total_directories,
            "scan_time": self.scan_time.isoformat() if self.scan_time else None,
        }


class ProjectScanner:
    def __init__(
        self,
        root_path: str,
        excludes: Optional[list[str]] = None,
        use_gitignore: bool = True,
        include_hidden: bool = False,
        max_depth: Optional[int] = None,
        extensions: Optional[list[str]] = None,
    ):
        self.root_path = os.path.abspath(root_path)
        self.excludes = excludes if excludes is not None else DEFAULT_EXCLUDES.copy()
        self.use_gitignore = use_gitignore
        self.include_hidden = include_hidden
        self.max_depth = max_depth
        self.extensions = extensions
        self._gitignore_spec = None

        if use_gitignore and HAS_PATHSPEC:
            self._load_gitignore()

    def _load_gitignore(self) -> None:
        gitignore_path = os.path.join(self.root_path, ".gitignore")
        if os.path.exists(gitignore_path):
            with open(gitignore_path, "r", encoding="utf-8") as f:
                patterns = f.read().splitlines()
            self._gitignore_spec = pathspec.PathSpec.from_lines(
                pathspec.patterns.GitWildMatchPattern,
                [p for p in patterns if p and not p.startswith("#")]
            )

    def _should_exclude(self, relative_path: str, name: str) -> bool:
        if not self.include_hidden and name.startswith("."):
            return True

        for pattern in self.excludes:
            if pattern.startswith("*."):
                if name.endswith(pattern[1:]):
                    return True
            elif name == pattern:
                return True
            elif relative_path.startswith(pattern + "/") or "/" + pattern + "/" in "/" + relative_path:
                return True

        if self._gitignore_spec:
            if self._gitignore_spec.match_file(relative_path):
                return True

        return False

    def _get_language(self, extension: str) -> Optional[str]:
        return LANGUAGE_EXTENSIONS.get(extension.lower())

    def _is_text_file(self, file_path: str) -> bool:
        try:
            with open(file_path, "rb") as f:
                chunk = f.read(8192)
            if b"\x00" in chunk:
                return False
            try:
                chunk.decode("utf-8")
                return True
            except UnicodeDecodeError:
                try:
                    chunk.decode("gbk")
                    return True
                except UnicodeDecodeError:
                    return False
        except (IOError, OSError):
            return False

    def _should_include_extension(self, extension: str) -> bool:
        if self.extensions is None:
            return True
        return extension.lower() in [e.lower() for e in self.extensions]

    def scan(self) -> ScanResult:
        result = ScanResult(root_path=self.root_path, scan_time=datetime.now())
        
        for root, dirs, files in os.walk(self.root_path):
            rel_root = os.path.relpath(root, self.root_path)
            if rel_root == ".":
                rel_root = ""

            if self.max_depth is not None:
                depth = rel_root.count(os.sep) if rel_root else 0
                if depth > self.max_depth:
                    continue

            dirs_to_remove = []
            for dir_name in dirs:
                dir_rel_path = os.path.join(rel_root, dir_name) if rel_root else dir_name
                if self._should_exclude(dir_rel_path, dir_name):
                    dirs_to_remove.append(dir_name)
                else:
                    result.directories.append(os.path.join(root, dir_name))
                    result.total_directories += 1

            for d in dirs_to_remove:
                dirs.remove(d)

            for file_name in files:
                file_rel_path = os.path.join(rel_root, file_name) if rel_root else file_name
                
                if self._should_exclude(file_rel_path, file_name):
                    continue

                file_path = os.path.join(root, file_name)
                extension = os.path.splitext(file_name)[1].lower()

                if not self._should_include_extension(extension):
                    continue

                try:
                    stat = os.stat(file_path)
                    is_text = self._is_text_file(file_path)
                    
                    file_info = FileInfo(
                        path=file_path,
                        relative_path=file_rel_path.replace("\\", "/"),
                        name=file_name,
                        extension=extension,
                        language=self._get_language(extension),
                        size=stat.st_size,
                        modified_time=datetime.fromtimestamp(stat.st_mtime),
                        is_text_file=is_text,
                    )
                    result.files.append(file_info)
                    result.total_files += 1
                except (IOError, OSError):
                    continue

        return result

    def scan_by_language(self, language: str) -> list[FileInfo]:
        result = self.scan()
        return [f for f in result.files if f.language == language]

    def get_entry_files(self) -> list[FileInfo]:
        result = self.scan()
        entry_patterns = [
            "main.py", "app.py", "run.py", "server.py", "index.py",
            "main.js", "index.js", "app.js", "server.js",
            "main.go", "main.rs", "Main.java",
            "__main__.py",
        ]
        
        entry_files = []
        for f in result.files:
            if f.name in entry_patterns:
                entry_files.append(f)
        
        return entry_files


def scan_project(
    root_path: str,
    excludes: Optional[list[str]] = None,
    use_gitignore: bool = True,
    include_hidden: bool = False,
    max_depth: Optional[int] = None,
    extensions: Optional[list[str]] = None,
) -> ScanResult:
    scanner = ProjectScanner(
        root_path=root_path,
        excludes=excludes,
        use_gitignore=use_gitignore,
        include_hidden=include_hidden,
        max_depth=max_depth,
        extensions=extensions,
    )
    return scanner.scan()
