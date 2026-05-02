"""科研领域专用模块

针对科研/机器学习实验场景的专项优化。
核心特性：
- 实验追踪：超参数、指标、数据集版本关联
- 可复现性保障：环境依赖、随机种子记录
- 论文-代码映射：论文章节与代码文件关联
- 消融实验管理：实验变体对比分析
"""

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from projmap.models import ProjMap, Node, Decision, DecisionType

logger = logging.getLogger(__name__)


@dataclass
class ExperimentConfig:
    """实验配置"""
    experiment_id: str
    name: str
    description: str = ""
    hyperparameters: dict = field(default_factory=dict)
    dataset_version: str = ""
    random_seed: int = 42
    environment: dict = field(default_factory=dict)  # Python版本、库版本等
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class ExperimentResult:
    """实验结果"""
    result_id: str
    experiment_id: str
    metrics: dict = field(default_factory=dict)  # 准确率、F1、损失等
    training_time: float = 0.0
    model_size: int = 0
    checkpoint_path: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    notes: str = ""


@dataclass
class PaperMapping:
    """论文-代码映射"""
    paper_title: str
    paper_url: str = ""
    arxiv_id: str = ""
    section_mappings: dict = field(default_factory=dict)  # 章节 -> 代码文件
    algorithm_implementations: dict = field(default_factory=dict)  # 算法 -> 实现位置


