# Stock Scout — 產品規格書（Product Spec）v1.1

> 一句話定位：一個每日自動運行嘅偵測哨兵，喺「大眾未知、但已有一小群專業人士討論／行動」嘅階段
> 發現潛力股同爆紅產品，並用 LLM 總結背後嘅故事，以 daily digest 形式送到用戶嘅 Slack 頻道。
>
> 相關文件：[PLAN.md](PLAN.md)（背景分析、盲點修正、數據源 brainstorm——本 spec 嘅決策依據）
>
> v1.1 變更：落實用戶決定——通知通道 Slack、資料庫 Supabase、v1 淨做美股、每日兩次、
> 唔設市值上限、包埋 penny stocks（§12 已決事項）。

---

## 1. 產品概述

### 1.1 定位

- **係乜**：idea discovery 研究助手。輸出係「呢隻股值得你今晚花 30 分鐘研究」嘅高質候選名單＋故事總結
- **唔係乜**（non-goals）：
  - ❌ 唔係交易信號，唔接自動交易
  - ❌ 唔係 real-time 系統——每日 batch 2 次
  - ❌ 唔係大眾情緒儀表板（嗰啲已經有 ApeWisdom／SwaggyStocks）
  - ❌ 唔做多用戶 SaaS——單用戶個人工具

### 1.2 用戶與場景

單一用戶。每日喺指定 Slack 頻道收到 digest，5 分鐘內判斷邊隻值得深入研究；
每隻候選附原文連結，方便自行驗證。用戶用 Slack emoji reaction（👍/👎）對 alert 標記質素，
下次運行時系統讀返 reactions 記入資料庫，餵俾回測層。
資料庫用 Supabase，用戶可以隨時經 Supabase connector 直接同 Claude 傾住嚟查數據。

### 1.3 成功標準

1. **有用率**：用戶標記「值得研究」嘅 alert 比例 ≥ 30%
2. **領先性**（回測驗證）：alert 後 20 個交易日，候選股相對 SPY 嘅超額回報中位數 > 0
3. **早過大眾**：alert 觸發日，該股未上 WSB／ApeWisdom top 50
4. **運行成本** ≤ US$15/月；每日運行 ≤ 15 分鐘；零運維（GitHub Actions ＋ Supabase）

---

## 2. 核心概念定義

| 術語 | 定義 |
|---|---|
| **Mention** | 一個 post/comment/文章對一隻 ticker 或品牌嘅一次有效提及（經消歧義後） |
| **Source Tier** | `leading`（細眾專業源，信號來源）/ `lagging`(WSB 等大眾源，做排除條件) / `action`(SEC 檔案等行動信號) |
| **Velocity z-score** | 今日加權提及量相對該 ticker 自身 30 日滾動基線嘅標準差偏離 |
| **Novelty** | ticker 喺監察範圍內首次（或近乎首次）被多個獨立作者提及 |
| **Author reputation** | 作者信譽分 0–1，由帳號年齡、發文質量、歷史準確度組成 |
| **Manipulation risk** | 操縱風險分 0–1，由新號集中度、文本相似度、價量先後次序組成；penny/OTC 股有基礎分 |
| **Materiality**（產品線） | 爆紅產品佔母公司收入嘅比重估算，決定產品 buzz 對股價嘅傳導力 |

---

## 3. 功能需求（FR）

### FR-1 資料擷取（Ingestion）

