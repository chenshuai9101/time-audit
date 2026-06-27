"""
FDE 执行引擎

编排五阶段流水线，管理状态持久化，提供完整的 CLI 和 API 入口。
"""
import os
import json
import uuid
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict

from time_audit.fde import phases
from time_audit.fde.deliverable import (
    build_discovery_doc,
    build_assessment_doc,
    build_architecture_doc,
    build_prototype_doc,
    build_handoff_package,
)


# ── 常量 ─────────────────────────────────────────────────────────────
FDE_OUTPUT_BASE = os.path.expanduser("~/Desktop/fde-engagements/")


# ── 数据类型 ──────────────────────────────────────────────────────────
@dataclass
class FDEConfig:
    """FDE 项目配置"""
    engagement_id: str = ""
    client_name: str = ""
    client_industry: str = ""
    project_name: str = ""

    # 时间审计集成
    time_audit_enabled: bool = True
    time_audit_report_id: Optional[str] = None

    # LLM 配置
    llm_provider: str = "ollama"
    llm_model: str = "qwen2.5:14b"
    llm_endpoint: str = "http://localhost:11434"

    # 输出
    output_dir: str = ""

    def __post_init__(self):
        if not self.engagement_id:
            self.engagement_id = datetime.now().strftime("eng-%Y%m%d-%H%M%S")
        if not self.output_dir:
            self.output_dir = os.path.join(FDE_OUTPUT_BASE, self.engagement_id)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FDEPhase:
    """单个阶段的执行状态"""
    phase: int              # 1-5
    name: str
    status: str = "pending"  # pending / running / completed / failed
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    deliverable_path: Optional[str] = None
    error: Optional[str] = None


