# KOL Agent 设计文档

**日期**: 2026-02-22
**状态**: 待实现

---

## 背景

persona-lens 目前是单账号 CLI 工具，生成个人画像报告。本次扩展目标是在其基础上构建一个 **Tool-Use Agent**，支持：

1. **批量分析达人**（5–20 个账号）
   - 最高频发帖时间点
   - 近期提及的产品及其分类
   - 高互动帖子的产品和话术规律洞察

2. **内容方向匹配**
   - 给定若干内容方向描述（如 AI 测评、技术分析、路人口吻）
   - 自动匹配最适合发布该内容的达人

**交互形式**: CLI（后续计划加 UI）
**账号规模**: 单次 5–20 个

---

## 架构

```
用户输入 (accounts.txt + briefs.txt)
          ↓
    Agent Core (Python)
    LLM (Claude claude-sonnet-4-6) + Tool Definitions
          ↓
    工具调用循环
    ├── fetch_user_tweets        ← Camofox Browser / Nitter（复用现有代码）
    ├── extract_tweet_data       ← 正则解析原始快照，保留互动数字
    ├── compute_posting_patterns ← snowflake 解码，纯计算
    ├── analyze_products         ← LLM：提取产品提及 + 分类
    ├── find_engagement_patterns ← LLM：高互动规律洞察
    └── match_content_briefs     ← LLM：内容方向 × 达人画像匹配
          ↓
    Markdown 报告输出
```

---

## 工具设计

### Token 控制策略

- 工具只返回结构化 JSON，不把原始快照传给 LLM
- LLM 只在三个工具中参与推理，其余工具为纯 Python 计算
- 批量账号顺序处理（避免 Camofox tab 上限触发 429）

### 工具列表

| 工具 | 输入 | 输出 | 实现 |
|------|------|------|------|
| `fetch_user_tweets(username, n)` | 用户名、推文数 | 原始快照字符串 | 复用 `fetchers/x.py:fetch_snapshot` |
| `extract_tweet_data(snapshot)` | 原始快照 | `[{id, text, likes, retweets, replies, timestamp_ms}]` | 正则解析，在 clean 前运行 |
| `compute_posting_patterns(tweets)` | tweet 列表 | `{peak_days, peak_hours}` | snowflake 解码，纯计算 |
| `analyze_products(username, tweets)` | tweet 列表 | `[{product, category, tweet_ids}]` | 单次 LLM 调用 |
| `find_engagement_patterns(all_data)` | 所有用户数据 | 洞察文本 + 结构化规律 | 单次 LLM 调用 |
| `match_content_briefs(briefs, profiles)` | 内容方向列表 + 用户画像 | `[{brief, matched_users, reason}]` | 单次 LLM 调用 |

### 关键实现细节

**`extract_tweet_data`**：必须在 `clean_snapshot()` 之前运行，因为 `clean_snapshot` 会丢弃互动数字行（`re.fullmatch(r'[\d,\s]+', content)`）。原始快照中每条推文后跟一行纯数字格式的互动统计，需先提取再清理。

**`fetch_user_tweets`**：顺序执行，不并发。每个账号用完后 `DELETE /tabs/:id`，避免 tab 累积。

**产品分类体系**（`analyze_products` 的分类维度）：
- AI 工具（编程/写作/图像/视频/Agent）
- SaaS 工具
- 硬件/消费电子
- 开发工具（非 AI）
- 其他

---

## 文件结构

```
persona_lens/
  fetchers/
    x.py                      # 现有，不改动
  analyzers/
    openai_analyzer.py        # 现有
    product_analyzer.py       # 新增：analyze_products 实现
    engagement_analyzer.py    # 新增：find_engagement_patterns 实现
    content_matcher.py        # 新增：match_content_briefs 实现
  agent/
    __init__.py
    core.py                   # Agent 主循环 + 工具注册 + LLM 调用
    tools.py                  # 工具 schema 定义 + Python 函数映射
    cli.py                    # 新 CLI 入口
```

---

## CLI 接口

```bash
# 批量分析达人
uv run persona-lens-agent \
  --accounts accounts.txt \
  --tweets 30 \
  --output report.md

# 含内容方向匹配
uv run persona-lens-agent \
  --accounts accounts.txt \
  --briefs briefs.txt \
  --tweets 30 \
  --output report.md
```

**accounts.txt 格式**（每行一个用户名）：
```
elonmusk
sama
karpathy
```

**briefs.txt 格式**（每行一个内容方向描述）：
```
AI产品测评，大众口吻，有趣易懂
技术深度分析，dev 口吻，引用数据
观望态度，路人视角，自然口语
```

---

## 输出报告结构

```markdown
# KOL 批量分析报告

## 汇总洞察
- 最高频发帖时间：UTC 14:00–17:00（多数达人集中于此）
- 高互动产品类型：AI 编程工具 > AI 写作工具
- 话术规律：技术对比 + 亲身测评 > 纯宣传

## 各达人分析
### @karpathy
- 发帖高峰：周二 UTC 15:00
- 近期产品提及：Cursor、Claude、Gemini
- 高互动规律：技术测评 + 对比类帖子互动最高

## 内容方向匹配
| 内容方向 | 推荐达人 | 匹配理由 |
|---------|---------|---------|
| AI 产品测评 | @karpathy | 技术 + 易读风格，测评类帖互动高 |
| 技术深度分析 | @sama | dev 口吻，数据引用多 |
| 路人自然口吻 | @elonmusk | 随性风格，高频互动 |
```

---

## 待确认事项

- [ ] Nitter 原始快照是否包含浏览量（view count）？需用 `--debug` 确认字段格式
- [ ] LLM 选用 Claude claude-sonnet-4-6 还是 GPT-4o？（项目现用 OpenAI，可切换）
