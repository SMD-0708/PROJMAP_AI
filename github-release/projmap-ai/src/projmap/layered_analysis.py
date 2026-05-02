"""分层深度分析模块

核心功能：
1. 初始扫描时只用骨架信息让AI做语义推断
2. 用户点击节点时才触发深度分析
3. 深度分析结果补充到脉络图中

设计原则：按需深入，避免一次性分析所有文件造成资源浪费。
"""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any
from enum import Enum

from projmap.models import ProjMap, Node, Decision, TechTag, NodeType, DecisionType, DecisionSource
from projmap.skeleton_extractor import PythonSkeletonExtractor, SkeletonExtractor
from projmap.tech_tags import TechTagRecognizer


class AnalysisDepth(Enum):
    SKELETON = "skeleton"
    FUNCTION = "function"
    CLASS = "class"
    FILE = "file"


class InferenceType(Enum):
    FUNCTION_TAG = "function_tag"
    NODE_TYPE = "node_type"
    DECISION_HINT = "decision_hint"
    RELATIONSHIP = "relationship"
    TECH_TAG = "tech_tag"


@dataclass
class InferenceResult:
    inference_type: InferenceType
    content: Any
    confidence: float
    reasoning: str
    needs_confirmation: bool = False


@dataclass
class SkeletonAnalysisResult:
    node_id: str
    function_tags: list[str] = field(default_factory=list)
    node_type: Optional[str] = None
    tech_tags: list[dict] = field(default_factory=list)
    decision_hints: list[dict] = field(default_factory=list)
    relationship_hints: list[dict] = field(default_factory=list)
    confidence: float = 0.0
    needs_confirmation: bool = False


@dataclass
class DeepAnalysisResult:
    node_id: str
    description: str = ""
    new_decisions: list[dict] = field(default_factory=list)
    new_tech_tags: list[dict] = field(default_factory=list)
    updated_function_tags: list[str] = field(default_factory=list)
    input_sources: list[str] = field(default_factory=list)
    output_targets: list[str] = field(default_factory=list)
    artifacts: list[dict] = field(default_factory=list)
    failure_hints: list[dict] = field(default_factory=list)
    confidence: float = 1.0


