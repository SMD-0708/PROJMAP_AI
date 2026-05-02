"""信任梯度数据提取器

根据五档信任梯度提取不同深度的代码信息。
档位说明：
- 1档·纯本地：零网络请求，仅骨架脉络
- 2档·骨架：文件路径、函数名、import
- 3档·注释：以上+所有注释
- 4档·参数：以上+关键参数值
- 5档·全量：以上+代码结构骨架
"""

import ast
import os
import re
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class TrustLevelData:
    trust_level: int
    file_path: str = ""
    file_name: str = ""
    language: Optional[str] = None
    imports: list[str] = field(default_factory=list)
    exports: list[str] = field(default_factory=list)
    comments: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    code_structure: str = ""
    function_signatures: list[dict] = field(default_factory=list)
    class_signatures: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        result = {
            "trust_level": self.trust_level,
            "file_path": self.file_path,
        }
        
        if self.trust_level >= 1:
            result["file_name"] = self.file_name
        
        if self.trust_level >= 2:
            result["language"] = self.language
            result["imports"] = self.imports
            result["exports"] = self.exports
        
        if self.trust_level >= 3:
            result["comments"] = self.comments
        
        if self.trust_level >= 4:
            result["parameters"] = self.parameters
        
        if self.trust_level >= 5:
            result["code_structure"] = self.code_structure
            result["function_signatures"] = self.function_signatures
            result["class_signatures"] = self.class_signatures
        
        return result


