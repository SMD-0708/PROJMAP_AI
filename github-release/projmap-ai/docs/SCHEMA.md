# .projmap 文件格式规范

## 概述

`.projmap` 是 ProjMap 项目的核心文件格式，用于描述项目的结构、依赖关系和决策过程。

## 文件结构

```json
{
    "version": "1.0",
    "project": {
        "name": "项目名称",
        "description": "项目描述",
        "root_path": "/path/to/project"
    },
    "nodes": [...],
    "edges": [...],
    "decisions": [...],
    "metadata": {...}
}
```

## 核心字段

### nodes

节点列表，每个节点代表一个文件或目录：

```json
{
    "id": "node_001",
    "label": "main.py",
    "type": "file",
    "path": "src/main.py",
    "language": "python",
    "lines": 100,
    "status": "active_main"
}
```

### edges

边列表，表示节点之间的关系：

```json
{
    "id": "edge_001",
    "source": "node_001",
    "target": "node_002",
    "type": "data_flow",
    "label": "读取 config.yaml"
}
```

### decisions

决策点列表：

```json
{
    "id": "dec_001",
    "node_id": "node_001",
    "type": "architecture",
    "title": "选择数据库",
    "rationale": "PostgreSQL 更适合事务处理",
    "alternatives": ["MySQL", "MongoDB"],
    "timestamp": "2026-01-15T10:00:00Z"
}
```

## 节点类型

| 类型 | 说明 |
|:---|:---|
| `file` | 文件 |
| `directory` | 目录 |
| `data` | 数据文件 |
| `config` | 配置文件 |
| `model` | 模型文件 |

## 边类型

| 类型 | 说明 |
|:---|:---|
| `data_flow` | 数据流 |
| `control_flow` | 控制流 |
| `temporal_flow` | 时序流 |
| `config_dependency` | 配置依赖 |
| `inheritance` | 继承关系 |

## 节点状态

| 状态 | 说明 |
|:---|:---|
| `active_main` | 当前主开发路径 |
| `active_branch` | 活跃分支路径 |
| `dormant` | 休眠路径 |
| `archived` | 归档路径 |

## 完整示例

参见 [schemas/projmap-v2.json](../schemas/projmap-v2.json)