| # | 需求 | 驗收標準 |
|---|---|---|
| FR-1.1 | 從 Reddit API 擷取指定 subreddits 嘅 new + hot posts 同 top-level comments | 每日兩次運行各 subreddit 遺漏率 <5%（對照人手抽查） |
| FR-1.2 | 從 RSS feeds（Substack、Seeking Alpha、blog）擷取新文章全文 | feed 有更新後下次運行必然攞到 |
| FR-1.3 | 從 ApeWisdom API 攞每日 Reddit mention 排行榜（做基線熱啟動＋lagging 對照） | 每日一次成功寫入 |
| FR-1.4 | 所有源由 `config/sources.yaml` 定義（kind、url、tier、enabled），加減源唔使改 code | 新增一行 YAML 即生效 |
| FR-1.5 | 去重：同一 post 重複擷取唔會重複入庫 | `(source, external_id)` 唯一約束 |
| FR-1.6 | 單一源失敗唔影響其他源；失敗記入 run log，連續 3 日失敗先告警 | 模擬源故障，其餘源正常完成 |
| FR-1.7 | Raw 內容（title、body、author、時間、engagement 指標）全量落庫，永久保留 | 回測層可重放任何歷史日 |

### FR-2 Ticker 抽取與消歧義

| # | 需求 | 驗收標準 |
|---|---|---|
| FR-2.1 | Cashtag（`$TSLA`）直接匹配，最高可信度 | precision ≥ 99% |
| FR-2.2 | 大寫字匹配必須對照 ticker universe（美股：NASDAQ/NYSE/AMEX＋OTC 官方名單，每週更新）＋常用英文字 blacklist | — |
| FR-2.3 | 模糊 case（短 ticker、一詞多義）batch 送 LLM（Haiku）做上下文判別 | 綜合 precision ≥ 95%（人手抽查 100 條） |
| FR-2.4 | 公司名→ticker 對應（專業文章多數淨寫公司名） | 常見公司名覆蓋 |
| FR-2.5 | 每條 mention 記錄抽取方法（cashtag/exact/llm）同 confidence | 可按方法過濾分析 |

### FR-3 品牌／產品抽取（Product Buzz Radar，Phase 2.5）

| # | 需求 | 驗收標準 |
|---|---|---|
| FR-3.1 | 喺產品類 subreddits 用 LLM 抽取品牌／產品名（NER） | — |
| FR-3.2 | Entity resolution：品牌→母公司→係咪美股上市→ticker | 對應錯誤率 <5% |
| FR-3.3 | Materiality 檢查：LLM＋財報數據估算產品佔母公司收入比重，低於閾值（預設 10%）過濾 | digest 只出 material 嘅 |
| FR-3.4 | Google Trends 二次驗證：品牌搜尋量加速先入 digest | — |

### FR-4 評分引擎（詳細規格見 §5）

| # | 需求 | 驗收標準 |
|---|---|---|
| FR-4.1 | 每日對每隻有 mention 嘅 ticker 計算綜合分 | 全量 <2 分鐘 |
| FR-4.2 | 分數可完全拆解（每個分項獨立入庫） | digest 顯示拆解 |
| FR-4.3 | 權重同閾值全部喺 `config/scoring.yaml`，改 config 唔使改 code | — |
| FR-4.4 | 每日最多輸出 N 個 alert（預設 10），按分排序 | — |

### FR-5 反操縱層（Phase 3）

| # | 需求 | 驗收標準 |
|---|---|---|
| FR-5.1 | 新帳號集中度：講該股嘅作者入面帳號年齡 <90 日嘅比例 | — |
| FR-5.2 | 文本相似度：同一 ticker 當日 posts 嘅 MinHash 相似度檢測 copy-paste | — |
| FR-5.3 | 價量先後：對比討論起飛日同價量異動日先後次序；價量先行→標記「追落後」 | — |
| FR-5.4 | Penny/OTC 基礎風險：股價 <$1 或 OTC 掛牌自動加操縱風險基礎分（預設 +0.2） | — |
| FR-5.5 | 操縱風險分不作靜默過濾，於 digest 明確標示（Low/Med/High） | High risk 有醒目警示 |

### FR-6 LLM 故事總結

