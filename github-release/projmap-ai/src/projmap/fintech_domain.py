"""金融科技领域专用模块

针对金融科技/量化交易场景的专项优化。
核心特性：
- 合规审计追踪：所有决策和操作可追溯
- 版本时空管理：精确记录版本有效时间
- 策略回测记录：回测参数与结果关联
- 风险管理标记：风险等级与审批流程
"""

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Optional
from uuid import uuid4

from projmap.models import ProjMap, Node, Decision, DecisionType

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """风险等级"""
    LOW = "low"           # 低风险
    MEDIUM = "medium"     # 中风险
    HIGH = "high"         # 高风险
    CRITICAL = "critical" # 极高风险


class ApprovalStatus(Enum):
    """审批状态"""
    PENDING = "pending"       # 待审批
    APPROVED = "approved"     # 已批准
    REJECTED = "rejected"     # 已拒绝
    ESCALATED = "escalated"   # 已升级


@dataclass
class ComplianceRecord:
    """合规记录"""
    record_id: str
    record_type: str  # strategy_change, model_update, parameter_change
    entity_id: str    # 关联的节点或决策ID
    operator: str     # 操作人
    timestamp: datetime
    action: str       # 具体操作
    reason: str       # 操作原因
    risk_level: RiskLevel
    approval_status: ApprovalStatus
    approver: str = ""  # 审批人
    approval_time: Optional[datetime] = None
    checksum: str = ""  # 数据完整性校验


@dataclass
class StrategyVersion:
    """策略版本"""
    version_id: str
    strategy_name: str
    version_number: str  # 语义化版本，如 1.2.3
    effective_from: datetime  # 生效时间
    effective_to: Optional[datetime] = None  # 失效时间
    code_hash: str = ""  # 代码哈希
    parameters: dict = field(default_factory=dict)
    backtest_results: dict = field(default_factory=dict)
    live_performance: dict = field(default_factory=dict)
    regulatory_framework: str = ""  # 适用的监管框架


@dataclass
class BacktestRecord:
    """回测记录"""
    backtest_id: str
    strategy_version: str
    start_date: str
    end_date: str
    initial_capital: float
    final_capital: float
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    trade_count: int
    parameters: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


