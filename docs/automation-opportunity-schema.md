# Automation Opportunity Schema (AOS)

> 一份可移植的契约，描述"一条值得自动化的工作机会"长什么样。
> **版本：0.1.0** · 状态：**Draft（草案，结构仍可能破坏性变更）** · License：MIT（随项目）

## 这是什么 / 为什么存在

把"人的真实工作里，哪些事值得让 AI/脚本替他做"这件事，标准化成一个**机器可读的对象**。

```text
   发现层                          AOS                       执行层
（谁产出 opportunity）   ── 这份 schema ──>   （谁消费 opportunity）
时间审计 / 任何行为分析工具              Agent / RPA / Fara / MCP 客户端 / skill 生成器
```

- **发现层**：从屏幕行为、日志、访谈等任何来源，发现可自动化的工作模式。
- **执行层**：Agent / 自动化执行器读取 opportunity，决定创建哪个 skill、跑哪个流程。

AOS 让两层**解耦**：发现工具不必关心谁来执行，执行器不必关心机会怎么发现的。任何工具都可以**产出**或**消费** AOS，无需依赖时间审计本身。

> 时间审计是 AOS 的**参考实现**（reference producer），但 AOS 本身工具中立。

## 设计原则

1. **证据可回溯**：每条机会必须带 `evidence_sessions`，配合信封 `report_id` 能追回原始上下文，杜绝"模型凭空胡说"（解析方式见下『证据解析』）。
2. **分层即落地方式**：`layer` 不只是分类，它决定该怎么用（见下）。
3. **置信度与难度显式化**：消费方据此排序与过滤，而非盲信。规范拼写只有 `low/med/high`。
4. **加性演进**：MINOR 版本只增字段、不改旧字段语义；消费方必须忽略未知字段。
5. **身份与编号分离**：`id` 是报告内位置编号（不跨报告稳定）；`fingerprint` 才是跨报告稳定身份，用于回写与累积。

## 版本与稳定性

- 采用语义化版本 `MAJOR.MINOR.PATCH`。**版本的唯一真源是产出方代码常量 `report_query.SCHEMA_VERSION`**，规范 md 与本仓库测试以它为准对齐。
- **0.x = Draft**：当前处于草案期，`layer` 取值集合、枚举、必填字段等仍可能变化。鼓励试用与反馈，但请勿当作冻结标准依赖。
- **MINOR**：新增可选字段，向后兼容。消费方遇到未知字段**必须忽略**，不得报错。
- **MAJOR**：删除字段、改字段类型、改枚举语义、增删 `layer` 等破坏性变更。
- 当前 `schema_version = "0.1.0"`。产出方应在响应信封顶层带上 `schema_version`。

## 三个层级（`layer`）

| layer | 标识前缀 | 发现什么 | 消费方怎么用 |
|:--|:--|:--|:--|
| `point` | `P-xx` | 单次低效小动作（几秒~几十秒） | 做 snippet / 快捷键 |
| `line` | `L-xx` | 跨多 App、有固定步骤的流程 | 让 Agent 做多步自动化 skill（**最可执行**） |
| `surface` | `F-xx` | 角色级、工作方式级判断 | 反思工作方式，可能是减事而非加 skill |

`line` 是执行层最关心的层级——它带 `automation_difficulty`、`steps`、`estimated_weekly_savings_min`，可直接转成可执行任务。

## 对象定义

### 信封（Envelope）

产出方返回一批机会时的顶层结构（时间审计 MCP `query_automation_opportunities` 即此形）：

| 字段 | 类型 | 必填 | 说明 |
|:--|:--|:--:|:--|
| `schema_version` | string | ✓ | AOS 版本，如 `"0.1.0"` |
| `report_id` | string | ✓ | 数据来源标识（产出方自定义，如时间戳报告 id） |
| `produced_at` | string |  | 产出时间（建议 ISO-8601 或报告生成时间），便于判断新鲜度 |
| `producer` | string |  | 产出方标识，如 `"time-audit/v2 (LLM-driven)"`，便于判断来源与信任度 |
| `filters` | object |  | 本次返回所应用的过滤条件（回显，便于审计） |
| `count` | integer | ✓ | `opportunities` 条数 |
| `opportunities` | array<Opportunity> | ✓ | 机会列表 |