class ResearchExperimentManager:
    """科研实验管理器"""
    
    def __init__(
        self,
        projmap: ProjMap,
        data_dir: str = ".projmap/research",
    ):
        self.projmap = projmap
        self.data_dir = data_dir
        self._experiments: dict[str, ExperimentConfig] = {}
        self._results: dict[str, ExperimentResult] = {}
        self._paper_mappings: dict[str, PaperMapping] = {}
        
        os.makedirs(data_dir, exist_ok=True)
        self._load_data()
        self._logger = logging.getLogger("projmap.research")
    
    def _load_data(self):
        """加载实验数据"""
        experiments_file = os.path.join(self.data_dir, "experiments.json")
        if os.path.exists(experiments_file):
            try:
                with open(experiments_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._experiments = {
                    k: ExperimentConfig(**v) for k, v in data.items()
                }
            except Exception as e:
                self._logger.warning(f"加载实验数据失败: {e}")
    
    def _save_data(self):
        """保存实验数据"""
        experiments_file = os.path.join(self.data_dir, "experiments.json")
        try:
            with open(experiments_file, "w", encoding="utf-8") as f:
                json.dump(
                    {k: v.__dict__ for k, v in self._experiments.items()},
                    f, ensure_ascii=False, indent=2, default=str
                )
        except Exception as e:
            self._logger.error(f"保存实验数据失败: {e}")
    
    def create_experiment(
        self,
        name: str,
        description: str = "",
        hyperparameters: Optional[dict] = None,
        dataset_version: str = "",
        random_seed: int = 42,
    ) -> ExperimentConfig:
        """创建新实验"""
        # 捕获环境信息
        import sys
        environment = {
            "python_version": sys.version,
            "platform": sys.platform,
        }
        
        # 尝试获取依赖版本
        try:
            import pkg_resources
            installed = {d.key: d.version for d in pkg_resources.working_set}
            environment["dependencies"] = {
                k: v for k, v in installed.items()
                if k in ["torch", "tensorflow", "numpy", "pandas", "scikit-learn"]
            }
        except Exception:
            pass
        
        experiment = ExperimentConfig(
            experiment_id=str(uuid4())[:12],
            name=name,
            description=description,
            hyperparameters=hyperparameters or {},
            dataset_version=dataset_version,
            random_seed=random_seed,
            environment=environment,
        )
        
        self._experiments[experiment.experiment_id] = experiment
        self._save_data()
        
        # 添加决策记录
        from projmap.decision_manager import DecisionManager
        manager = DecisionManager(self.projmap)
        manager.add_decision(
            node_id="research_root",
            decision_type="milestone",
            content=f"创建实验: {name}",
            reason=f"数据集版本: {dataset_version}, 随机种子: {random_seed}",
            parameters=hyperparameters,
        )
        
        self._logger.info(f"创建实验: {name} ({experiment.experiment_id})")
        return experiment
    
    def record_result(
        self,
        experiment_id: str,
        metrics: dict,
        training_time: float = 0.0,
        checkpoint_path: str = "",
        notes: str = "",
    ) -> ExperimentResult:
        """记录实验结果"""
        if experiment_id not in self._experiments:
            raise ValueError(f"实验不存在: {experiment_id}")
        
        result = ExperimentResult(
            result_id=str(uuid4())[:12],
            experiment_id=experiment_id,
            metrics=metrics,
            training_time=training_time,
            checkpoint_path=checkpoint_path,
            notes=notes,
        )
        
        self._results[result.result_id] = result
        
        # 保存到文件
        results_file = os.path.join(self.data_dir, f"results_{experiment_id}.json")
        try:
            existing = []
            if os.path.exists(results_file):
                with open(results_file, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            existing.append(result.__dict__)
            with open(results_file, "w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            self._logger.error(f"保存结果失败: {e}")
        
        self._logger.info(f"记录结果: {result.result_id}")
        return result
    
    def compare_experiments(self, experiment_ids: list[str]) -> dict:
        """对比多个实验"""
        comparison = {
            "experiments": [],
            "metrics_comparison": {},
            "best_by_metric": {},
        }
        
        for exp_id in experiment_ids:
            if exp_id not in self._experiments:
                continue
            
            exp = self._experiments[exp_id]
            results = [r for r in self._results.values() if r.experiment_id == exp_id]
            
            exp_data = {
                "id": exp_id,
                "name": exp.name,
                "hyperparameters": exp.hyperparameters,
                "results_count": len(results),
            }
            comparison["experiments"].append(exp_data)
            
            # 对比指标
            for result in results:
                for metric_name, value in result.metrics.items():
                    if metric_name not in comparison["metrics_comparison"]:
                        comparison["metrics_comparison"][metric_name] = []
                    comparison["metrics_comparison"][metric_name].append({
                        "experiment": exp.name,
                        "value": value,
                        "timestamp": result.timestamp.isoformat(),
                    })
        
        # 找出每个指标的最佳实验
        for metric_name, values in comparison["metrics_comparison"].items():
            if values:
                best = max(values, key=lambda x: x["value"])
                comparison["best_by_metric"][metric_name] = best
        
        return comparison
    
    def map_paper_to_code(
        self,
        paper_title: str,
        paper_url: str = "",
        arxiv_id: str = "",
    ) -> PaperMapping:
        """创建论文-代码映射"""
        mapping = PaperMapping(
            paper_title=paper_title,
            paper_url=paper_url,
            arxiv_id=arxiv_id,
        )
        
        self._paper_mappings[paper_title] = mapping
        
        # 保存
        papers_file = os.path.join(self.data_dir, "paper_mappings.json")
        try:
            with open(papers_file, "w", encoding="utf-8") as f:
                json.dump(
                    {k: v.__dict__ for k, v in self._paper_mappings.items()},
                    f, ensure_ascii=False, indent=2
                )
        except Exception as e:
            self._logger.error(f"保存论文映射失败: {e}")
        
        return mapping
    
    def link_paper_section(
        self,
        paper_title: str,
        section: str,
        code_file: str,
        line_range: Optional[tuple[int, int]] = None,
    ):
        """关联论文章节与代码"""
        if paper_title not in self._paper_mappings:
            raise ValueError(f"论文未注册: {paper_title}")
        
        mapping = self._paper_mappings[paper_title]
        mapping.section_mappings[section] = {
            "file": code_file,
            "lines": line_range,
        }
        
        # 更新节点描述
        for node in self.projmap.nodes:
            if node.file_path == code_file:
                if not node.description:
                    node.description = f"实现论文《{paper_title}》的 {section}"
                if paper_title not in (node.tags or []):
                    node.tags = node.tags or []
                    node.tags.append(f"paper:{paper_title}")
        
        self._save_data()
    
    def generate_reproducibility_report(self) -> dict:
        """生成可复现性报告"""
        report = {
            "total_experiments": len(self._experiments),
            "total_results": len(self._results),
            "environment_consistency": True,
            "missing_dependencies": [],
            "recommendations": [],
        }
        
        # 检查环境一致性
        if self._experiments:
            first_env = list(self._experiments.values())[0].environment
            for exp in self._experiments.values():
                if exp.environment.get("python_version") != first_env.get("python_version"):
                    report["environment_consistency"] = False
                    break
        
        # 生成建议
        if not report["environment_consistency"]:
            report["recommendations"].append("检测到不同Python版本，建议使用虚拟环境或Docker")
        
        if len(self._experiments) > 0 and len(self._results) == 0:
            report["recommendations"].append("有实验配置但无结果记录，请确保调用record_result()")
        
        return report
    
    def export_to_mlflow_format(self, output_dir: str) -> bool:
        """导出为MLflow兼容格式"""
        try:
            os.makedirs(output_dir, exist_ok=True)
            
            for exp_id, exp in self._experiments.items():
                exp_dir = os.path.join(output_dir, exp_id)
                os.makedirs(exp_dir, exist_ok=True)
                
                # 保存实验配置
                with open(os.path.join(exp_dir, "params.json"), "w") as f:
                    json.dump(exp.hyperparameters, f, indent=2)
                
                # 保存指标
                results = [r for r in self._results.values() if r.experiment_id == exp_id]
                if results:
                    metrics = {}
                    for r in results:
                        for k, v in r.metrics.items():
                            if k not in metrics:
                                metrics[k] = []
                            metrics[k].append(v)
                    with open(os.path.join(exp_dir, "metrics.json"), "w") as f:
                        json.dump(metrics, f, indent=2)
            
            return True
        except Exception as e:
            self._logger.error(f"导出失败: {e}")
            return False


class AblationStudyManager:
    """消融实验管理器"""
    
    def __init__(self, research_manager: ResearchExperimentManager):
        self.rm = research_manager
        self._ablations: dict[str, dict] = {}
    
    def create_ablation_study(
        self,
        base_experiment_id: str,
        component_name: str,
        variations: list[dict],
    ) -> str:
        """创建消融实验研究
        
        Args:
            base_experiment_id: 基础实验ID
            component_name: 要消融的组件名称
            variations: 变体列表，每个变体是一个参数覆盖字典
        """
        study_id = str(uuid4())[:12]
        
        base_exp = self.rm._experiments.get(base_experiment_id)
        if not base_exp:
            raise ValueError(f"基础实验不存在: {base_experiment_id}")
        
        self._ablations[study_id] = {
            "base_experiment": base_experiment_id,
            "component": component_name,
            "variations": [],
            "created_at": datetime.now().isoformat(),
        }
        
        # 为每个变体创建实验
        for i, variation in enumerate(variations):
            # 合并基础参数和变体参数
            merged_params = {**base_exp.hyperparameters, **variation}
            
            exp = self.rm.create_experiment(
                name=f"{base_exp.name}_ablation_{component_name}_{i}",
                description=f"消融实验: {component_name} 变体 {i}",
                hyperparameters=merged_params,
                dataset_version=base_exp.dataset_version,
                random_seed=base_exp.random_seed,
            )
            
            self._ablations[study_id]["variations"].append({
                "experiment_id": exp.experiment_id,
                "parameters": variation,
            })
        
        return study_id
    
    def analyze_ablation(self, study_id: str) -> dict:
        """分析消融实验结果"""
        if study_id not in self._ablations:
            raise ValueError(f"消融研究不存在: {study_id}")
        
        study = self._ablations[study_id]
        base_exp_id = study["base_experiment"]
        
        # 收集所有相关实验的结果
        all_results = []
        
        # 基础实验结果
        base_results = [r for r in self.rm._results.values() if r.experiment_id == base_exp_id]
        if base_results:
            all_results.append({
                "type": "base",
                "experiment_id": base_exp_id,
                "metrics": base_results[-1].metrics,  # 取最新结果
            })
        
        # 各变体结果
        for var in study["variations"]:
            var_results = [r for r in self.rm._results.values() if r.experiment_id == var["experiment_id"]]
            if var_results:
                all_results.append({
                    "type": "ablation",
                    "experiment_id": var["experiment_id"],
                    "parameters": var["parameters"],
                    "metrics": var_results[-1].metrics,
                })
        
        # 计算各组件贡献
        analysis = {
            "study_id": study_id,
            "component": study["component"],
            "total_variations": len(study["variations"]),
            "completed_variations": len([r for r in all_results if r["type"] == "ablation"]),
            "results": all_results,
        }
        
        return analysis