| # | 需求 | 驗收標準 |
|---|---|---|
| FR-6.1 | 每個 alert，攞該 ticker 當日＋近 7 日 top posts（≤8k tokens）送 Claude 總結 | — |
| FR-6.2 | 輸出結構化 JSON：`thesis`（牛方論點）、`catalyst`（催化劑＋時間表）、`bear_case`（反方觀點）、`risks`、`who_is_talking`（邊類人喺度講）、`manipulation_notes` | 全欄位必填 |
| FR-6.3 | 成本護欄：每次運行 LLM 開支硬上限（預設 US$1），超出即跳過剩餘總結並記 log | 唔會爆 budget |
| FR-6.4 | 總結必附原文連結（最多 5 條），聲明「非投資建議」 | — |

### FR-7 Daily Digest 輸出（Slack）

| # | 需求 | 驗收標準 |
|---|---|---|
| FR-7.1 | 推送到指定 Slack 頻道（Incoming Webhook 或 Bot token＋`chat.postMessage`，用 Block Kit 排版）；markdown 檔案同步 commit 入 repo `digests/` 做存檔 | 兩通道內容一致 |
| FR-7.2 | 格式見 §6；每隻候選一個獨立 Slack message（方便逐隻 react） | — |
| FR-7.3 | 冇合格候選嗰日照發「今日無發現」（證明系統有運行） | — |
| FR-7.4 | 股票討論信號同產品 buzz 信號分開兩欄 | — |

### FR-8 回測與反饋（Phase 4；反饋機制 M1 已有）

| # | 需求 | 驗收標準 |
|---|---|---|
| FR-8.1 | 每日收市後補錄所有 alert 股票嘅價格 | prices 表無缺日 |
| FR-8.2 | 回測報告：alert 後 5/20/60 交易日絕對回報＋相對 SPY 超額回報，按月匯總 | 一條命令生成 |
| FR-8.3 | 用戶喺 Slack 對 alert message 用 👍/👎 emoji react；下次運行用 `reactions.get` 讀返上批 digest messages 嘅 reactions，記入 alerts 表 | 標記率統計 |
| FR-8.4 | 權重調參：用歷史數據 grid search 評分權重，報告不同權重下嘅命中率 | — |

---

## 4. 非功能需求（NFR)

| # | 需求 |
|---|---|
| NFR-1 | **冪等**：同一日重跑唔會產生重複數據或重複 digest |
| NFR-2 | **零運維**：GitHub Actions schedule 運行（每日兩次）；資料庫用 Supabase（託管 Postgres），無本地狀態 |
| NFR-3 | **成本上限**：總成本 ≤ US$15/月；LLM 每次運行 ≤ US$1；Supabase 用 free tier（500MB DB），接近上限時告警 |
| NFR-4 | **運行時間** ≤ 15 分鐘／次 |
| NFR-5 | **可觀測**：每次運行寫 `runs` 表（起止時間、各源擷取量、LLM 開支、錯誤）；連續失敗 Slack 告警 |
| NFR-6 | **Secrets**：全部行 GitHub Secrets（Reddit API key、Claude API key、Slack bot token、Supabase connection string），repo 內零明文 |
| NFR-7 | **合規**：只用官方 API 同公開 RSS；遵守各 API ToS；digest 唔公開轉發 |

---

## 5. 評分規格（v1 預設值，全部可喺 config 調）

### 5.1 前置過濾（唔滿足直接出局）

```yaml
prefilter:
  market: US                       # v1 淨做美股
  market_cap_min: 0                # 唔設下限（包 micro caps）
  market_cap_max: null             # 唔設上限（用戶決定）；「大眾未知」靠 mainstream_penalty 處理
  price_min: 0                     # 包 penny stocks
  exclude_otc: false               # 包埋 OTC
  avg_dollar_volume_min: 100_000   # 唯一硬過濾：完全冇成交嘅殭屍股先剔走
```

注意：放開晒市值／價格限制之後，「大眾未知」同「垃圾股」嘅把關責任
轉移到 `mainstream_penalty`（排除已爆紅）同 `manipulation_risk`（penny/OTC 基礎分 +0.2）兩個分項。