class ComplianceAuditor:
    """合规审计器"""
    
    def __init__(
        self,
        projmap: ProjMap,
        data_dir: str = ".projmap/compliance",
    ):
        self.projmap = projmap
        self.data_dir = data_dir
        self._records: list[ComplianceRecord] = []
        self._strategy_versions: dict[str, StrategyVersion] = {}
        
        os.makedirs(data_dir, exist_ok=True)
        self._load_data()
        self._logger = logging.getLogger("projmap.compliance")
    
    def _load_data(self):
        """加载合规数据"""
        records_file = os.path.join(self.data_dir, "compliance_records.json")
        if os.path.exists(records_file):
            try:
                with open(records_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._records = [
                    ComplianceRecord(
                        record_id=r["record_id"],
                        record_type=r["record_type"],
                        entity_id=r["entity_id"],
                        operator=r["operator"],
                        timestamp=datetime.fromisoformat(r["timestamp"]),
                        action=r["action"],
                        reason=r["reason"],
                        risk_level=RiskLevel(r["risk_level"]),
                        approval_status=ApprovalStatus(r["approval_status"]),
                        approver=r.get("approver", ""),
                        approval_time=datetime.fromisoformat(r["approval_time"]) if r.get("approval_time") else None,
                        checksum=r.get("checksum", ""),
                    )
                    for r in data.get("records", [])
                ]
            except Exception as e:
                self._logger.warning(f"加载合规记录失败: {e}")
    
    def _save_data(self):
        """保存合规数据"""
        records_file = os.path.join(self.data_dir, "compliance_records.json")
        try:
            with open(records_file, "w", encoding="utf-8") as f:
                json.dump({
                    "records": [
                        {
                            "record_id": r.record_id,
                            "record_type": r.record_type,
                            "entity_id": r.entity_id,
                            "operator": r.operator,
                            "timestamp": r.timestamp.isoformat(),
                            "action": r.action,
                            "reason": r.reason,
                            "risk_level": r.risk_level.value,
                            "approval_status": r.approval_status.value,
                            "approver": r.approver,
                            "approval_time": r.approval_time.isoformat() if r.approval_time else None,
                            "checksum": r.checksum,
                        }
                        for r in self._records
                    ],
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self._logger.error(f"保存合规记录失败: {e}")
    
    def _calculate_checksum(self, data: dict) -> str:
        """计算数据校验和"""
        content = json.dumps(data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def record_action(
        self,
        record_type: str,
        entity_id: str,
        operator: str,
        action: str,
        reason: str,
        risk_level: RiskLevel = RiskLevel.MEDIUM,
    ) -> ComplianceRecord:
        """记录操作"""
        record = ComplianceRecord(
            record_id=str(uuid4())[:16],
            record_type=record_type,
            entity_id=entity_id,
            operator=operator,
            timestamp=datetime.now(),
            action=action,
            reason=reason,
            risk_level=risk_level,
            approval_status=ApprovalStatus.PENDING if risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL) else ApprovalStatus.APPROVED,
        )
        
        # 计算校验和
        record.checksum = self._calculate_checksum({
            "record_id": record.record_id,
            "action": action,
            "timestamp": record.timestamp.isoformat(),
        })
        
        self._records.append(record)
        self._save_data()
        
        self._logger.info(f"记录合规操作: {record.record_id} - {action}")
        return record
    
    def approve_action(
        self,
        record_id: str,
        approver: str,
        approved: bool = True,
    ) -> bool:
        """审批操作"""
        for record in self._records:
            if record.record_id == record_id:
                record.approval_status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
                record.approver = approver
                record.approval_time = datetime.now()
                self._save_data()
                self._logger.info(f"审批操作: {record_id} - {'通过' if approved else '拒绝'}")
                return True
        return False
    
    def query_audit_trail(
        self,
        entity_id: Optional[str] = None,
        operator: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> list[ComplianceRecord]:
        """查询审计轨迹"""
        results = self._records
        
        if entity_id:
            results = [r for r in results if r.entity_id == entity_id]
        
        if operator:
            results = [r for r in results if r.operator == operator]
        
        if start_time:
            results = [r for r in results if r.timestamp >= start_time]
        
        if end_time:
            results = [r for r in results if r.timestamp <= end_time]
        
        return sorted(results, key=lambda r: r.timestamp)
    
    def verify_integrity(self) -> dict:
        """验证数据完整性"""
        violations = []
        
        for record in self._records:
            expected_checksum = self._calculate_checksum({
                "record_id": record.record_id,
                "action": record.action,
                "timestamp": record.timestamp.isoformat(),
            })
            if record.checksum != expected_checksum:
                violations.append({
                    "record_id": record.record_id,
                    "expected": expected_checksum,
                    "actual": record.checksum,
                })
        
        return {
            "total_records": len(self._records),
            "violations": violations,
            "is_valid": len(violations) == 0,
        }
    
    def generate_audit_report(self, start_time: Optional[datetime] = None, end_time: Optional[datetime] = None) -> dict:
        """生成审计报告"""
        records = self.query_audit_trail(start_time=start_time, end_time=end_time)
        
        report = {
            "report_period": {
                "start": start_time.isoformat() if start_time else "all",
                "end": end_time.isoformat() if end_time else "all",
            },
            "total_actions": len(records),
            "by_type": {},
            "by_risk_level": {},
            "by_operator": {},
            "pending_approvals": len([r for r in records if r.approval_status == ApprovalStatus.PENDING]),
            "integrity_check": self.verify_integrity(),
        }
        
        for record in records:
            # 按类型统计
            report["by_type"][record.record_type] = report["by_type"].get(record.record_type, 0) + 1
            
            # 按风险等级统计
            risk_key = record.risk_level.value
            report["by_risk_level"][risk_key] = report["by_risk_level"].get(risk_key, 0) + 1
            
            # 按操作人统计
            report["by_operator"][record.operator] = report["by_operator"].get(record.operator, 0) + 1
        
        return report


class StrategyVersionManager:
    """策略版本管理器"""
    
    def __init__(
        self,
        projmap: ProjMap,
        compliance_auditor: ComplianceAuditor,
        data_dir: str = ".projmap/strategies",
    ):
        self.projmap = projmap
        self.auditor = compliance_auditor
        self.data_dir = data_dir
        self._versions: dict[str, StrategyVersion] = {}
        
        os.makedirs(data_dir, exist_ok=True)
        self._load_data()
        self._logger = logging.getLogger("projmap.strategy")
    
    def _load_data(self):
        """加载策略版本数据"""
        versions_file = os.path.join(self.data_dir, "strategy_versions.json")
        if os.path.exists(versions_file):
            try:
                with open(versions_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._versions = {
                    k: StrategyVersion(
                        version_id=v["version_id"],
                        strategy_name=v["strategy_name"],
                        version_number=v["version_number"],
                        effective_from=datetime.fromisoformat(v["effective_from"]),
                        effective_to=datetime.fromisoformat(v["effective_to"]) if v.get("effective_to") else None,
                        code_hash=v.get("code_hash", ""),
                        parameters=v.get("parameters", {}),
                        backtest_results=v.get("backtest_results", {}),
                        live_performance=v.get("live_performance", {}),
                        regulatory_framework=v.get("regulatory_framework", ""),
                    )
                    for k, v in data.items()
                }
            except Exception as e:
                self._logger.warning(f"加载策略版本失败: {e}")
    
    def _save_data(self):
        """保存策略版本数据"""
        versions_file = os.path.join(self.data_dir, "strategy_versions.json")
        try:
            with open(versions_file, "w", encoding="utf-8") as f:
                json.dump({
                    k: {
                        "version_id": v.version_id,
                        "strategy_name": v.strategy_name,
                        "version_number": v.version_number,
                        "effective_from": v.effective_from.isoformat(),
                        "effective_to": v.effective_to.isoformat() if v.effective_to else None,
                        "code_hash": v.code_hash,
                        "parameters": v.parameters,
                        "backtest_results": v.backtest_results,
                        "live_performance": v.live_performance,
                        "regulatory_framework": v.regulatory_framework,
                    }
                    for k, v in self._versions.items()
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self._logger.error(f"保存策略版本失败: {e}")
    
    def create_version(
        self,
        strategy_name: str,
        version_number: str,
        code_files: list[str],
        parameters: dict,
        regulatory_framework: str = "",
        operator: str = "",
    ) -> StrategyVersion:
        """创建新版本"""
        # 计算代码哈希
        hasher = hashlib.sha256()
        for file_path in sorted(code_files):
            if os.path.exists(file_path):
                with open(file_path, "rb") as f:
                    hasher.update(f.read())
        code_hash = hasher.hexdigest()[:16]
        
        # 失效旧版本
        for v in self._versions.values():
            if v.strategy_name == strategy_name and v.effective_to is None:
                v.effective_to = datetime.now()
        
        version = StrategyVersion(
            version_id=str(uuid4())[:12],
            strategy_name=strategy_name,
            version_number=version_number,
            effective_from=datetime.now(),
            code_hash=code_hash,
            parameters=parameters,
            regulatory_framework=regulatory_framework,
        )
        
        self._versions[version.version_id] = version
        self._save_data()
        
        # 记录合规操作
        self.auditor.record_action(
            record_type="strategy_version_create",
            entity_id=version.version_id,
            operator=operator,
            action=f"创建策略版本 {strategy_name}@{version_number}",
            reason=f"代码哈希: {code_hash}",
            risk_level=RiskLevel.HIGH,
        )
        
        self._logger.info(f"创建策略版本: {strategy_name}@{version_number}")
        return version
    
    def get_version_at_time(self, strategy_name: str, timestamp: datetime) -> Optional[StrategyVersion]:
        """获取特定时间点的策略版本"""
        candidates = [
            v for v in self._versions.values()
            if v.strategy_name == strategy_name
            and v.effective_from <= timestamp
            and (v.effective_to is None or v.effective_to >= timestamp)
        ]
        
        if not candidates:
            return None
        
        # 返回最新版本
        return max(candidates, key=lambda v: v.effective_from)
    
    def record_backtest(
        self,
        version_id: str,
        backtest_record: BacktestRecord,
    ) -> bool:
        """记录回测结果"""
        if version_id not in self._versions:
            return False
        
        version = self._versions[version_id]
        version.backtest_results[backtest_record.backtest_id] = {
            "start_date": backtest_record.start_date,
            "end_date": backtest_record.end_date,
            "total_return": backtest_record.total_return,
            "sharpe_ratio": backtest_record.sharpe_ratio,
            "max_drawdown": backtest_record.max_drawdown,
            "win_rate": backtest_record.win_rate,
            "trade_count": backtest_record.trade_count,
            "timestamp": backtest_record.timestamp.isoformat(),
        }
        
        self._save_data()
        return True
    
    def compare_versions(self, version_id1: str, version_id2: str) -> dict:
        """对比两个版本"""
        v1 = self._versions.get(version_id1)
        v2 = self._versions.get(version_id2)
        
        if not v1 or not v2:
            return {"error": "版本不存在"}
        
        comparison = {
            "version1": {
                "id": v1.version_id,
                "number": v1.version_number,
                "effective_from": v1.effective_from.isoformat(),
            },
            "version2": {
                "id": v2.version_id,
                "number": v2.version_number,
                "effective_from": v2.effective_from.isoformat(),
            },
            "parameter_diff": {},
            "backtest_comparison": {},
        }
        
        # 参数差异
        all_params = set(v1.parameters.keys()) | set(v2.parameters.keys())
        for param in all_params:
            p1 = v1.parameters.get(param)
            p2 = v2.parameters.get(param)
            if p1 != p2:
                comparison["parameter_diff"][param] = {"old": p1, "new": p2}
        
        # 回测对比
        if v1.backtest_results and v2.backtest_results:
            latest1 = list(v1.backtest_results.values())[-1]
            latest2 = list(v2.backtest_results.values())[-1]
            
            comparison["backtest_comparison"] = {
                "total_return": {
                    "v1": latest1.get("total_return"),
                    "v2": latest2.get("total_return"),
                    "diff": latest2.get("total_return", 0) - latest1.get("total_return", 0),
                },
                "sharpe_ratio": {
                    "v1": latest1.get("sharpe_ratio"),
                    "v2": latest2.get("sharpe_ratio"),
                },
                "max_drawdown": {
                    "v1": latest1.get("max_drawdown"),
                    "v2": latest2.get("max_drawdown"),
                },
            }
        
        return comparison


class RiskManager:
    """风险管理器"""
    
    def __init__(self, compliance_auditor: ComplianceAuditor):
        self.auditor = compliance_auditor
        self._risk_rules: list[dict] = []
    
    def add_risk_rule(
        self,
        rule_name: str,
        condition: dict,
        risk_level: RiskLevel,
        required_approvers: int = 1,
    ):
        """添加风险规则"""
        self._risk_rules.append({
            "name": rule_name,
            "condition": condition,
            "risk_level": risk_level,
            "required_approvers": required_approvers,
        })
    
    def assess_risk(
        self,
        action_type: str,
        parameters: dict,
        operator: str,
    ) -> RiskLevel:
        """评估风险等级"""
        # 默认风险等级
        risk_level = RiskLevel.LOW
        
        # 检查规则
        for rule in self._risk_rules:
            if self._matches_condition(parameters, rule["condition"]):
                if rule["risk_level"].value == "critical":
                    return RiskLevel.CRITICAL
                elif rule["risk_level"].value == "high" and risk_level.value != "critical":
                    risk_level = RiskLevel.HIGH
                elif rule["risk_level"].value == "medium" and risk_level.value in ("low",):
                    risk_level = RiskLevel.MEDIUM
        
        # 特定高风险操作
        high_risk_actions = ["strategy_deploy", "parameter_live_update", "model_rollback"]
        if action_type in high_risk_actions:
            risk_level = RiskLevel.HIGH
        
        return risk_level
    
    def _matches_condition(self, parameters: dict, condition: dict) -> bool:
        """检查参数是否匹配条件"""
        for key, value in condition.items():
            if key not in parameters:
                return False
            if isinstance(value, dict):
                # 范围检查
                if "min" in value and parameters[key] < value["min"]:
                    return False
                if "max" in value and parameters[key] > value["max"]:
                    return False
            elif parameters[key] != value:
                return False
        return True
