# 快速入门指南

## 安装

```bash
pip install projmap-ai
```

## 基础使用

### 1. 命令行方式

```bash
# 初始化项目
projmap init ./my_project

# 扫描项目
projmap scan ./my_project

# 生成 HTML 脉络图
projmap scan ./my_project -o map.html

# 查看帮助
projmap --help
```

### 2. Python API 方式

```python
import projmap

# 扫描项目
result = projmap.scan_project("./my_project")

# 查看结果
print(f"文件数量: {len(result.files)}")
for file_info in result.files[:5]:
    print(f"  {file_info.path}")

# 生成 .projmap 文件
projmap.generate_projmap(
    result,
    output="my_project.projmap",
    project_name="My Project"
)
```

## 核心功能

### 信任等级控制

```python
from projmap import TrustLevelExtractor

# Level 1: 仅骨架
# Level 3: 包含注释
# Level 5: 完整代码

extractor = TrustLevelExtractor(trust_level=3)
data = extractor.extract("src/main.py")
```

### 决策管理

```python
from projmap import DecisionManager, DecisionType

dm = DecisionManager()
dm.add_decision(
    node_id="node_001",
    decision_type=DecisionType.ARCHITECTURE,
    title="选择数据库",
    rationale="PostgreSQL 更适合事务处理",
    alternatives=["MySQL", "MongoDB"]
)
```

### 路径状态机

```python
from projmap.state_machine import PathStateMachine, PathState

sm = PathStateMachine("my_project")
sm.register_path("src/core", PathState.ACTIVE_MAIN)
sm.register_path("src/legacy", PathState.ARCHIVED)
```

### 链路分析

```python
from projmap.link_analyzer import analyze_links

files = {
    "main.py": "...",
    "utils.py": "..."
}
result = analyze_links(files)
print(f"发现 {len(result['links'])} 条链路")
```

### 智能布局

```python
from projmap.layout_engine import generate_layout

layout = generate_layout(file_list, dependencies)
print(f"推荐布局: {layout['config']['strategy']}")
```

## 配置

### 环境变量

```bash
export DEEPSEEK_API_KEY="your-api-key"
export PROJMAP_TRUST_LEVEL=3
```

### 配置文件

创建 `~/.projmap/config.json`:

```json
{
    "default_trust_level": 3,
    "exclude_patterns": ["*.pyc", "__pycache__", ".git"]
}
```

## 下一步

- 查看 [README.md](README.md) 了解完整功能
- 查看 [examples/](examples/) 目录的示例代码
- 查看 [schemas/](schemas/) 目录了解 .projmap 文件格式