class SkeletonAnalyzer:
    """骨架分析器 - 基于骨架信息进行语义推断"""
    
    def __init__(self):
        self.tag_recognizer = TechTagRecognizer()
        self._function_patterns = self._build_function_patterns()
        self._node_type_patterns = self._build_node_type_patterns()
        self._decision_patterns = self._build_decision_patterns()
    
    def analyze_python_skeleton(self, skeleton: dict) -> SkeletonAnalysisResult:
        result = SkeletonAnalysisResult(
            node_id=self._generate_node_id(skeleton.get("file_path", "")),
        )
        
        file_name = skeleton.get("file_name", "")
        imports = skeleton.get("imports", [])
        functions = skeleton.get("functions", [])
        classes = skeleton.get("classes", [])
        file_reads = skeleton.get("file_reads", [])
        file_writes = skeleton.get("file_writes", [])
        todos = skeleton.get("todos", [])
        dependencies = skeleton.get("dependencies", [])
        
        result.function_tags = self._infer_function_tags(
            file_name, imports, functions, classes, file_reads, file_writes
        )
        
        result.node_type = self._infer_node_type(
            file_name, functions, classes, imports
        )
        
        result.tech_tags = self._infer_tech_tags_from_skeleton(
            imports, functions, classes, dependencies
        )
        
        result.decision_hints = self._infer_decision_hints(
            todos, functions, classes
        )
        
        result.relationship_hints = self._infer_relationships(
            imports, file_reads, file_writes
        )
        
        result.confidence = self._calculate_confidence(skeleton)
        result.needs_confirmation = result.confidence < 0.7
        
        return result
    
    def _generate_node_id(self, file_path: str) -> str:
        return file_path.replace("/", "_").replace("\\", "_").replace(".", "_")
    
    def _build_function_patterns(self) -> dict:
        return {
            "data_loading": {
                "keywords": ["read_csv", "read_excel", "read_json", "load", "fetch", "download"],
                "imports": ["pandas", "requests", "sqlalchemy", "pyodbc"],
            },
            "data_cleaning": {
                "keywords": ["clean", "preprocess", "transform", "normalize", "fillna", "dropna"],
                "imports": ["pandas", "numpy"],
            },
            "feature_engineering": {
                "keywords": ["feature", "encode", "scale", "extract", "select", "transform"],
                "imports": ["sklearn", "feature_engine"],
            },
            "model_training": {
                "keywords": ["train", "fit", "model", "estimator", "classifier", "regressor"],
                "imports": ["sklearn", "xgboost", "lightgbm", "tensorflow", "torch", "keras"],
            },
            "model_evaluation": {
                "keywords": ["evaluate", "score", "accuracy", "precision", "recall", "predict"],
                "imports": ["sklearn.metrics", "metrics"],
            },
            "visualization": {
                "keywords": ["plot", "chart", "figure", "visualize", "render", "display"],
                "imports": ["matplotlib", "seaborn", "plotly", "bokeh"],
            },
            "api": {
                "keywords": ["app", "router", "endpoint", "route", "handler", "controller"],
                "imports": ["flask", "fastapi", "django", "tornado"],
            },
            "testing": {
                "keywords": ["test", "assert", "mock", "fixture", "setup", "teardown"],
                "imports": ["pytest", "unittest", "mock"],
            },
            "configuration": {
                "keywords": ["config", "setting", "option", "parameter", "env"],
                "imports": ["configparser", "dotenv", "yaml"],
            },
            "utility": {
                "keywords": ["util", "helper", "common", "shared", "tool"],
                "imports": [],
            },
        }
    
    def _build_node_type_patterns(self) -> dict:
        return {
            "entry": {
                "file_patterns": ["main.py", "app.py", "run.py", "__main__.py", "server.py"],
                "function_patterns": ["main", "run", "start", "execute"],
            },
            "module": {
                "file_patterns": [],
                "has_classes": True,
                "has_exports": True,
            },
            "script": {
                "file_patterns": [],
                "has_top_level_code": True,
                "no_classes": True,
            },
            "config": {
                "file_patterns": ["config", "setting", "env"],
                "extensions": [".yaml", ".yml", ".json", ".toml", ".ini"],
            },
            "test": {
                "file_patterns": ["test_", "_test.py"],
                "directories": ["tests", "test"],
            },
            "data": {
                "extensions": [".csv", ".json", ".parquet", ".feather"],
            },
            "notebook": {
                "extensions": [".ipynb"],
            },
        }
    
    def _build_decision_patterns(self) -> dict:
        return {
            "algorithm_selection": {
                "keywords": ["model", "algorithm", "classifier", "regressor", "estimator"],
                "pattern": r"(use|choose|select|adopt)\s+(\w+)\s+(instead|over|rather)",
            },
            "parameter_tuning": {
                "keywords": ["parameter", "hyperparameter", "config", "setting"],
                "pattern": r"(set|tune|adjust)\s+(\w+)\s*(to|=)\s*(\w+)",
            },
            "architecture": {
                "keywords": ["architecture", "structure", "design", "pattern"],
                "pattern": r"(adopt|use|implement)\s+(\w+)\s+(pattern|architecture)",
            },
            "abandonment": {
                "keywords": ["abandon", "deprecated", "obsolete", "remove", "discard"],
                "pattern": r"(abandon|deprecate|remove)\s+(\w+)\s+(because|due|since)",
            },
        }
    
    def _infer_function_tags(
        self, file_name: str, imports: list, functions: list, classes: list, file_reads: list, file_writes: list
    ) -> list[str]:
        tags = set()
        
        import_modules = [i.get("module", "") for i in imports]
        import_names = [i.get("name", "") for i in imports if i.get("is_from_import")]
        
        function_names = [f.get("name", "") for f in functions]
        class_names = [c.get("name", "") for c in classes]
        
        for tag, patterns in self._function_patterns.items():
            keyword_matches = any(
                any(kw in name.lower() for name in function_names + class_names)
                for kw in patterns["keywords"]
            )
            
            import_matches = any(
                any(imp in mod for mod in import_modules)
                for imp in patterns["imports"]
            )
            
            if keyword_matches or import_matches:
                tags.add(tag)
        
        if file_reads:
            tags.add("data_loading")
        if file_writes:
            tags.add("data_export")
        
        if "test_" in file_name.lower() or "_test" in file_name.lower():
            tags.add("testing")
        
        return list(tags) if tags else ["utility"]
    
    def _infer_node_type(self, file_name: str, functions: list, classes: list, imports: list) -> str:
        file_lower = file_name.lower()
        
        if file_lower in ["main.py", "app.py", "run.py", "__main__.py", "server.py"]:
            return "entry"
        
        if file_lower.startswith("test_") or file_lower.endswith("_test.py"):
            return "test"
        
        if any("flask" in i.get("module", "") or "fastapi" in i.get("module", "") for i in imports):
            if "app" in file_lower or "server" in file_lower or "main" in file_lower:
                return "entry"
        
        if classes:
            return "module"
        
        if functions:
            return "script"
        
        return "module"
    
    def _infer_tech_tags_from_skeleton(
        self, imports: list, functions: list, classes: list, dependencies: list
    ) -> list[dict]:
        tags = []
        
        all_text = " ".join(
            [i.get("module", "") for i in imports] +
            [f.get("name", "") for f in functions] +
            [c.get("name", "") for c in classes] +
            dependencies
        )
        
        recognized = self.tag_recognizer.recognize(all_text)
        
        for tag in recognized[:10]:
            tags.append({
                "name": tag.name,
                "category": tag.category,
                "domain": tag.domain,
                "confidence": tag.confidence,
                "source": "skeleton_inference",
            })
        
        return tags
    
    def _infer_decision_hints(self, todos: list, functions: list, classes: list) -> list[dict]:
        hints = []
        
        for todo in todos:
            if todo.get("type") in ["FIXME", "XXX"]:
                hints.append({
                    "type": "pending_fix",
                    "content": todo.get("content", ""),
                    "line_number": todo.get("line_number"),
                })
        
        for func in functions:
            docstring = func.get("docstring", "")
            if docstring:
                for pattern_name, pattern_info in self._decision_patterns.items():
                    import re
                    if re.search(pattern_info["pattern"], docstring, re.IGNORECASE):
                        hints.append({
                            "type": pattern_name,
                            "content": docstring[:200],
                            "function": func.get("name"),
                        })
        
        return hints
    
    def _infer_relationships(self, imports: list, file_reads: list, file_writes: list) -> list[dict]:
        relationships = []
        
        for imp in imports:
            module = imp.get("module", "")
            if module and not module.startswith(("os", "sys", "re", "json", "datetime")):
                relationships.append({
                    "type": "import",
                    "target": module,
                    "line_number": imp.get("line_number"),
                })
        
        for fr in file_reads:
            relationships.append({
                "type": "data_input",
                "target": fr.get("target", ""),
                "method": fr.get("method", ""),
            })
        
        for fw in file_writes:
            relationships.append({
                "type": "data_output",
                "target": fw.get("target", ""),
                "method": fw.get("method", ""),
            })
        
        return relationships
    
    def _calculate_confidence(self, skeleton: dict) -> float:
        confidence = 0.5
        
        if skeleton.get("functions"):
            confidence += 0.1
        if skeleton.get("classes"):
            confidence += 0.1
        if skeleton.get("imports"):
            confidence += 0.1
        if skeleton.get("file_reads") or skeleton.get("file_writes"):
            confidence += 0.1
        if skeleton.get("top_level_docstring"):
            confidence += 0.1
        
        return min(1.0, confidence)