### 5.2 綜合分

```
score = 3.0 · min(velocity_z, 10)     # 相對自身 30 日基線嘅 z-score，封頂 10
      + 3.0 · novelty                 # 首次被 ≥3 個獨立作者提及＝1，否則 0
      + 2.0 · cross_source            # 今日有提及嘅獨立 leading 源數（封頂 5）
      + 2.0 · author_quality          # 加權平均作者信譽 0–1
      + 4.0 · action_signal           # SEC 行動信號（13D/Form 4 群聚）0–1
      − 5.0 · mainstream_flag         # 已上 WSB 熱榜／ApeWisdom top 50＝1
      − 4.0 · manipulation_risk       # 0–1（penny/OTC 基礎 0.2 起步）

alert_threshold: 8.0
max_alerts_per_day: 10
```

### 5.3 基線規則

- 每 (ticker, tier) 維護 30 日滾動 mean/std（加權提及量：每條 mention × 作者信譽）
- 歷史 <5 日嘅 ticker 行 novelty 路徑，唔計 z-score
- 基線熱啟動：首次部署用 ApeWisdom 歷史數據回填 30 日

### 5.4 作者信譽分 v1

```
reputation = 0.3 · min(account_age_years / 3, 1)
           + 0.3 · post_quality        # 平均 post 長度／有冇數據佐證（LLM 抽樣評分）
           + 0.4 · track_record        # 歷史提及股票嘅 20 日超額回報命中率（冷啟動時取 0.5）
```

---

## 6. Digest 格式規格（Slack Block Kit）

每次運行發一個 header message，然後每隻候選一個獨立 message（方便逐隻 👍/👎 react）：

```
📡 Stock Scout Daily — 2026-07-08 盤前
掃描：12 subreddits · 31 RSS feeds · EDGAR ｜ 發現 3 個候選
─────────────────────────────
🎯 #1  $XYZ — XYZ Corp（半導體設備 · 市值 $1.2B）
分數 14.2 ｜ 操縱風險：🟢 Low
▸ 觸發：r/SecurityAnalysis 3 篇深度帖（30日來首次）；
  兩位高信譽作者；Form 4 顯示 CFO 上週買入 $200k
▸ 故事：〔LLM 總結：論點／催化劑＋時間表／反方觀點／風險〕
▸ 邊個喺度講：value 型作者為主，平均帳齡 4.2 年
▸ 原文：[link1] [link2] [link3]
   （👍 值得研究 / 👎 冇用 —— react 呢個 message）
─────────────────────────────
🛍️ 產品 Buzz
#2 Brand ABC（母公司 $DEF，產品佔收入 ~35%）
▸ r/running 提及 30 日 +420%；Google Trends 同步加速
─────────────────────────────
⚠️ 本 digest 為研究線索，非投資建議。
```

Penny/OTC 候選額外顯示：`⚠️ Penny/OTC — 操縱風險基礎分已計入，注意流動性`。

---

## 7. 系統架構

### 7.1 數據流

```
[GitHub Actions cron: 每日兩次 — 美股盤前 12:00 UTC ＋ 收市後 21:30 UTC]
        │
        ▼
feedback（讀上批 Slack digest messages 嘅 👍/👎 reactions → alerts 表）
        ▼
ingest（reddit / rss / apewisdom / edgar*）── raw posts ──▶ Supabase (Postgres)
        ▼
extract（ticker + brand*）── mentions ──▶ Supabase
        ▼
enrich（yfinance 價量市值；materiality*）
        ▼
score（velocity / novelty / cross-source / author / manipulation*）
        ▼
summarize（Claude：每 alert 一個故事 JSON）
        ▼
report（Slack Block Kit push ＋ digests/YYYY-MM-DD.md commit）
                                          （* = Phase 2+）
```

### 7.2 目錄結構

