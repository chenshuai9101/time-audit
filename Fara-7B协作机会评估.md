# Fara-7B 与时间审计项目的协作机会评估

生成日期：2026-06-02

## 结论

Fara-7B 不适合直接替换时间审计当前的文本分析模型。更合理的位置是：时间审计负责从 Screenpipe 历史记录中发现“哪些工作值得自动化”，Fara-7B 负责把其中一部分 web / browser 工作流跑成可验证的 computer-use 执行动作。

一句话架构：

```text
Screenpipe 历史数据
  -> 时间审计：压缩、归因、发现点/线/面
  -> 候选自动化任务
  -> Fara-7B：在浏览器沙箱中尝试执行
  -> 轨迹、成功/失败、节省时间
  -> 回写时间审计报告，形成 skill 候选池
```

这不是“模型接入”问题，而是“发现层 + 执行层 + 验证层”的产品闭环问题。

## 当前项目边界

时间审计当前是一个本地优先的 Python CLI：

- 数据源：Screenpipe SQLite、CSV 或模拟数据。
- 压缩层：`time_audit/core/event_compressor.py` 把大量 OCR 事件压成 session。
- 分析层：`time_audit/core/llm_analyzer.py` 只接 Ollama 文本模型 `/api/generate`。
- 输出层：`time_audit/core/report_builder.py` 生成 JSON 和 Markdown。
- 洞察结构：点、线、面三层，重点是“发现可 skill 化的工作模式”。

当前瓶颈不是“缺一个更强聊天模型”，而是：

- 发现出来的 `lines` 还停在建议层，没有执行验证。
- 报告没有记录“这个建议是否真的能自动化成功”。
- 没有把历史 OCR 证据转成可执行任务说明、浏览器起始状态和验收标准。

## Fara-7B 的可用能力

根据 Microsoft 官方资料，Fara-7B 是 7B 参数的 Computer Use Agent，面向网页/浏览器任务。它通过截图观察界面，并输出点击、输入、滚动、访问 URL 等工具调用，而不是只返回文本回答。它基于 Qwen2.5-VL-7B，训练数据来自多步 web 任务轨迹，官方仓库支持通过 vLLM、LM Studio 或 Ollama/本地 GGUF 方式托管。

对时间审计最重要的特征是：

- 它天然适合“浏览器里的重复流程”，如查询、填表、信息检索、账号流程、预订、比价。
- 它使用可见屏幕和坐标动作，更接近真实用户操作路径。
- 它是本地/私有部署友好的小模型，和时间审计的隐私叙事一致。
- 它仍是实验性模型，需要沙箱、人工监督和高风险操作拦截。

资料来源：

- Microsoft Research: https://www.microsoft.com/en-us/research/blog/fara-7b-an-efficient-agentic-model-for-computer-use/
- GitHub: https://github.com/microsoft/fara
- arXiv: https://arxiv.org/abs/2511.19663

## 三类协作机会

### 1. 最值得做：把时间审计报告转成 Fara 任务

目标：从 `ai_insights.lines` 中筛选适合浏览器执行的流程，生成 Fara 可执行任务。

适合条件：

- `apps_involved` 包含 Chrome、Safari、Edge、Browser、Web App。
- `automation_difficulty` 为 `low` 或 `med`。
- `confidence` 为 `high` 或 `med`。
- 步骤里出现查询、打开网站、复制信息、填写表单、下载文件、提交非敏感内容等动作。

新增产物可以是：

```json
{
  "task_id": "L-02",
  "source_workflow": "病历系统信息查询",
  "fara_task": "打开指定系统，查询患者 ID 对应的基础信息，并整理为摘要。",
  "start_url": "https://...",
  "allowed_domains": ["..."],
  "requires_human_approval": true,
  "success_criteria": [
    "页面显示目标记录",
    "摘要包含姓名、诊断、日期",
    "不提交或修改任何生产数据"
  ],
  "evidence_sessions": ["S001", "S007"]
}
```

这是最小闭环：时间审计发现任务，Fara 尝试执行，人确认是否有价值。

### 2. 很有价值：用 Fara 轨迹反哺时间审计的“可自动化性评分”

当前报告里的 `automation_difficulty` 是 LLM 猜测。引入 Fara 后，可以变成实测：