class DeepAnalyzer:
    """深度分析器 - 读取完整代码进行语义理解"""
    
    def __init__(self, llm_service=None):
        self.llm_service = llm_service
        self.skeleton_analyzer = SkeletonAnalyzer()
    
    def analyze_node(self, projmap: ProjMap, node: Node, depth: AnalysisDepth = AnalysisDepth.FILE) -> DeepAnalysisResult:
        result = DeepAnalysisResult(node_id=node.id)
        
        if not os.path.exists(node.file_path):
            result.description = "文件不存在"
            return result
        
        with open(node.file_path, "r", encoding="utf-8", errors="ignore") as f:
            full_content = f.read()
        
        extractor = PythonSkeletonExtractor(node.file_path)
        skeleton = extractor.extract()
        
        if depth == AnalysisDepth.SKELETON:
            skeleton_result = self.skeleton_analyzer.analyze_python_skeleton({
                "file_path": skeleton.file_path,
                "file_name": skeleton.file_name,
                "imports": skeleton.imports,
                "functions": skeleton.functions,
                "classes": skeleton.classes,
                "file_reads": skeleton.file_reads,
                "file_writes": skeleton.file_writes,
                "todos": skeleton.todos,
                "dependencies": skeleton.dependencies,
            })
            
            result.updated_function_tags = skeleton_result.function_tags
            result.confidence = skeleton_result.confidence
            return result
        
        result.description = self._generate_description(skeleton, full_content)
        
        result.new_tech_tags = self._extract_tech_tags(skeleton, full_content)
        
        result.new_decisions = self._extract_decisions(skeleton, full_content, node)
        
        result.input_sources = [fr["target"] for fr in skeleton.file_reads]
        result.output_targets = [fw["target"] for fw in skeleton.file_writes]
        
        result.artifacts = self._detect_artifacts(skeleton, full_content)
        
        result.failure_hints = self._detect_failure_hints(skeleton, full_content)
        
        result.confidence = 0.9
        
        return result
    
    def _generate_description(self, skeleton, full_content: str) -> str:
        parts = []
        
        if skeleton.top_level_docstring:
            parts.append(skeleton.top_level_docstring.split("\n")[0])
        
        if skeleton.classes:
            class_names = [c["name"] for c in skeleton.classes[:3]]
            parts.append(f"包含类: {', '.join(class_names)}")
        
        if skeleton.functions:
            func_names = [f["name"] for f in skeleton.functions[:5] if not f["name"].startswith("_")]
            if func_names:
                parts.append(f"主要函数: {', '.join(func_names)}")
        
        if skeleton.file_reads:
            parts.append(f"读取数据: {skeleton.file_reads[0]['target']}")
        
        if skeleton.file_writes:
            parts.append(f"输出数据: {skeleton.file_writes[0]['target']}")
        
        return " | ".join(parts) if parts else "代码模块"
    
    def _extract_tech_tags(self, skeleton, full_content: str) -> list[dict]:
        recognizer = TechTagRecognizer()
        tags = recognizer.recognize(full_content)
        
        return [
            {
                "name": t.name,
                "category": t.category,
                "domain": t.domain,
                "confidence": t.confidence,
                "source": "deep_analysis",
            }
            for t in tags[:15]
        ]
    
    def _extract_decisions(self, skeleton, full_content: str, node: Node) -> list[dict]:
        decisions = []
        
        import re
        
        decision_patterns = [
            (r"#\s*DECISION:\s*(.+?)(?:\n|$)", "architecture"),
            (r"#\s*WHY:\s*(.+?)(?:\n|$)", "architecture"),
            (r"#\s*ALTERNATIVE:\s*(.+?)(?:\n|$)", "method_selection"),
        ]
        
        for pattern, decision_type in decision_patterns:
            for match in re.finditer(pattern, full_content, re.IGNORECASE):
                decisions.append({
                    "type": decision_type,
                    "content": match.group(1).strip(),
                    "node_id": node.id,
                    "source": "code_annotation",
                })
        
        for todo in skeleton.todos:
            if todo.get("type") == "FIXME":
                decisions.append({
                    "type": "pending_fix",
                    "content": todo.get("content", ""),
                    "line_number": todo.get("line_number"),
                    "node_id": node.id,
                })
        
        return decisions
    
    def _detect_artifacts(self, skeleton, full_content: str) -> list[dict]:
        artifacts = []
        
        for fw in skeleton.file_writes:
            target = fw.get("target", "")
            if target:
                artifacts.append({
                    "type": "output_file",
                    "path": target,
                    "method": fw.get("method", ""),
                })
        
        import re
        model_patterns = [
            (r"\.save\s*\(\s*['\"]([^'\"]+)['\"]", "model"),
            (r"joblib\.dump\s*\([^,]+,\s*['\"]([^'\"]+)['\"]", "model"),
            (r"pickle\.dump\s*\([^,]+,\s*['\"]([^'\"]+)['\"]", "model"),
        ]
        
        for pattern, artifact_type in model_patterns:
            for match in re.finditer(pattern, full_content):
                artifacts.append({
                    "type": artifact_type,
                    "path": match.group(1),
                })
        
        return artifacts
    
    def _detect_failure_hints(self, skeleton, full_content: str) -> list[dict]:
        hints = []
        
        import re
        error_patterns = [
            (r"except\s+(\w+Error|\w+Exception)", "exception_handler"),
            (r"raise\s+(\w+Error|\w+Exception)", "exception_raise"),
            (r"#\s*BUG:\s*(.+?)(?:\n|$)", "known_bug"),
            (r"#\s*FIXME:\s*(.+?)(?:\n|$)", "fixme"),
        ]
        
        for pattern, hint_type in error_patterns:
            for match in re.finditer(pattern, full_content, re.IGNORECASE):
                hints.append({
                    "type": hint_type,
                    "content": match.group(1) if match.lastindex else "",
                    "line_number": full_content[:match.start()].count("\n") + 1,
                })
        
        return hints