```
stock_scout/
├── SPEC.md / PLAN.md / README.md
├── pyproject.toml
├── config/
│   ├── sources.yaml        # 所有源：kind, url, tier, enabled
│   └── scoring.yaml        # 權重、閾值、前置過濾
├── src/stock_scout/
│   ├── cli.py              # run / backtest / report 子命令
│   ├── db/                 # schema.sql (Postgres), repo.py
│   ├── ingest/             # base.py, reddit.py, rss.py, apewisdom.py, edgar.py
│   ├── extract/            # universe.py, tickers.py, brands.py
│   ├── enrich/             # market_data.py, materiality.py
│   ├── score/              # velocity.py, novelty.py, author.py, manipulation.py, composite.py
│   ├── summarize/          # story.py, prompts.py, budget.py
│   └── report/             # digest.py, slack.py, feedback.py
├── digests/                # 每日 digest markdown 存檔
├── tests/
└── .github/workflows/daily.yml
```

### 7.3 數據模型（Supabase / Postgres）

```sql
sources(id, kind, name, url, tier, enabled)
authors(id, source_kind, handle, account_created_at, first_seen,
        reputation, UNIQUE(source_kind, handle))
posts(id, source_id→sources, external_id, url, title, body,
      author_id→authors, posted_at, fetched_at, upvotes, num_comments,
      UNIQUE(source_id, external_id))
tickers(symbol PK, name, exchange, sector, market_cap, is_otc, first_seen)
mentions(id, post_id→posts, symbol→tickers, method, confidence)
brands(id, name, parent_company, symbol→tickers NULL, is_public,
       materiality_pct, resolved_at)
brand_mentions(id, post_id→posts, brand_id→brands, confidence)
daily_stats(date, symbol, tier, mention_count, unique_authors,
            weighted_mentions, velocity_z, PK(date, symbol, tier))
prices(date, symbol, close, volume, market_cap, PK(date, symbol))
alerts(id, date, symbol, brand_id NULL, score, components_json,
       manipulation_risk, story_json, slack_message_ts,
       feedback NULL, created_at)
runs(id, started_at, finished_at, status, stats_json, llm_cost_usd)
```

註：`alerts.slack_message_ts` 記低每個 alert 嘅 Slack message timestamp，
下次運行用嚟讀 reactions（FR-8.3）。

Supabase 附帶好處：用戶可經 Supabase MCP connector 直接同 Claude 對話查庫
（「上個月邊個作者命中率最高?」），唔使自己寫 dashboard——M5 嘅需求一部分已經免費解決。

---

## 8. 技術選型

| 部件 | 選擇 | 備註 |
|---|---|---|
| 語言 | Python 3.12＋uv | |
| Reddit | PRAW（官方 API 免費層） | 100 req/min 夠用 |
| RSS | feedparser + trafilatura（全文抽取） | |
| 行情 | yfinance | 市值、價量、回測數據 |
| SEC | edgartools 或直接 EDGAR full-text API | 免費 |
| DB | **Supabase**（託管 Postgres，free tier 起步） | psycopg 直連；用戶有 MCP connector 可對話式查庫 |
| LLM | claude-haiku（消歧義）＋ claude-sonnet（故事總結） | budget.py 統一計費護欄 |
| 排程 | GitHub Actions schedule（每日兩次） | 無狀態 runner，狀態全在 Supabase |
| 通知 | **Slack**：Bot token＋`chat.postMessage`（Block Kit）；`reactions.get` 讀反饋 | Webhook 唔支持讀 reactions，所以用 bot token |
| 測試 | pytest；抽取層有 golden-file 測試集 | |

---

## 9. 里程碑與驗收

### M0 — 骨架（~2 日）
Repo scaffolding、pyproject、config 載入、Supabase schema migration、CLI 骨架、CI（lint+test）。
**驗收**：`stock-scout run --dry-run` 走通全流程（假數據）；schema 成功 apply 到 Supabase。

