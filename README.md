<h1 align="center">⏱  时间审计 · Time Audit</h1>

<p align="center">
  <b>本地大模型驱动的工作行为分析中间件</b><br>
  把屏幕录制的海量数据，变成本地 AI 能消化的会话片段，<br>
  替你看清这一周到底花在哪了——以及哪些事情可以让 AI 替你做。
</p>

<p align="center">
  <img src="https://img.shields.io/badge/license-MIT-blue.svg">
  <img src="https://img.shields.io/badge/python-3.8+-green.svg">
  <img src="https://img.shields.io/badge/llm-ollama-orange.svg">
  <img src="https://img.shields.io/badge/version-2.0.0-purple.svg">
  <img src="https://img.shields.io/badge/privacy-local--only-success.svg">
</p>

---

## 一句话定位

> 让本地大模型看一眼你最近两周的电脑使用记录，告诉你——
> **你哪些事在重复、哪些可以让 AI 替你做、哪些根本不该再做。**
>
> 数据从不离机。屏幕、模型推理、洞察报告全在你电脑上完成。

## 为什么需要这个

大多数人对自己一天的工作其实是失忆的。你以为在写代码，实际三分之一时间在切窗口；你以为日报花十分钟，实际跟着前后准备要四十分钟；你以为某些操作只做一次，其实每周做三次。

市面上看似相关的工具有两类，但都解决不了这个问题：

- **时间追踪类**（RescueTime / Toggl）只告诉你"用了哪个 App 多久"，看不见你在 App 里做了什么
- **录屏检索类**（Screenpipe / Rewind / Microsoft Recall）能记住所有内容，但是**被动的**——你得知道要问什么才能查出来

时间审计填的是中间这层：**主动从录屏数据里挖出可以让 AI 替你做的工作模式**。它不替你回忆，它替你诊断。

## 核心架构

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐    ┌──────────────┐
│  Screenpipe     │ →  │ event_compressor │ →  │ 本地 LLM        │ →  │  分析报告     │
│  (录屏+OCR)     │    │ 切分 / 去重 / 采样│    │ (Ollama)        │    │ JSON + MD    │
│  本地 SQLite    │    │  把万级事件压成   │    │ 跑"点/线/面"    │    │ 给人看        │
│                 │    │  千级会话片段     │    │ 三套 prompt     │    │ 给 Agent 用   │
└─────────────────┘    └──────────────────┘    └─────────────────┘    └──────────────┘
       原始数据             解决喂不进的问题         真正做语义分析          可执行洞察
```

唯一在动脑的是**事件压缩器**。它做的事很无聊但必须做：屏幕没变时 OCR 文本会反复出现，海量重复必须先扔掉，长会话必须采样，否则本地 14B 模型一次塞不进一周的数据。剩下的语义判断全部交给 LLM，因为统计算法做不到。

## 三层洞察：点 / 线 / 面

时间审计不出"通用建议"。每条洞察都被归到三层之一，**层级决定该怎么落地**。

| 层 | 标识 | 它发现什么 | 你怎么用 |
|:--|:--|:--|:--|
| **点** | P-xx | 单次低效的小动作，几秒到几十秒 | 做个 snippet / 快捷键 |
| **线** | L-xx | 跨多个 App、有固定步骤的流程 | 让 Agent 做多步自动化 skill |
| **面** | F-xx | 角色级、工作方式级的判断 | 反思工作方式，可能是减事而非加 skill |

每一条都带着 **session 编号** 作为证据（S001、S007…），可以追回原始上下文，不是 LLM 凭空胡说。

### 实际输出长什么样

跑过一次后你会拿到这样的报告片段（真实运行输出，不是宣传图）：

```markdown
### P-02 查询每日销售数据 · 置信度 high
- 描述：用户频繁通过SQL语句查询当前日期的销售记录。
- 频次：每天多次 / 每周15次
- 建议：创建预设查询，一键获取销售数据。
- 证据：S001, S002, S003, S004, S005

### L-02 病历文档填写与保存 · 难度 low · 置信度 high
- 触发：每天11:00
- 涉及应用：Chrome, Word
- 重复次数：3
- 单次耗时：约 14 分钟
- 预计周节省：70 分钟
- 步骤：
  1. 登录 HIS 系统查询患者信息
  2. 打开 Word 病历模板
  3. 填写患者基本信息和诊断摘要
  4. 保存病历文档

### F-04 医生角色的工作模式 · 置信度 high
- 现象：用户频繁在HIS系统和Word中切换，进行患者信息查询与病历填写。
- 含义：表明用户工作高度依赖纸质模板，缺少电子化录入工具。
- 建议：引入结构化的电子病历系统，减少跨应用切换。
- 证据：S001, S007, S015
```

## 快速开始

### 路径 A · 还没装 Screenpipe，想看看效果

```bash
git clone https://github.com/<your>/time-audit && cd time-audit
pip install -e .
time-audit --dryrun --days 7
```

会用内置的多场景模拟数据（医生 / 程序员 / 运营场景）跑出报告样本，看看产品长什么样再决定要不要接真实数据。

### 路径 B · 完整链路

需要本地装 [Ollama](https://ollama.com/) 和一个能跑的模型：

```bash
brew install ollama && ollama serve &
ollama pull qwen2.5:7b              # 入门款；机器够大可换 14b / 32b