class LayeredAnalysisManager:
    """分层分析管理器"""
    
    def __init__(self, projmap: ProjMap, llm_service=None):
        self.projmap = projmap
        self.skeleton_analyzer = SkeletonAnalyzer()
        self.deep_analyzer = DeepAnalyzer(llm_service)
        self._analysis_cache: dict[str, DeepAnalysisResult] = {}
    
    def initial_analysis(self, project_root: str) -> dict:
        extractor = SkeletonExtractor(project_root)
        skeleton_data = extractor.extract(file_types=[".py"])
        
        results = {}
        
        for py_file in skeleton_data.get("python_files", []):
            result = self.skeleton_analyzer.analyze_python_skeleton(py_file)
            results[result.node_id] = {
                "function_tags": result.function_tags,
                "node_type": result.node_type,
                "tech_tags": result.tech_tags,
                "decision_hints": result.decision_hints,
                "relationship_hints": result.relationship_hints,
                "confidence": result.confidence,
                "needs_confirmation": result.needs_confirmation,
            }
        
        return results
    
    def deep_analyze(self, node_id: str, depth: AnalysisDepth = AnalysisDepth.FILE) -> DeepAnalysisResult:
        if node_id in self._analysis_cache:
            return self._analysis_cache[node_id]
        
        node = next((n for n in self.projmap.nodes if n.id == node_id), None)
        if not node:
            return DeepAnalysisResult(node_id=node_id, description="节点不存在")
        
        result = self.deep_analyzer.analyze_node(self.projmap, node, depth)
        
        self._analysis_cache[node_id] = result
        
        self._apply_analysis_result(node, result)
        
        return result
    
    def _apply_analysis_result(self, node: Node, result: DeepAnalysisResult):
        if result.description:
            node.description = result.description
        
        if result.updated_function_tags:
            node.function_tags = result.updated_function_tags
        
        if result.new_tech_tags:
            existing_names = {t.name for t in (node.tech_tags or [])}
            for tag_data in result.new_tech_tags:
                if tag_data["name"] not in existing_names:
                    if not node.tech_tags:
                        node.tech_tags = []
                    node.tech_tags.append(TechTag(
                        name=tag_data["name"],
                        category=tag_data["category"],
                        domain=tag_data["domain"],
                        confidence=tag_data.get("confidence", 1.0),
                        source=tag_data.get("source", "deep_analysis"),
                    ))
        
        if result.input_sources:
            node.input_sources = result.input_sources
        
        if result.output_targets:
            node.output_targets = result.output_targets
        
        if result.artifacts:
            from projmap.models import Artifact
            node.artifacts = [
                Artifact(
                    type=a["type"],
                    path=a["path"],
                    description=a.get("method", ""),
                )
                for a in result.artifacts
            ]
        
        node.confidence = result.confidence
