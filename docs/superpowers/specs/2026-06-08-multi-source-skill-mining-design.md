# 多源「该做成 skill」信号挖掘 — 设计文档

- 日期：2026-06-08
- 分支：`feat/multi-source-skill-mining`
- 状态：已批准，待实现

## 背景与动机

时间审计当前只从 Screenpipe 屏幕 OCR 一个来源做分析。对重度终端 / Agent 用户，这条路有两个结构性问题：

1. **盲点**：用户真正反复做的事（敲命令、反复委托 agent）发生在终端 / agent 会话里，OCR 抓到的只是 `终端 / unknown` 噪声，挖不出可固化的工作流。实测某用户 7 天数据中 `unknown(45%) + 终端(37%) = 82%` 对 OCR 无效。
2. **证据失真**：OCR 层的洞察靠 LLM 生成，`evidence_sessions` 无任何校验。实测一份真实报告引用了 13 个 session，其中 10 个不存在（纯幻觉），整个「线」层证据是编的。

**目标**：让时间审计能从用户日常使用中**任意可优化的流程化来源**挖出"该做成 skill"的信号，且证据真实可信。数据源必须是**可插拔、可扩展**的框架，而非写死某一两个。

核心判断：**命令层的重复最直接说明"该做成脚本 / skill / 可快速触发的自动化流程"**。命令 / 意图层不交给 LLM 猜（那正是幻觉根源），而是**确定性统计真实重复**——证据是真命令行 + 真次数。

## 范围

### 本版交付
- 可插拔适配器框架（`time_audit/sources/`）。
- 四个具体适配器：Screenpipe OCR（保留现状）、Shell 历史、Claude Code 转录、OpenClaw 日志（best-effort）。
- 确定性命令挖掘器（`command_miner.py`）：重复命令 → 点候选，重复命令序列 → 线候选。
- 报告增加 `modality` 标签；OCR 层洞察落盘前做证据校验，丢弃引用不存在 session 的条目。

### 不做（YAGNI）
- 不改 MCP server 三个工具的签名（`report_query` 自动受益）。
- 不做实时，仍批跑。
- 不死磕 OpenClaw 深度逆向，认得多少算多少，不认就跳过且不报错。

## 架构

现有管线有干净接缝：`db_reader.load_events(cfg) → events[] → compress → analyze → report`，`events` schema 为
`{timestamp, app, window, event_type, content, file_path, source, ts, gap_seconds}`。
新设计在 `load_events` 处插入适配器层，下游全部复用。

### 1. 适配器层 `time_audit/sources/`

统一接口（每个源一个文件，互相隔离、可独立测试）：

```python
class SourceAdapter:
    name: str
    def available(self, cfg: dict) -> bool: ...        # 此机器上是否存在该源
    def collect(self, cfg: dict, days: int) -> list[dict]: ...   # 归一化事件
```

| 适配器 | 来源 | app | content | 时间戳 | 备注 |
|---|---|---|---|---|---|
| `screenpipe.py` | 现有 OCR | 真实应用 | OCR 文本 | 真实 | 包装现有 `read_screenpipe_events`，行为不变 |
| `shell_history.py` | `~/.zsh_history` / `~/.bash_history` | `shell` | 命令原文 | **无 → 按序号合成单调递增 ts** | 处理 `\` 续行、`#` 注释、zsh 扩展格式 `: <ts>:<dur>;` |
| `claude_code.py` | `~/.claude/projects/**/*.jsonl` | `claude-code` | 用户意图消息 | 真实（行内 timestamp） | 只取 user 文本消息，跳过 `queue-operation` 等运维噪声 |
| `openclaw.py` | `~/.openclaw` 下 logs / flows / cron | `openclaw` | 会话 / 任务描述 | 尽力 | best-effort，格式不认则返回空、不抛错 |

`load_events`：遍历注册表，对 `available()` 为真的适配器调 `collect()`，合并所有事件、按 `ts` 排序、重算 `gap_seconds`。

