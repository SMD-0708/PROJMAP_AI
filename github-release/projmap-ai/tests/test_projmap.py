"""ProjMap 单元测试"""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from projmap.models import (
    Node,
    Edge,
    Decision,
    ProjMap,
    Metadata,
    NodeStatus,
    NodeType,
    EdgeType,
    DecisionType,
    generate_node_id,
    generate_edge_id,
)
from projmap.scanner import ProjectScanner, FileInfo, scan_project
from projmap.trust_level import TrustLevelExtractor, extract_for_trust_level
from projmap.decision_manager import DecisionManager


class TestModels:
    """数据模型测试"""
    
    def test_node_creation(self):
        node = Node(
            id="test_node",
            name="Test Node",
            file_path="test.py",
            status=NodeStatus.ACTIVE_MAIN,
        )
        assert node.id == "test_node"
        assert node.name == "Test Node"
        assert node.status == NodeStatus.ACTIVE_MAIN
        assert node.type == NodeType.FILE
    
    def test_node_to_dict(self):
        node = Node(
            id="test_node",
            name="Test",
            file_path="test.py",
            status=NodeStatus.ACTIVE_BRANCH,
            function_tags=["test", "example"],
        )
        d = node.to_dict()
        assert d["id"] == "test_node"
        assert d["name"] == "Test"
        assert d["status"] == "active_branch"
        assert d["function_tags"] == ["test", "example"]
    
    def test_node_from_dict(self):
        data = {
            "id": "test_node",
            "name": "Test",
            "file_path": "test.py",
            "status": "dormant",
        }
        node = Node.from_dict(data)
        assert node.id == "test_node"
        assert node.status == NodeStatus.DORMANT
    
    def test_edge_creation(self):
        edge = Edge(
            id="test_edge",
            source="node1",
            target="node2",
            type=EdgeType.IMPORTS,
        )
        assert edge.source == "node1"
        assert edge.target == "node2"
        assert edge.type == EdgeType.IMPORTS
    
    def test_decision_creation(self):
        decision = Decision(
            id="test_decision",
            node_id="node1",
            type=DecisionType.ALGORITHM,
            content="选择随机森林",
            timestamp=datetime.now(),
        )
        assert decision.type == DecisionType.ALGORITHM
        assert decision.content == "选择随机森林"
    
    def test_projmap_serialization(self):
        projmap = ProjMap(
            version="1.0",
            metadata=Metadata(
                project_name="Test Project",
                project_root="/tmp/test",
                created_at=datetime.now(),
            ),
            nodes=[
                Node(
                    id="node1",
                    name="Main",
                    file_path="main.py",
                    status=NodeStatus.ACTIVE_MAIN,
                )
            ],
            edges=[],
        )
        
        json_str = projmap.to_json()
        data = json.loads(json_str)
        assert data["version"] == "1.0"
        assert data["metadata"]["project_name"] == "Test Project"
        assert len(data["nodes"]) == 1
        
        loaded = ProjMap.from_json(json_str)
        assert loaded.version == "1.0"
        assert len(loaded.nodes) == 1
    
    def test_generate_node_id(self):
        id1 = generate_node_id("test.py")
        id2 = generate_node_id("test.py")
        id3 = generate_node_id("other.py")
        
        assert id1 == id2
        assert id1 != id3
        assert id1.startswith("node_")


class TestScanner:
    """文件扫描测试"""
    
    @pytest.fixture
    def temp_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "main.py").write_text("print('hello')")
            Path(tmpdir, "utils.py").write_text("def helper(): pass")
            
            subdir = Path(tmpdir, "data")
            subdir.mkdir()
            Path(subdir, "loader.py").write_text("def load(): pass")
            
            yield tmpdir
    
    def test_scan_project(self, temp_project):
        result = scan_project(temp_project)
        
        assert result.total_files == 3
        assert result.total_directories == 1
        assert len(result.files) == 3
    
    def test_scan_excludes(self, temp_project):
        Path(temp_project, "__pycache__").mkdir()
        Path(temp_project, "__pycache__", "test.pyc").write_text("")
        
        result = scan_project(temp_project)
        assert result.total_files == 3
    
    def test_file_info(self, temp_project):
        result = scan_project(temp_project)
        
        main_file = next(f for f in result.files if f.name == "main.py")
        assert main_file.language == "python"
        assert main_file.is_text_file