class TrustLevelExtractor:
    LANGUAGE_CONFIGS = {
        "python": {
            "comment_patterns": [r'#.*$', r'"""[\s\S]*?"""', r"'''[\s\S]*?'''"],
            "param_patterns": [r'(\w+)\s*=\s*([0-9.]+|"[^"]*"|\'[^\']*\')'],
        },
        "javascript": {
            "comment_patterns": [r'//.*$', r'/\*[\s\S]*?\*/'],
            "param_patterns": [r'(\w+)\s*[:=]\s*([0-9.]+|"[^"]*"|\'[^\']*\')'],
        },
        "typescript": {
            "comment_patterns": [r'//.*$', r'/\*[\s\S]*?\*/'],
            "param_patterns": [r'(\w+)\s*[:=]\s*([0-9.]+|"[^"]*"|\'[^\']*\')'],
        },
    }

    def __init__(self, trust_level: int = 1):
        self.trust_level = trust_level

    def extract(self, file_path: str, content: Optional[str] = None) -> TrustLevelData:
        data = TrustLevelData(trust_level=self.trust_level)
        
        if not os.path.exists(file_path):
            return data
        
        data.file_path = file_path
        data.file_name = os.path.basename(file_path)
        
        if content is None:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except (IOError, OSError, UnicodeDecodeError):
                return data
        
        language = self._detect_language(file_path)
        data.language = language
        
        if language == "python":
            self._extract_python(content, data)
        elif language in ("javascript", "typescript"):
            self._extract_js_ts(content, data)
        else:
            self._extract_generic(content, data)
        
        return data

    def _detect_language(self, file_path: str) -> Optional[str]:
        ext = os.path.splitext(file_path)[1].lower()
        lang_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".jsx": "javascript",
            ".go": "go",
            ".rs": "rust",
            ".java": "java",
            ".c": "c",
            ".cpp": "cpp",
            ".h": "c",
            ".hpp": "cpp",
        }
        return lang_map.get(ext)

    def _extract_python(self, content: str, data: TrustLevelData) -> None:
        if self.trust_level >= 2:
            try:
                tree = ast.parse(content)
                
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            data.imports.append(alias.name)
                    elif isinstance(node, ast.ImportFrom):
                        module = node.module or ""
                        data.imports.append(module)
                    elif isinstance(node, ast.FunctionDef):
                        data.exports.append(node.name)
                        if self.trust_level >= 5:
                            args = [arg.arg for arg in node.args.args]
                            data.function_signatures.append({
                                "name": node.name,
                                "args": args,
                                "line": node.lineno,
                            })
                    elif isinstance(node, ast.ClassDef):
                        data.exports.append(node.name)
                        if self.trust_level >= 5:
                            methods = [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
                            data.class_signatures.append({
                                "name": node.name,
                                "methods": methods,
                                "line": node.lineno,
                            })
            except SyntaxError:
                pass
        
        if self.trust_level >= 3:
            comments = []
            for match in re.finditer(r'#.*$', content, re.MULTILINE):
                comments.append(match.group().strip())
            for match in re.finditer(r'"""[\s\S]*?"""', content):
                comments.append(match.group().strip())
            for match in re.finditer(r"'''[\s\S]*?'''", content):
                comments.append(match.group().strip())
            data.comments = "\n".join(comments)
        
        if self.trust_level >= 4:
            params = {}
            param_pattern = r'([A-Z_][A-Z0-9_]*)\s*=\s*([0-9.]+|"[^"]*"|\'[^\']*\'|\[[^\]]*\]|\{[^}]*\})'
            for match in re.finditer(param_pattern, content):
                key, value = match.groups()
                if key not in ["TRUE", "FALSE", "NONE", "IF", "ELSE", "FOR", "WHILE"]:
                    params[key] = value.strip('"\'')
            
            func_param_pattern = r'def\s+\w+\s*\([^)]*([a-z_]\w*)\s*=\s*([0-9.]+|"[^"]*"|\'[^\']*\')'
            for match in re.finditer(func_param_pattern, content):
                key, value = match.groups()
                params[f"param_{key}"] = value.strip('"\'')
            
            data.parameters = params
        
        if self.trust_level >= 5:
            lines = content.split("\n")
            structure_lines = []
            indent_stack = [0]
            
            for i, line in enumerate(lines):
                stripped = line.lstrip()
                if not stripped or stripped.startswith("#"):
                    continue
                
                indent = len(line) - len(stripped)
                
                if stripped.startswith("def "):
                    structure_lines.append(f"{'  ' * len(indent_stack)}{stripped.split('(')[0]}")
                elif stripped.startswith("class "):
                    structure_lines.append(f"{'  ' * len(indent_stack)}{stripped.split(':')[0]}")
                elif stripped.startswith("if __name__"):
                    structure_lines.append(f"{'  ' * len(indent_stack)}if __name__ == '__main__'")
            
            data.code_structure = "\n".join(structure_lines)

    def _extract_js_ts(self, content: str, data: TrustLevelData) -> None:
        if self.trust_level >= 2:
            import_patterns = [
                r'import\s+.*?from\s+[\'"]([^\'"]+)[\'"]',
                r'import\s+[\'"]([^\'"]+)[\'"]',
                r'require\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)',
            ]
            for pattern in import_patterns:
                for match in re.finditer(pattern, content):
                    data.imports.append(match.group(1))
            
            export_patterns = [
                r'export\s+(?:default\s+)?function\s+(\w+)',
                r'export\s+(?:default\s+)?class\s+(\w+)',
                r'export\s+(?:const|let|var)\s+(\w+)',
            ]
            for pattern in export_patterns:
                for match in re.finditer(pattern, content):
                    data.exports.append(match.group(1))
        
        if self.trust_level >= 3:
            comments = []
            for match in re.finditer(r'//.*$', content, re.MULTILINE):
                comments.append(match.group().strip())
            for match in re.finditer(r'/\*[\s\S]*?\*/', content):
                comments.append(match.group().strip())
            data.comments = "\n".join(comments)
        
        if self.trust_level >= 4:
            params = {}
            param_pattern = r'(\w+)\s*[:=]\s*([0-9.]+|"[^"]*"|\'[^\']*\'|\[[^\]]*\]|\{[^}]*\})'
            for match in re.finditer(param_pattern, content):
                key, value = match.groups()
                if key not in ["const", "let", "var", "function", "class", "if", "else", "for", "while"]:
                    params[key] = value.strip('"\'')
            data.parameters = params
        
        if self.trust_level >= 5:
            lines = content.split("\n")
            structure_lines = []
            
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("function ") or stripped.startswith("const ") and "=>" in stripped:
                    structure_lines.append(stripped.split("{")[0].strip())
                elif stripped.startswith("class "):
                    structure_lines.append(stripped.split("{")[0].strip())
                elif "export " in stripped:
                    structure_lines.append(stripped)
            
            data.code_structure = "\n".join(structure_lines)

    def _extract_generic(self, content: str, data: TrustLevelData) -> None:
        if self.trust_level >= 2:
            import_pattern = r'import\s+([a-zA-Z0-9_.]+)'
            for match in re.finditer(import_pattern, content):
                data.imports.append(match.group(1))
        
        if self.trust_level >= 3:
            comments = []
            for match in re.finditer(r'#.*$', content, re.MULTILINE):
                comments.append(match.group().strip())
            for match in re.finditer(r'//.*$', content, re.MULTILINE):
                comments.append(match.group().strip())
            data.comments = "\n".join(comments)


def extract_for_trust_level(
    file_path: str,
    trust_level: int,
    content: Optional[str] = None,
) -> dict:
    extractor = TrustLevelExtractor(trust_level=trust_level)
    data = extractor.extract(file_path, content)
    return data.to_dict()