- 是否能打开目标页面。
- 是否能定位关键 UI。
- 是否能完成前 3 步。
- 是否在登录、验证码、权限、支付、隐私信息处停住。
- 平均动作步数是多少。
- 失败发生在哪一步。

建议给每条 `line` 增加字段：

```json
{
  "execution_probe": {
    "agent": "fara-7b",
    "status": "not_run|success|partial|failed|blocked",
    "step_count": 16,
    "failure_point": "login_2fa",
    "risk_flags": ["sensitive_data", "requires_approval"],
    "verified_savings_min": 8
  }
}
```

这样时间审计从“建议生成器”升级成“自动化机会评估器”。

### 3. 中长期：Screenpipe 历史截图到 Fara 训练/评测轨迹

时间审计手里最有价值的不是 OCR 文本，而是“真实用户工作流的历史轨迹”。如果能把 Screenpipe 的截图、窗口、OCR、时间戳整理成 observe-think-act 风格的数据，就能用于：

- 建立私有 workflow benchmark。
- 评估 Fara 在用户真实工作流上的成功率。
- 沉淀企业/个人专属的 computer-use skill 数据。

但这一步复杂度高，因为历史记录缺少用户真实动作标签，只有屏幕状态和 OCR。短期不建议先做训练数据，建议先做离线评测和任务探针。

## 不建议现在做的事

- 不建议把 Fara-7B 作为 `llm_analyzer.py` 的普通文本模型替换。它的强项是截图驱动动作，不是纯文本报告归纳。
- 不建议直接让 Fara 操作真实工作账号。先限定浏览器沙箱、测试账号、只读流程。
- 不建议一开始做“全自动 skill 生成”。应该先做候选任务导出、人工确认、执行探针、再谈自动化。
- 不建议把所有 Screenpipe 截图都喂给 Fara。成本高、隐私风险高，也不符合它的执行式使用方式。

## MVP 方案

### MVP-1：报告到 Fara 任务清单

工作量：小。

改动：

- 新增 `time_audit/core/fara_exporter.py`。
- 从报告 JSON 读取 `ai_insights.lines`。
- 按 app、置信度、难度筛选浏览器流程。
- 输出 `reports/fara_tasks_*.json`。
- CLI 增加 `--export-fara-tasks`。

价值：

- 不需要先跑 Fara。
- 立即验证时间审计报告能不能变成 agent backlog。
- 是后续执行探针的输入层。

### MVP-2：Fara 执行探针

工作量：中。

改动：

- 增加 `fara` provider 配置，指向 Fara CLI 或 OpenAI-compatible endpoint。
- 每个任务只跑 dry-run / headful sandbox。
- 保存轨迹文件、截图摘要、失败点。
- 把结果回写到报告 JSON。

价值：

- 把“可能自动化”变成“已试跑、可验证”。
- 能快速识别哪些机会是假机会，例如登录、验证码、权限、上下文不足。

### MVP-3：Agent/MCP 模式

工作量：中到大。

改动：

- 时间审计提供 MCP server 或本地 API。
- 外部 agent 查询“最值得自动化的流程”。
- Fara/Magentic-UI 作为执行器读取任务。

价值：

- 让时间审计成为 agent 的用户工作画像层。
- 适合和 OpenClaw、Magentic-UI、Claude/Codex 类工具协作。

## 推荐优先级

1. 先做 `fara_tasks` 导出，不接模型。
2. 用 3-5 条真实报告里的浏览器流程手工跑 Fara，验证任务描述是否足够。
3. 再做执行探针，把成功率、失败点、风险标记写回报告。
4. 最后再考虑 MCP server 或持续学习。

## 判断标准

这个方向值得继续投入，当且仅当满足以下条件：

- 时间审计能稳定发现每周重复 2 次以上的浏览器流程。
- Fara 能在沙箱中完成或部分完成至少 30%-50% 的候选流程。
- 执行失败原因可被归类，而不是随机不可解释。
- 用户愿意对高风险动作做人工审批。

如果候选流程主要发生在 Word、Excel、本地文件系统、微信、医疗内网客户端，Fara-7B 的价值会明显下降；这时更应该走 AppleScript、Playwright、RPA、MCP tool 或专用 skill，而不是 computer-use agent。