class TestTrustLevel:
    """信任梯度测试"""
    
    @pytest.fixture
    def temp_python_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('''
"""模块文档字符串"""

import os
import sys

MAX_SIZE = 100
DEFAULT_NAME = "test"

def main(data_path: str = "data.csv", epochs: int = 10):
    """主函数"""
    pass

class DataProcessor:
    def process(self):
        pass
''')
            yield f.name
        os.unlink(f.name)
    
    def test_trust_level_1(self, temp_python_file):
        data = extract_for_trust_level(temp_python_file, 1)
        assert data["trust_level"] == 1
        assert data["file_path"] != ""
        assert "imports" not in data or data.get("imports") == []
    
    def test_trust_level_2(self, temp_python_file):
        data = extract_for_trust_level(temp_python_file, 2)
        assert data["trust_level"] == 2
        assert len(data.get("imports", [])) > 0
        assert len(data.get("exports", [])) > 0
    
    def test_trust_level_3(self, temp_python_file):
        data = extract_for_trust_level(temp_python_file, 3)
        assert data["trust_level"] == 3
        assert len(data.get("comments", "")) > 0
    
    def test_trust_level_4(self, temp_python_file):
        data = extract_for_trust_level(temp_python_file, 4)
        assert data["trust_level"] == 4
        assert len(data.get("parameters", {})) > 0
    
    def test_trust_level_5(self, temp_python_file):
        data = extract_for_trust_level(temp_python_file, 5)
        assert data["trust_level"] == 5
        assert len(data.get("code_structure", "")) > 0


class TestDecisionManager:
    """决策点管理测试"""
    
    @pytest.fixture
    def projmap(self):
        return ProjMap(
            nodes=[
                Node(
                    id="node1",
                    name="Main",
                    file_path="main.py",
                    status=NodeStatus.ACTIVE_MAIN,
                )
            ]
        )
    
    def test_add_decision(self, projmap):
        manager = DecisionManager(projmap)
        
        decision = manager.add_decision(
            node_id="node1",
            decision_type="algorithm",
            content="选择随机森林",
            reason="效果最好",
        )
        
        assert len(projmap.decisions) == 1
        assert decision.content == "选择随机森林"
    
    def test_get_decisions_by_node(self, projmap):
        manager = DecisionManager(projmap)
        
        manager.add_decision("node1", "algorithm", "决策1")
        manager.add_decision("node1", "parameter", "决策2")
        
        decisions = manager.get_decisions_by_node("node1")
        assert len(decisions) == 2
    
    def test_search_decisions(self, projmap):
        manager = DecisionManager(projmap)
        
        manager.add_decision("node1", "algorithm", "选择随机森林分类器")
        manager.add_decision("node1", "parameter", "设置学习率为0.01")
        
        results = manager.search_decisions("随机森林")
        assert len(results) == 1
        assert "随机森林" in results[0].content
    
    def test_parameter_history(self, projmap):
        manager = DecisionManager(projmap)
        
        manager.add_decision("node1", "parameter", "设置参数", parameters={"lr": 0.01})
        manager.add_decision("node1", "parameter", "调整参数", parameters={"lr": 0.001})
        
        history = manager.get_parameter_history("lr")
        assert len(history) == 2


class TestNodeStatus:
    """节点状态测试"""
    
    def test_status_values(self):
        assert NodeStatus.ACTIVE_MAIN.value == "active_main"
        assert NodeStatus.ACTIVE_BRANCH.value == "active_branch"
        assert NodeStatus.DORMANT.value == "dormant"
        assert NodeStatus.ARCHIVED.value == "archived"
    
    def test_status_from_string(self):
        status = NodeStatus("dormant")
        assert status == NodeStatus.DORMANT


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