@dataclass
class FDEState:
    """FDE 项目完整状态"""
    config: FDEConfig
    phases: List[FDEPhase] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        self.updated_at = datetime.now().isoformat()
        if not self.phases:
            self.phases = [
                FDEPhase(phase=1, name="现场发现", status="pending"),
                FDEPhase(phase=2, name="差距评估", status="pending"),
                FDEPhase(phase=3, name="架构设计", status="pending"),
                FDEPhase(phase=4, name="原型构建", status="pending"),
                FDEPhase(phase=5, name="交付交接", status="pending"),
            ]

    def to_dict(self) -> dict:
        return {
            "config": self.config.to_dict(),
            "phases": [asdict(p) for p in self.phases],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def save(self, path: str = None) -> str:
        """持久化状态到 JSON"""
        path = path or os.path.join(self.config.output_dir, "fde_state.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        return path

    @classmethod
    def load(cls, path: str) -> "FDEState":
        """从 JSON 恢复状态"""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        config = FDEConfig(**data["config"])
        state = cls(config=config)
        state.phases = [FDEPhase(**p) for p in data["phases"]]
        state.created_at = data["created_at"]
        state.updated_at = data["updated_at"]
        return state


# ── 引擎 ──────────────────────────────────────────────────────────────
class FDEEngine:
    """FDE 执行引擎 — 编排五阶段流水线"""

    def __init__(self, config: FDEConfig):
        self.config = config
        self.state = FDEState(config=config)

    # ── 状态管理 ───────────────────────────────────────────────────
    def get_phase(self, phase: int) -> FDEPhase:
        if phase < 1 or phase > 5:
            raise ValueError(f"阶段号必须为 1-5，收到: {phase}")
        return self.state.phases[phase - 1]

    def _set_phase_running(self, phase: int):
        p = self.get_phase(phase)
        p.status = "running"
        p.started_at = datetime.now().isoformat()
        self.state.updated_at = datetime.now().isoformat()
        self._save_state()

    def _set_phase_completed(self, phase: int, deliverable_path: str = ""):
        p = self.get_phase(phase)
        p.status = "completed"
        p.completed_at = datetime.now().isoformat()
        if deliverable_path:
            p.deliverable_path = deliverable_path
        self.state.updated_at = datetime.now().isoformat()
        self._save_state()

    def _set_phase_failed(self, phase: int, error: str):
        p = self.get_phase(phase)
        p.status = "failed"
        p.error = error
        self.state.updated_at = datetime.now().isoformat()
        self._save_state()

    def _save_state(self):
        self.config = self.state.config
        os.makedirs(self.config.output_dir, exist_ok=True)
        self.state.save()

    def save_state(self):
        """公开保存接口"""
        self._save_state()

    # ── 公开 API ──────────────────────────────────────────────────
    def get_status_text(self) -> str:
        """返回人类可读的状态概览"""
        lines = [
            f"📋 FDE 项目: {self.config.project_name or self.config.engagement_id}",
            f"   客户: {self.config.client_name} ({self.config.client_industry})",
            f"   输出目录: {self.config.output_dir}",
            "",
            "阶段状态:",
        ]
        for p in self.state.phases:
            icon = {"pending": "⏳", "running": "🔄", "completed": "✅", "failed": "❌"}
            line = f"  {icon.get(p.status, '❓')} Phase {p.phase}: {p.name} — {p.status}"
            if p.deliverable_path:
                line += f"\n     📄 {p.deliverable_path}"
            if p.error:
                line += f"\n     ⚠️  {p.error}"
            lines.append(line)
        return "\n".join(lines)

    def run_phase(self, phase: int, context: dict = None) -> dict:
        """执行指定阶段。

        Args:
            phase: 1-5
            context: 阶段上下文（含用户输入、上阶段产出等）

        Returns:
            阶段输出数据
        """
        context = context or {}
        phase_funcs = {
            1: self._run_discovery,
            2: self._run_assessment,
            3: self._run_architecture,
            4: self._run_prototype,
            5: self._run_handoff,
        }

        func = phase_funcs.get(phase)
        if not func:
            raise ValueError(f"无效阶段: {phase}，仅支持 1-5")

        self._set_phase_running(phase)
        try:
            result = func(context)
            self._set_phase_completed(phase, result.get("deliverable_path", ""))
            return result
        except Exception as e:
            self._set_phase_failed(phase, str(e))
            raise

    def run_all(self, context: dict = None) -> dict:
        """顺序执行全部五阶段"""
        context = context or {}
        results = {}
        for i in range(1, 6):
            results[f"phase_{i}"] = self.run_phase(i, context.get(f"phase_{i}", {}))
        return results

    # ── 阶段实现 ───────────────────────────────────────────────────
    def _run_discovery(self, ctx: dict) -> dict:
        """Phase 1: 现场发现"""
        client_input = ctx.get("client_input", "")
        pain_points = phases.run_discovery(client_input, self.config)

        doc_path = build_discovery_doc(
            self.config, pain_points, ctx
        )
        return {"pain_points": pain_points, "deliverable_path": doc_path}

    def _run_assessment(self, ctx: dict) -> dict:
        """Phase 2: 差距评估"""
        pain_points = ctx.get("pain_points", [])
        opportunities = phases.run_assessment(
            pain_points,
            self.config,
            ctx.get("time_audit_opportunities"),
        )

        doc_path = build_assessment_doc(
            self.config, opportunities, ctx
        )
        return {"opportunities": opportunities, "deliverable_path": doc_path}

    def _run_architecture(self, ctx: dict) -> dict:
        """Phase 3: 架构设计"""
        opportunities = ctx.get("opportunities", [])
        architecture = phases.run_architecture(opportunities, self.config)

        doc_path = build_architecture_doc(
            self.config, architecture, ctx
        )
        return {"architecture": architecture, "deliverable_path": doc_path}

    def _run_prototype(self, ctx: dict) -> dict:
        """Phase 4: 原型构建"""
        architecture = ctx.get("architecture", {})
        prototype = phases.run_prototype(architecture, self.config)

        doc_path = build_prototype_doc(
            self.config, prototype, ctx
        )
        return {"prototype": prototype, "deliverable_path": doc_path}

    def _run_handoff(self, ctx: dict) -> dict:
        """Phase 5: 交付交接"""
        package = phases.run_handoff(self.state, self.config)

        doc_path = build_handoff_package(
            self.config, self.state, package
        )
        return {"handoff": package, "deliverable_path": doc_path}


# ── 快捷入口 ──────────────────────────────────────────────────────────
def create_engagement(
    client_name: str = "",
    client_industry: str = "",
    project_name: str = "",
    **kwargs,
) -> FDEEngine:
    """快速创建 FDE 项目引擎，自动持久化状态"""
    config = FDEConfig(
        client_name=client_name,
        client_industry=client_industry,
        project_name=project_name,
        **kwargs,
    )
    eng = FDEEngine(config)
    eng._save_state()  # 创建时即持久化
    return eng


def load_engagement(path: str) -> FDEEngine:
    """从状态文件恢复 FDE 项目"""
    state = FDEState.load(path)
    engine = FDEEngine(state.config)
    engine.state = state
    return engine