### M1 — Reddit MVP（~2 週）🎯 最重要里程碑
FR-1.1/1.3–1.7、FR-2、FR-4、FR-5.4、FR-6、FR-7、FR-8.3（reactions 反饋）、NFR 全部。
sources.yaml 首發名單：
- leading：r/SecurityAnalysis, r/valueinvesting, r/UndervaluedStonks, r/Vitards, r/pennystocks, r/Biotechplays, r/SPACs, r/Shortsqueeze(反指標參考)
- lagging：r/wallstreetbets, r/stocks, r/investing

**驗收**：連續 5 日自動運行成功；digest 準時到 Slack 頻道；👍/👎 反饋成功寫返入庫；
100 條 mention 人手抽查 precision ≥95%；單次運行 <15 分鐘、LLM 開支 <US$1。

### M2 — 行動信號＋擴源（~1 週）
EDGAR 13D/13G＋Form 4 群聚買入（`action_signal` 分項生效）；
Substack RSS（curate 20+ 作者）；Seeking Alpha RSS；FR-1.2。
**驗收**：action 信號出現喺分數拆解；跨源擴散分生效。

### M2.5 — Product Buzz Radar（~1.5 週）
FR-3 全部；產品類 subreddits＋Google Trends 驗證；digest 產品欄。
**驗收**：品牌→ticker 對應抽查錯誤率 <5%；materiality 過濾生效。

### M3 — 質量層（~1 週）
FR-5 反操縱全套；作者信譽 track_record 開始用真數據計。
**驗收**：已知 pump 案例（歷史數據回放）被標 High risk。

### M4 — 回測（~1 週）
FR-8 全部。
**驗收**：一條命令出月度回測報告；權重 grid search 報告。

### M5 —（可選）Dashboard
Supabase connector 已覆蓋對話式查庫；如仍需視覺化，起簡單 web UI：
alert 歷史、ticker 趨勢圖、作者排行榜。

---

## 10. 風險與緩解

| 風險 | 影響 | 緩解 |
|---|---|---|
| Reddit API 政策再收緊 | 主源斷供 | Raw data 已落庫；ApeWisdom 做後備；架構上源可插拔 |
| Ticker 抽取噪音失控 | Digest 全是垃圾 | Golden-file 測試集＋LLM 判別＋confidence 分級 |
| 被 pump 局污染（包 penny/OTC 後風險更高） | 用戶接火棒 | FR-5 全套＋penny/OTC 基礎風險分＋風險標示唔靜默過濾＋digest 免責聲明 |
| 信號其實冇 alpha | 白做 | M4 回測係一級公民；由 day 1 儲全量數據 |
| Supabase free tier 500MB 用爆 | 寫入失敗 | runs 表監察 DB 大小；posts.body 可壓縮／歸檔；必要時升 Pro（US$25/月，超 NFR-3 要用戶批准） |
| LLM 成本失控 | 超支 | budget.py 硬上限；Haiku 做量大工序 |

---

## 11. 合規注意

- 只用官方 API 同公開 RSS；唔爬 X、唔爬需要登入嘅內容
- 純個人研究用途；**唔接自動交易**
- Digest 內容唔好公開轉發（Reddit API 條款對再分發有限制）

---

## 12. 已決事項（用戶拍板記錄，2026-07-07）

| # | 問題 | 決定 |
|---|---|---|
| Q1 | 市場範圍 | **v1 淨做美股**；港股／台股後期再議 |
| Q2 | 通知通道 | **Slack 頻道**（Bot token＋Block Kit；reactions 做反饋） |
| Q3 | 每日運行次數 | **兩次**（美股盤前＋收市後） |
| Q4 | 市值上限 | **唔設上限**；「大眾未知」靠 mainstream_penalty 把關 |
| Q5 | Penny stocks | **包埋**（連 OTC）；penny/OTC 自動加操縱風險基礎分 +0.2 |
| — | 資料庫 | **Supabase**（託管 Postgres；用戶有 MCP connector 可對話式查庫） |
