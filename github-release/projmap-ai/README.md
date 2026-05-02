# ProjMap - 智能项目认知脉络系统

[![PyPI version](https://badge.fury.io/py/projmap-ai.svg)](https://badge.fury.io/py/projmap-ai)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**ProjMap** 是一个开源的智能项目认知脉络系统，通过生成 `.projmap` 文件标准，帮助开发者和 AI 助手深度理解项目结构、依赖关系和关键决策。

## 🎯 解决的六大核心痛点

| 痛点 | 解决方案 | 效果 |
|:---|:---|:---|
| **知识断层** | 项目导航器 | 智能推荐阅读路径，快速理解项目 |
| **AI 污染** | 路径状态机 | 隔离已完成代码，防止上下文混乱 |
| **决策遗忘** | 决策追溯器 | 记录关键决策及理由，支持回溯 |
| **踩坑复现** | 失败检索器 | 标记错误和解决方案，避免重复踩坑 |
| **迷失症** | 工作区管理器 | 保存和恢复工作状态，随时继续 |
| **代码过时** | 废弃标记系统 | 标记过时实现，防止误用 |

## ✨ 核心亮点

### 1. 五档信任梯度（隐私控制）
```python
Level 1: 仅本地骨架（文件名、路径）
Level 2: 添加函数签名和类定义
Level 3: 包含注释和文档字符串
Level 4: 包含参数和返回值信息
Level 5: 完整代码内容
```

### 2. 多类型链路识别
- **数据流**：识别文件读写和数据传递
- **控制流**：识别函数调用链
- **时序流**：识别执行顺序和版本演进
- **配置依赖**：识别配置文件读取
- **继承关系**：识别类继承和接口实现

### 3. 智能布局引擎
根据项目特征自动选择最佳布局：
- 层级树布局：有明显入口文件
- 阶段分区布局：数据处理流水线
- 星型分组布局：核心模块居中
- 时间轴布局：版本演进项目

### 4. 领域专属技术标签
- **金融科技**: 风控、合规、策略、回测、VaR...
- **科研领域**: 实验、消融、数据集、基准...
- **软件开发**: API、数据库、缓存、消息队列...

## 🚀 快速开始

### 安装

```bash
pip install projmap-ai
```

### 命令行使用

```bash
# 初始化项目
projmap init ./my_project

# 扫描并生成脉络图
projmap scan ./my_project -o map.html

# 查看帮助
projmap --help
```

### Python API 使用

```python
import projmap

# 扫描项目
result = projmap.scan_project("./my_project")
print(f"发现 {len(result.files)} 个文件")

# 生成 .projmap 文件
projmap.generate_projmap(
    result,
    output="./my_project.projmap",
    project_name="My Project"
)

# 信任等级控制
from projmap import TrustLevelExtractor
extractor = TrustLevelExtractor(trust_level=3)
data = extractor.extract("src/main.py")

# 决策点管理
from projmap import DecisionManager, DecisionType
dm = DecisionManager()
dm.add_decision(
    node_id="node_001",
    decision_type=DecisionType.ARCHITECTURE,
    title="选择数据库",
    rationale="PostgreSQL 更适合事务处理"
)
```

## 📁 项目结构

```
projmap-ai/
├── src/projmap/           # 核心代码
│   ├── scanner.py         # 项目扫描器
│   ├── analyzer.py        # 依赖分析器
│   ├── generator.py       # 脉络生成器
│   ├── trust_level.py     # 信任等级系统
│   ├── decision_manager.py # 决策管理器
│   ├── state_machine.py   # 路径状态机
│   ├── link_analyzer.py   # 链路识别器
│   ├── layout_engine.py   # 布局引擎
│   ├── node_aggregator.py # 节点聚合器
│   ├── tech_tags.py       # 技术标签系统
│   └── cli.py             # 命令行接口
├── examples/              # 示例代码
├── tests/                 # 测试文件
├── schemas/               # JSON Schema
└── docs/                  # 文档
```

## 📦 核心模块

| 模块 | 功能 |
|:---|:---|
| `scanner` | 项目扫描器 |
| `analyzer` | 依赖分析器 |
| `generator` | 脉络生成器 |
| `trust_level` | 信任等级系统 |
| `decision_manager` | 决策管理器 |
| `state_machine` | 路径状态机 |
| `project_navigator` | 项目导航器 |
| `decision_tracer` | 决策追溯器 |
| `failure_retrieval` | 失败检索器 |
| `workspace_manager` | 工作区管理器 |
| `tech_tags` | 技术标签系统 |
| `link_analyzer` | 链路识别器 |
| `layout_engine` | 布局引擎 |
| `node_aggregator` | 节点聚合器 |
| `llm_service` | LLM 服务接口 |

## 🔧 配置方式

### 配置文件 (`~/.projmap/config.json`)

```json
{
    "default_trust_level": 3,
    "deepseek_api_key": "your-api-key",
    "exclude_patterns": ["*.pyc", "__pycache__", ".git"],
    "include_patterns": ["*.py", "*.js", "*.ts"]
}
```

### 环境变量

```bash
export DEEPSEEK_API_KEY="your-api-key"
export PROJMAP_TRUST_LEVEL=3
```

## 💡 适用场景

- **大型复杂项目** - 知识管理和脉络梳理
- **多人协作项目** - 决策记录和团队共享
- **AI 辅助开发** - 上下文管理和精准辅助
- **遗留项目** - 快速理解和重构
- **科研项目** - 过程追溯和实验管理
- **金融系统** - 合规审计和风险控制

## 🏗️ 技术架构

- **核心引擎**: Python 3.10+
- **依赖库**: click, pathspec, rich
- **可选依赖**: openai（用于 LLM 增强）
- **可视化**: HTML + JavaScript（内嵌 JSON 数据）

## 📄 许可证

MIT License

## 🔗 相关链接

- **PyPI**: https://pypi.org/project/projmap-ai/
- **问题反馈**: https://github.com/projmap/projmap/issues

---

**ProjMap - 让 AI 真正理解你的项目**
