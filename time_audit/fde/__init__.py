"""
FDE Agent Skill — 前线部署工程执行引擎（时间审计集成版）

提供完整的 FDE 五阶段自动执行能力：
  Phase 1: Field Discovery (现场发现)
  Phase 2: Gap Assessment (差距评估)
  Phase 3: Solution Architecture (架构设计)
  Phase 4: Rapid Prototype (原型构建)
  Phase 5: Handoff (交付交接)

每个阶段输出结构化 Markdown 交付物，最终打包为交付证据包。
"""

__version__ = "1.0.0"
__all__ = [
    "engine",
    "phases",
    "deliverable",
    "mcp_tools",
]

from time_audit.fde import engine, phases, deliverable, mcp_tools
