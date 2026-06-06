# Time Audit Pipe（Screenpipe 插件）

把「时间审计」封装成一个 Screenpipe pipe：Screenpipe 每 12 小时自动唤醒一个编码 Agent
（Claude Code / Cursor 等），让它调用本机的 `time-audit` 跑一次分析，产出**人类小结** +
**标准 AOS 文件**，无需你手动运行。

这是面向 Screenpipe 用户的「入门体验」——先让人看到效果，再决定要不要用完整 CLI。

## 它做什么

每 12 小时：
1. 检查本地分析引擎（Ollama / 云端）是否就绪；
2. `time-audit --days 1` 分析最近一天的屏幕活动（读 Screenpipe 库 → 压缩 → 本地 LLM 三层分析）；
3. `python -m time_audit.aos_export` 导出标准 AOS 文件；
4. 把最值得自动化的流程讲给你听，并存一份小结到 `~/Desktop/时间审计-自动发现/`。

产出物：
- `~/Desktop/时间审计/reports/report_<id>.md` — 人类可读报告
- `~/Desktop/时间审计/reports/aos_<id>.json` — AOS 标准文件（供其它 Agent 消费）
- `~/Desktop/时间审计-自动发现/summary-<时间>.md` — 本次小结

## 前置条件

1. **Screenpipe 正在录制**（pipe 靠它的数据库吃饭）。
2. **`time-audit` 已安装且在 PATH 上**。验证：
   ```bash
   time-audit --version
   ```
   若未安装：在时间审计项目根目录 `pip install -e .`（建议用项目自带的 `.venv`）。
   若不在 PATH：把 pipe.md 里的 `time-audit` 换成你的绝对路径，例如
   `~/Desktop/时间审计/.venv/bin/time-audit`，并把 `python` 换成 `~/Desktop/时间审计/.venv/bin/python`。
3. **分析引擎二选一**：本地 Ollama 已启动（隐私优先，默认），或已配置云端 API key。
   验证：`time-audit --check-llm`。未就绪时 pipe 会自动降级为「只统计活动量」并提示你。

## 安装

### 方式 A：从 GitHub 安装（推荐，无需 Screenpipe 云账号）

```bash
# 1. 克隆本仓库
git clone https://github.com/chenshuai9101/time-audit.git
cd time-audit

# 2. 安装 time-audit CLI（pipe 靠它干活）
pip install -e .

# 3. 用 Screenpipe 安装本 pipe（接受本地路径）
screenpipe pipe install ./pipes/time-audit

# 4. 确认已装上 + 启用
screenpipe pipe list        # 应能看到 time-audit, schedule = every 12h
screenpipe pipe enable time-audit
```

> `screenpipe pipe install` 接受本地路径或 URL，因此**不依赖 Screenpipe 云商店**——
> 克隆仓库后本地安装即可。（云 registry 的 `pipe publish` 需要登录 Screenpipe 云账号，
> 在部分地区不可用，不影响本安装方式。）

### 方式 B：手动复制 / 软链

```bash
# 复制
cp -r pipes/time-audit ~/.screenpipe/pipes/time-audit

# 或软链（改动本仓库即生效，便于迭代）
ln -s "$(pwd)/pipes/time-audit" ~/.screenpipe/pipes/time-audit
```

然后在 Screenpipe 里启用该 pipe（或确认 `pipe.md` 头部 `enabled: true`）。

## 手动试跑（不等 12 小时）

想立刻看到效果、验证链路是否通，直接在终端按 pipe 的步骤手跑一遍：

```bash
time-audit --check-llm        # 1. 引擎探活
time-audit --days 1           # 2. 分析最近一天
python -m time_audit.aos_export   # 3. 导出 AOS 文件
```

看 `~/Desktop/时间审计/reports/` 下最新的 `report_*.md` 与 `aos_*.json`。

## 已知限制（MVP）

- **粒度是「天」不是「12 小时」**：CLI 最细按天分析，pipe 每 12h 跑一次会有约一天的重叠覆盖。
  单次报告内部已去重，不影响阅读；彻底解决要等增量分析（v2.3，未开发）。
- **建议质量 = 模型质量**：本地 7B 模型的「面（surface）」层洞察有限；要更准可切云端模型。
- **单机单用户**：不聚合多设备/团队。

## 与完整 CLI 的关系

| | 本 pipe | 完整 CLI |
|--|--|--|
| 触发 | Screenpipe 每 12h 自动 | 手动 `time-audit --days N` |
| 深度 | 最近 1 天 | 任意天数全量 |
| 定位 | 入门体验、看效果 | 深度分析、完整控制 |

pipe 觉得有用 → 直接用 CLI 跑更长区间、更深分析。两者共用同一套分析与 AOS 产出逻辑。