### Opportunity（公共字段）

所有机会共有：

| 字段 | 类型 | 必填 | 说明 |
|:--|:--|:--:|:--|
| `id` | string | ✓ | **报告内**稳定的位置编号，形如 `P-01` / `L-02` / `F-03`。不跨报告稳定 |
| `fingerprint` | string |  | **跨报告**稳定身份（形如 `fp_0a1b2c3d4e5f`），由内容特征派生。`execution_probe` 回写、去重、累积统计应以此为 join key |
| `layer` | enum | ✓ | `point` \| `line` \| `surface`（判别字段） |
| `confidence` | enum | ✓ | 规范拼写 `low` \| `med` \| `high`。`medium` 仅作入参别名被容忍，产出方须归一化为 `med`，**不得直接发出** |
| `evidence_sessions` | array<string> | ✓ | 证据会话编号，如 `["S001","S007"]`，配合 `report_id` 可回溯（见『证据解析』） |

### `layer = "point"` 额外字段

| 字段 | 类型 | 必填 | 说明 |
|:--|:--|:--:|:--|
| `title` | string | ✓ | 简短标题 |
| `description` | string | ✓ | 这个低效动作是什么 |
| `frequency_hint` | string |  | 频次提示，如"每天多次 / 每周15次" |
| `skill_suggestion` | string |  | 建议怎么解决（如做个快捷键） |

### `layer = "line"` 额外字段

| 字段 | 类型 | 必填 | 说明 |
|:--|:--|:--:|:--|
| `workflow_name` | string | ✓ | 流程名 |
| `trigger` | string |  | 触发条件，如"每天11:00" |
| `apps_involved` | array<string> |  | 涉及应用，如 `["Chrome","Word"]` |
| `steps` | array<string> |  | 有序步骤 |
| `occurrence_count` | integer\|null |  | 观察到的重复次数 |
| `avg_duration_min` | number\|null |  | 单次耗时（分钟） |
| `estimated_weekly_savings_min` | number\|null |  | **LLM 估算**的每周可省（分钟），ROI 排序用。实测值见 `execution_probe.verified_savings_min` |
| `automation_difficulty` | enum |  | `low` \| `med` \| `high`，自动化难度（同 `confidence` 的规范拼写约定） |
| `skill_suggestion` | string |  | 建议的自动化方式 |

### `layer = "surface"` 额外字段

| 字段 | 类型 | 必填 | 说明 |
|:--|:--|:--:|:--|
| `insight_title` | string | ✓ | 洞察标题 |
| `observation` | string | ✓ | 观察到的现象 |
| `implication` | string |  | 这意味着什么 |
| `recommendation` | string |  | 建议（可能是"减事"而非"加 skill"） |

> **关于 surface 层（设计决策 · 0.1.0）**：surface 是给「人」看的反思，不是给 Agent 执行的任务——它没有 `steps` / 难度这类可执行字段。消费方应把它当**背景洞察**展示，不要尝试自动执行。是否在 1.0 正式版保留 surface，留待有真实消费方反馈后再定；在此之前它与 point/line 清晰隔离、可随时移除，不影响其它两层。

## 扩展点（前向兼容）

消费方**必须忽略**未识别的字段。规范预留两类扩展：

- **`execution_probe`**（可选，object）：执行层回写的"实测可自动化性"。把 `automation_difficulty` 从 LLM 猜测升级为实测。建议结构：

  ```json
  {
    "execution_probe": {
      "agent": "fara-7b",
      "status": "not_run | success | partial | failed | blocked",
      "step_count": 16,
      "failure_point": "login_2fa",
      "risk_flags": ["sensitive_data", "requires_approval"],
      "verified_savings_min": 8
    }
  }
  ```