cd time-audit && pip install -e .
time-audit --check-llm              # 探活
time-audit --days 14                # 跑真分析
time-audit --report                 # 看最近报告
```

完整流程在 7B 模型上 5 分钟左右，14B 模型 10–15 分钟。**不实时，只批跑**——这是隐私和性能之间的取舍。

### 路径 C · Agent 开发者

报告是结构化 JSON，schema 在 `time_audit/core/report_builder.py` 的 `build_report()`。直接读：

```python
import json, pathlib
report_dir = pathlib.Path("~/Desktop/时间审计/reports").expanduser()
report = json.loads(sorted(report_dir.glob("report_*.json"))[-1].read_text())

for line in report["ai_insights"]["lines"]:
    if line["confidence"] == "high":
        agent.suggest_skill(line)
```

每条洞察都带 `evidence_sessions` 与 `confidence`，可直接喂给 Agent 做决策依据。

## 模型选型

| 模型 | 内存 | 能做什么 |
|:--|:--|:--|
| `llama3.2:1b` | ~2 GB | 仅供调试，几乎没有"线/面"能力 |
| `qwen2.5:7b` | ~7 GB | 入门门槛，"点/线"够用 |
| `qwen2.5:14b` | ~14 GB | 推荐基线，"面"层勉强 |
| `qwen2.5:32b` | ~32 GB | 全功能，"面"层有质感，需 64G 内存 |
| `gpt-oss:20b` | ~20 GB | 中等机器的甜点，质量优于 14B |

中文用户首选 Qwen 系列：中文 OCR 文本理解明显优于 Llama。

## 隐私设计

不是营销话术，是架构事实：

- **录制层**：Screenpipe 在本地，写入本地 SQLite
- **分析层**：时间审计读本地 SQLite，连接本地 11434 端口
- **推理层**：Ollama 跑本地模型，无网络请求
- **输出层**：报告写入本地磁盘
- **分发层**：本仓库不到 1000 行 Python，可全文审计，**无任何 telemetry / 联网代码**

唯一的网络访问是 `pip install` 本身。装完之后整条链路可以断网运行。

## 项目结构

```
time-audit/
├── time_audit/
│   ├── main.py                   # CLI 编排
│   └── core/
│       ├── db_reader.py          # Screenpipe SQLite / CSV / 模拟数据
│       ├── event_compressor.py   # ⭐ 事件流压缩（核心）
│       ├── frequency_analyzer.py # 给 LLM 的 context hint
│       ├── prompts.py            # 点/线/面 三套 prompt
│       ├── llm_analyzer.py       # Ollama HTTP 调用与批处理
│       └── report_builder.py     # LLM 输出 → JSON+MD 渲染
├── config/time_audit.yaml        # 阈值与模型配置
├── reports/                      # 历史报告
├── pyproject.toml
└── README.md
```

## 常见问题

**Q: 没有 Screenpipe 也能跑吗？**
能。`--dryrun` 用模拟数据跑完整链路，结构与真实运行完全一致。也支持自定义 CSV（格式见 `core/db_reader.py:read_custom_csv`）。

**Q: 屏幕数据会上传吗？**
不会。检查 `core/llm_analyzer.py` 里唯一的网络调用——只指向 `localhost:11434`。

**Q: 为什么不用 GPT-4 / Claude，效果不是更好？**
当然更好。但这违背隐私前提。屏幕录制是最敏感的数据之一，时间审计选择"用本地 7B 也要做出能用的产品"作为硬约束。如果你不在乎隐私，需求和 Rewind / Microsoft Recall 的重合度更高。

**Q: 跑出来的洞察是错的怎么办？**
每条洞察带 `evidence_sessions`，可以回溯到原始事件。错的多半因为：① 数据量太少（< 7 天）；② 模型太小（< 7B）；③ Screenpipe OCR 质量差。先调这三处。

**Q: 跟 Screenpipe 自带的 chat 有什么区别？**
Screenpipe chat 是**被动**的，需要你知道问什么。时间审计是**主动**的，从未被问过的角度提出"你这事可以让 AI 替你做"。一个解决检索，一个解决发现。

## 路线图

- [x] **v2.0** LLM 化重构（点/线/面三层 + 本地 Ollama）
- [ ] **v2.1** 增量分析（只跑新增数据，缩短迭代周期）
- [ ] **v2.2** MCP server 模式（Agent 直连而非读文件）
- [ ] **v2.3** 多模型对比（同一份数据三个模型并跑，对比质量）
- [ ] **v2.4** 团队脱敏聚合（B 端方向，发现"全团队共有的低效"）
- [ ] **v3.0** 持续学习（用户反馈"建议是否落地"反喂 prompt）

## 适合谁

- 怀疑自己时间被偷走、想做客观时间审计的个人
- 在做 AI Agent / Skill 平台、需要"用户工作画像"做主动建议的开发者
- 重视本地优先、不想把屏幕数据交给云的隐私敏感用户
- 中小团队负责人，想找出团队层面共有的低效环节

## 不适合谁

- 想要实时通知 / 实时干预的用户（当前是批跑）
- 没有任何本地推理资源的机器（< 8 GB 内存跑不动 7B 模型）
- 期待开箱即用、无需任何调参的用户（默认参数对不同行业可能需要调整）

## 致谢

- [Screenpipe](https://github.com/mediar-ai/screenpipe) — 提供了底层录制与 OCR 能力
- [Ollama](https://ollama.com/) — 让本地 LLM 真正可用
- 通义千问 / Llama / Phi 等开源模型团队

时间审计只是站在他们肩上的一层薄薄的中间件。

## License

MIT — 用、改、卖都行，唯一要求是别假装是你写的。
