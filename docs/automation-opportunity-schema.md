# Automation Opportunity Schema (AOS)

> 一份可移植的契约，描述"一条值得自动化的工作机会"长什么样。
> **版本：1.0.0** · 状态：Stable · License：MIT（随项目）

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

1. **证据可回溯**：每条机会必须带 `evidence_sessions`，能追回原始上下文，杜绝"模型凭空胡说"。
2. **分层即落地方式**：`layer` 不只是分类，它决定该怎么用（见下）。
3. **置信度与难度显式化**：消费方据此排序与过滤，而非盲信。
4. **加性演进**：新版本只增字段、不改旧字段语义；消费方必须忽略未知字段。

## 版本与稳定性

- 采用语义化版本 `MAJOR.MINOR.PATCH`。
- **MINOR**：新增可选字段，向后兼容。消费方遇到未知字段**必须忽略**，不得报错。
- **MAJOR**：删除字段、改字段类型或改枚举语义等破坏性变更。
- 当前 `schema_version = "1.0.0"`。产出方应在响应信封顶层带上 `schema_version`。

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
| `schema_version` | string | ✓ | AOS 版本，如 `"1.0.0"` |
| `report_id` | string | ✓ | 数据来源标识（产出方自定义，如时间戳报告 id） |
| `filters` | object |  | 本次返回所应用的过滤条件（回显，便于审计） |
| `count` | integer | ✓ | `opportunities` 条数 |
| `opportunities` | array<Opportunity> | ✓ | 机会列表 |

### Opportunity（公共字段）

所有机会共有：

| 字段 | 类型 | 必填 | 说明 |
|:--|:--|:--:|:--|
| `id` | string | ✓ | 在一份报告内稳定的编号，形如 `P-01` / `L-02` / `F-03` |
| `layer` | enum | ✓ | `point` \| `line` \| `surface`（判别字段） |
| `confidence` | enum | ✓ | `low` \| `med` \| `high`（也接受 `medium` 作 `med` 的别名） |
| `evidence_sessions` | array<string> | ✓ | 证据会话编号，如 `["S001","S007"]`，可回溯原始上下文 |

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
| `estimated_weekly_savings_min` | number\|null |  | 预计每周可省（分钟），ROI 排序用 |
| `automation_difficulty` | enum |  | `low` \| `med` \| `high`，自动化难度 |
| `skill_suggestion` | string |  | 建议的自动化方式 |

### `layer = "surface"` 额外字段

| 字段 | 类型 | 必填 | 说明 |
|:--|:--|:--:|:--|
| `insight_title` | string | ✓ | 洞察标题 |
| `observation` | string | ✓ | 观察到的现象 |
| `implication` | string |  | 这意味着什么 |
| `recommendation` | string |  | 建议（可能是"减事"而非"加 skill"） |

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

## 完整示例

```json
{
  "schema_version": "1.0.0",
  "report_id": "20260603_000631",
  "filters": { "layer": "all", "min_confidence": null, "max_difficulty": null },
  "count": 2,
  "opportunities": [
    {
      "id": "L-01",
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

- **Conformant Producer**：产出的每个 Envelope 含 `schema_version`，每条 Opportunity 含全部公共必填字段及其所属 layer 的必填字段；`layer` / `confidence` 取值在枚举内。
- **Conformant Consumer**：能解析全部已定义字段；遇到未知字段忽略而非报错；不假设可选字段一定存在。

机器可校验定义见同目录 [`automation-opportunity-schema.v1.json`](./automation-opportunity-schema.v1.json)（JSON Schema draft 2020-12）。

## 参考实现

- **产出**：时间审计 `time_audit/core/report_query.py:extract_opportunities`；MCP 工具 `query_automation_opportunities`。
- **版本常量**：`report_query.SCHEMA_VERSION`。