- **`x-` 前缀**：任何产出方私有的实验字段，以 `x-` 开头（如 `x-internal-score`）。未来标准字段不会使用该前缀，避免冲突。

## 证据解析（Evidence Resolution）

`evidence_sessions` 里的会话编号（如 `S001`）**只在其所属报告内有意义**——它不是全局可寻址的。一份 AOS 文档独立流转时，消费方要回到原始证据，需用 **`report_id` + `session_id` 二元组**向产出方解析：

```text
(report_id="20260603_000631", session_id="S001")
   └─ 时间审计：reports/report_<report_id>.json → raw_sessions[id == "S001"] → frames（含 timestamp / app / window / ocr）
```

约定：
- 产出方**应**保证：给定本次产出用的 `report_id`，其 `evidence_sessions` 内的编号可在该报告中解析。
- 消费方**不应**假设会话编号跨报告/跨产出方唯一。
- 若消费方拿不到原始报告（纯文档流转），证据即视为不可解析——此时应据 `confidence` 降级信任，而非当作已验证。

> ⚠️ 这是 Draft 阶段的已知边界：证据链目前依赖产出方的报告存储，AOS 文档本身**不自带**原始证据。未来版本可能引入可选的内联证据字段（`timestamp/app/window`）让机会自证。

## 完整示例

```json
{
  "schema_version": "0.1.0",
  "report_id": "20260603_000631",
  "produced_at": "2026-06-03 00:08:35",
  "producer": "time-audit/time-audit v2 (LLM-driven)",
  "filters": { "layer": "all", "min_confidence": null, "max_difficulty": null },
  "count": 2,
  "opportunities": [
    {
      "id": "L-01",
      "fingerprint": "fp_3f2a9c1d7e44",
      "layer": "line",
      "workflow_name": "病历文档填写与保存",
      "trigger": "每天11:00",
      "apps_involved": ["Chrome", "Word"],
      "steps": [
        "登录 HIS 系统查询患者信息",
        "打开 Word 病历模板",
        "填写患者基本信息和诊断摘要",
        "保存病历文档"
      ],
      "occurrence_count": 3,
      "avg_duration_min": 14,
      "estimated_weekly_savings_min": 70,
      "automation_difficulty": "low",
      "skill_suggestion": "自动从 HIS 拉取信息填入 Word 模板",
      "confidence": "high",
      "evidence_sessions": ["S001", "S007"]
    },
    {
      "id": "F-01",
      "fingerprint": "fp_8b5e0a2c9f31",
      "layer": "surface",
      "insight_title": "医生角色的工作模式",
      "observation": "用户频繁在 HIS 系统和 Word 中切换，进行患者信息查询与病历填写。",
      "implication": "工作高度依赖纸质模板，缺少电子化录入工具。",
      "recommendation": "引入结构化的电子病历系统，减少跨应用切换。",
      "confidence": "high",
      "evidence_sessions": ["S001", "S015"]
    }
  ]
}
```

## Conformance（一致性）

- **Conformant Producer**：产出的每个 Envelope 含 `schema_version`，每条 Opportunity 含全部公共必填字段及其所属 layer 的必填字段；`layer` / `confidence` / `automation_difficulty` 取值为**规范拼写**（`med`，而非 `medium`）；可选字段缺失时**省略**而非发空串。
- **Conformant Consumer**：能解析全部已定义字段；遇到未知字段忽略而非报错；不假设可选字段一定存在；用 `fingerprint`（而非 `id`）做跨报告关联。

机器可校验定义见同目录 [`automation-opportunity-schema.json`](./automation-opportunity-schema.json)（JSON Schema draft 2020-12）。本仓库 `tests/test_schema_conformance.py` 用 `jsonschema` 以**真实产出**跑该 schema，确保参考实现始终合规。

## 参考实现

- **产出**：时间审计 `time_audit/core/report_query.py:extract_opportunities`；MCP 工具 `query_automation_opportunities`。
- **版本常量**：`report_query.SCHEMA_VERSION`。