**控制开关**：
- CLI：`--sources screenpipe,shell,claude,openclaw`（缺省读 config）。
- config：`sources.enabled: [...]`，缺省 `[screenpipe, shell, claude, openclaw]`。
- 任一源缺失 / 解析失败：打印一行 warning，跳过该源，绝不让整条管线挂掉。

### 2. 确定性命令挖掘 `time_audit/core/command_miner.py`

只消费 `shell` / `claude-code` / `openclaw` 这类命令 / 意图事件（按 `app` 或 `source` 过滤）：

- **归一化**：剥掉路径、引号内容、明显可变参数，保留命令骨架。
  例：`git commit -m "fix bug"` → `git commit -m`；`gh api repos/x/y/traffic/views` → `gh api repos/_/_/traffic/views`。
  归一化激进程度由 config 控制，默认中等。
- **点候选**：单条归一化命令出现次数 ≥ `min_command_count`（默认 5）→ 建议 alias / snippet。
  证据 = 真实出现次数 + 最多 3 条样例原文。
- **线候选**：连续命令的 n-gram（窗口 2~5）重复次数 ≥ `min_sequence_count`（默认 3）→ 建议脚本 / skill。
  证据 = 真实命令序列 + 出现次数。Shell 无时间戳，序列按**出现顺序**判定连续，不依赖时间间隔。
- 完全确定性、零幻觉。LLM 仅**可选**地为候选起中文名 + 一句话建议（名字错了无所谓，证据是算出来的）。

### 3. 输出：统一进点 / 线 / 面，带 `modality` 标签

- 每条洞察新增字段 `modality ∈ {ocr, command, agent-intent}`，报告按模态可见来源。
- 命令 / 意图层洞察携带**真实证据**（次数 + 原文 / 序列）。
- OCR 层洞察落盘前过滤：`evidence_sessions` 中引用了当前 sessions 不存在的 id 的条目被丢弃或标红（在 `report_builder` 或合并阶段做一道 `validate_evidence`）。
- AOS schema 增加可选 `modality` 字段，向后兼容。
- 命令挖掘结果与 LLM 结果在 `analyze` 之后合并进 `{points, lines, surfaces}`，再交给 `build_report`。

## 数据流

```
sources registry
  ├─ screenpipe.collect ─┐
  ├─ shell.collect ──────┤
  ├─ claude_code.collect ┤→ merge + sort + gap → events[]
  └─ openclaw.collect ───┘
                                  │
        ┌─────────────────────────┴───────────────────────────┐
        │                                                       │
  event_compressor.compress (OCR 时间会话)            command_miner (命令/意图事件)
        │                                                       │
  llm_analyzer.analyze → {points,lines,surfaces}(ocr)    确定性候选 {points,lines}(command)
        │                                                       │
        └────────────── merge + validate_evidence ─────────────┘
                                  │
                          report_builder (带 modality)
```

## 错误处理

- 每个适配器 `collect` 内部捕获异常，失败返回 `[]` 并 warning，不影响其他源。
- `available()` 检查文件 / 目录存在性，不存在直接返回 False。
- 命令挖掘对空输入返回空候选。
- 证据校验对缺失字段宽容（无 `evidence_sessions` 视为命令层，不校验 session）。

## 测试策略

每个单元用**真实样本**做单测（用户机器上数据齐全，不靠 mock 自欺）：
- `shell_history`：构造含续行 / 注释 / 扩展格式的 fixture，验证归一化与事件产出。
- `claude_code`：用真实 jsonl 片段，验证只取 user 消息、跳过噪声、时间戳解析。
- `openclaw`：验证格式不认时优雅返回空。
- `command_miner`：构造重复命令 / 序列，验证点 / 线候选计数与证据真实。
- `validate_evidence`：验证引用不存在 session 的洞察被过滤。
- 适配器注册 / 合并 / 开关：验证启用子集、缺失源降级。

## 兼容性

- 不改现有 `events` schema，旧 Screenpipe 路径行为不变（仅被 `screenpipe.py` 包装）。
- 不改 MCP 工具签名。
- 缺省启用全部源；用户可通过 config / CLI 收窄。
