# stock_scout

每日自動運行嘅股票偵測哨兵：喺「大眾未知、但已有一小群專業人士討論／行動」嘅階段，
發現潛力股同爆紅產品，並用 LLM 總結背後嘅故事，以 daily digest 送到 Slack 頻道（資料庫用 Supabase）。

呢個工具係 idea discovery 研究助手，**唔係交易信號**，唔接自動交易。

## 文件

- **[SPEC.md](SPEC.md)** — 產品規格書：功能需求、評分規格、數據模型、架構、里程碑與驗收
- **[PLAN.md](PLAN.md)** — 背景分析：原構想嘅盲點修正、數據源 brainstorm、決策依據

## 快速開始

```bash
pip install -e ".[dev]"
pytest                       # 測試
stock-scout run --dry-run    # 假數據走通全流程，唔使任何 credentials
```

## 部署（GitHub Actions，每日兩次）

1. 開 Supabase project，攞 connection string
2. 開 Slack app，俾 bot `chat:write` + `reactions:read` scope，邀請入目標頻道
3. 喺 repo Settings → Secrets and variables → Actions 加入：

| Secret | 內容 |
|---|---|
| `DATABASE_URL` | Supabase Postgres connection string |
| `DEEPSEEK_API_KEY` | DeepSeek 官方 API（故事總結）：https://platform.deepseek.com |
| `SLACK_BOT_TOKEN` | Slack bot token（xoxb-…） |
| `SLACK_CHANNEL_ID` | 目標頻道 ID（C…） |
| `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` | **可選**。冇嘅話會自動改用 Reddit 公開 JSON endpoint（慢啲但唔使申請 app）；有嘅話用官方 API（要 `pip install -e ".[praw]"`） |
| `X_BEARER_TOKEN` | **可選**。X (Twitter) API v2 bearer token，另外要喺 `config/sources.yaml` 將 `x.enabled` 設做 `true`。注意：Free tier 冇 search，用唔到；要 Basic tier 或以上 |
| `ANTHROPIC_API_KEY` | **可選**。想改用 Claude 做總結先需要（`config/scoring.yaml` 將 `llm.provider` 改做 `anthropic`） |

4. 初始化 schema：本地 `DATABASE_URL=... stock-scout init-db`
5. 完成——`.github/workflows/daily.yml` 會喺美股盤前（12:00 UTC）同收市後（21:30 UTC）自動運行；
   digest 同步存檔喺 `digests/`

## 狀態

M0 骨架 ＋ M1 Reddit MVP 代碼完成（見 SPEC.md §9）。
每日 digest 喺 Slack 出現；喺 alert message 上面 react 👍/👎 就係反饋，下次運行自動收集。
