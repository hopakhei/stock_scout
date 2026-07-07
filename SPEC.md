# Stock Scout — 產品規格書（Product Spec）v1.0

> 一句話定位：一個每日自動運行嘅偵測哨兵，喺「大眾未知、但已有一小群專業人士討論／行動」嘅階段
> 發現潛力股同爆紅產品，並用 LLM 總結背後嘅故事，以 daily digest 形式送到用戶手上。
>
> 相關文件：[PLAN.md](PLAN.md)（背景分析、盲點修正、數據源 brainstorm——本 spec 嘅決策依據）

---

## 1. 產品概述

### 1.1 定位

- **係乜**：idea discovery 研究助手。輸出係「呢隻股值得你今晚花 30 分鐘研究」嘅高質候選名單＋故事總結
- **唔係乜**（non-goals）：
  - ❌ 唔係交易信號，唔接自動交易
  - ❌ 唔係 real-time 系統——每日 batch 1–2 次
  - ❌ 唔係大眾情緒儀表板（嗰啲已經有 ApeWisdom／SwaggyStocks）
  - ❌ 唔做多用戶 SaaS——單用戶個人工具

### 1.2 用戶與場景

單一用戶。每日收到 digest（Telegram 首選），5 分鐘內判斷邊隻值得深入研究；
每隻候選附原文連結，方便自行驗證。用戶可對 alert 作出標記（有用／冇用），餵返俾回測層。

### 1.3 成功標準

1. **有用率**：用戶主觀認為「值得研究」嘅 alert 比例 ≥ 30%
2. **領先性**（回測驗證）：alert 後 20 個交易日，候選股相對 SPY 嘅超額回報中位數 > 0
3. **早過大眾**：alert 觸發日，該股未上 WSB／ApeWisdom top 50
4. **運行成本** ≤ US$15/月；每日運行 ≤ 15 分鐘；零運維（GitHub Actions）

---

## 2. 核心概念定義

| 術語 | 定義 |
|---|---|
| **Mention** | 一個 post/comment/文章對一隻 ticker 或品牌嘅一次有效提及（經消歧義後） |
| **Source Tier** | `leading`（細眾專業源，信號來源）/ `lagging`(WSB 等大眾源，做排除條件) / `action`(SEC 檔案等行動信號) |
| **Velocity z-score** | 今日加權提及量相對該 ticker 自身 30 日滾動基線嘅標準差偏離 |
| **Novelty** | ticker 喺監察範圍內首次（或近乎首次）被多個獨立作者提及 |
| **Author reputation** | 作者信譽分 0–1，由帳號年齡、發文質量、歷史準確度組成 |
| **Manipulation risk** | 操縱風險分 0–1，由新號集中度、文本相似度、價量先後次序組成 |
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
| FR-2.2 | 大寫字匹配必須對照 ticker universe（NASDAQ/NYSE/AMEX 官方名單，每週更新）＋常用英文字 blacklist | — |
| FR-2.3 | 模糊 case（短 ticker、一詞多義）batch 送 LLM（Haiku）做上下文判別 | 綜合 precision ≥ 95%（人手抽查 100 條） |
| FR-2.4 | 公司名→ticker 對應（專業文章多數淨寫公司名） | 常見公司名覆蓋 |
| FR-2.5 | 每條 mention 記錄抽取方法（cashtag/exact/llm）同 confidence | 可按方法過濾分析 |

### FR-3 品牌／產品抽取（Product Buzz Radar，Phase 2.5）

| # | 需求 | 驗收標準 |
|---|---|---|
| FR-3.1 | 喺產品類 subreddits 用 LLM 抽取品牌／產品名（NER） | — |
| FR-3.2 | Entity resolution：品牌→母公司→係咪上市→ticker | 對應錯誤率 <5% |
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
| FR-5.4 | 操縱風險分不作靜默過濾，於 digest 明確標示（Low/Med/High） | High risk 有醒目警示 |

### FR-6 LLM 故事總結

| # | 需求 | 驗收標準 |
|---|---|---|
| FR-6.1 | 每個 alert，攞該 ticker 當日＋近 7 日 top posts（≤8k tokens）送 Claude 總結 | — |
| FR-6.2 | 輸出結構化 JSON：`thesis`（牛方論點）、`catalyst`（催化劑＋時間表）、`bear_case`（反方觀點）、`risks`、`who_is_talking`（邊類人喺度講）、`manipulation_notes` | 全欄位必填 |
| FR-6.3 | 成本護欄：每次運行 LLM 開支硬上限（預設 US$1），超出即跳過剩餘總結並記 log | 唔會爆 budget |
| FR-6.4 | 總結必附原文連結（最多 5 條），聲明「非投資建議」 | — |

### FR-7 Daily Digest 輸出

| # | 需求 | 驗收標準 |
|---|---|---|
| FR-7.1 | Telegram bot 推送（首選通道）；markdown 檔案同步 commit 入 repo `digests/` 做存檔 | 兩通道內容一致 |
| FR-7.2 | 格式見 §6；每隻候選一個卡片 | — |
| FR-7.3 | 冇合格候選嗰日照發「今日無發現」（證明系統有運行） | — |
| FR-7.4 | 股票討論信號同產品 buzz 信號分開兩欄 | — |

### FR-8 回測與反饋（Phase 4）

| # | 需求 | 驗收標準 |
|---|---|---|
| FR-8.1 | 每日收市後補錄所有 alert 股票嘅價格 | prices 表無缺日 |
| FR-8.2 | 回測報告：alert 後 5/20/60 交易日絕對回報＋相對 SPY 超額回報，按月匯總 | 一條命令生成 |
| FR-8.3 | 用戶可透過 Telegram 回覆對 alert 標記 👍/👎，記入 alerts 表 | 標記率統計 |
| FR-8.4 | 權重調參：用歷史數據 grid search 評分權重，報告不同權重下嘅命中率 | — |

---

## 4. 非功能需求（NFR)

| # | 需求 |
|---|---|
| NFR-1 | **冪等**：同一日重跑唔會產生重複數據或重複 digest |
| NFR-2 | **零運維**：GitHub Actions schedule 運行；SQLite 檔案用 Actions cache／artifact 持久化，每週備份 commit 入 repo |
| NFR-3 | **成本上限**：總成本 ≤ US$15/月；LLM 每次運行 ≤ US$1 |
| NFR-4 | **運行時間** ≤ 15 分鐘／次 |
| NFR-5 | **可觀測**：每次運行寫 `runs` 表（起止時間、各源擷取量、LLM 開支、錯誤）；連續失敗 Telegram 告警 |
| NFR-6 | **Secrets**：全部行 GitHub Secrets（Reddit API key、Claude API key、Telegram token），repo 內零明文 |
| NFR-7 | **合規**：只用官方 API 同公開 RSS；遵守各 API ToS；digest 唔公開轉發 |

---

## 5. 評分規格（v1 預設值，全部可喺 config 調）

### 5.1 前置過濾（唔滿足直接出局）

```yaml
prefilter:
  market_cap_min: 50_000_000      # 避開流動性陷阱
  market_cap_max: 10_000_000_000  # 大過呢個唔會係「大眾未知」
  price_min: 1.0                  # 避開仙股
  avg_dollar_volume_min: 1_000_000
  exclude_otc: true
```

### 5.2 綜合分

```
score = 3.0 · min(velocity_z, 10)     # 相對自身 30 日基線嘅 z-score，封頂 10
      + 3.0 · novelty                 # 首次被 ≥3 個獨立作者提及＝1，否則 0
      + 2.0 · cross_source            # 今日有提及嘅獨立 leading 源數（封頂 5）
      + 2.0 · author_quality          # 加權平均作者信譽 0–1
      + 4.0 · action_signal           # SEC 行動信號（13D/Form 4 群聚）0–1
      − 5.0 · mainstream_flag         # 已上 WSB 熱榜／ApeWisdom top 50＝1
      − 4.0 · manipulation_risk       # 0–1

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

## 6. Digest 格式規格

```markdown
📡 Stock Scout Daily — 2026-07-08
掃描：12 subreddits · 31 RSS feeds · EDGAR | 發現 3 個候選

━━━━━━━━━━━━━━━━━━━━
🎯 #1  $XYZ — XYZ Corp（半導體設備 · 市值 $1.2B）
分數 14.2 ｜ 操縱風險：🟢 Low
▸ 觸發：r/SecurityAnalysis 3 篇深度帖（30日來首次）；
  兩位高信譽作者；Form 4 顯示 CFO 上週買入 $200k
▸ 故事：〔LLM 總結：論點／催化劑＋時間表／反方觀點／風險〕
▸ 邊個喺度講：value 型作者為主，平均帳齡 4.2 年
▸ 原文：[link1] [link2] [link3]
━━━━━━━━━━━━━━━━━━━━
🛍️ 產品 Buzz
#2 Brand ABC（母公司 $DEF，產品佔收入 ~35%）
▸ r/running 提及 30 日 +420%；Google Trends 同步加速
▸ …
━━━━━━━━━━━━━━━━━━━━
⚠️ 本 digest 為研究線索，非投資建議。
👍/👎 回覆數字可標記候選質素。
```

---

## 7. 系統架構

### 7.1 數據流

```
[GitHub Actions cron: 每日 13:00 & 21:00 UTC]
        │
        ▼
ingest（reddit / rss / apewisdom / edgar*）── raw posts ──▶ SQLite
        ▼
extract（ticker + brand*）── mentions ──▶ SQLite
        ▼
enrich（yfinance 價量市值；materiality*）
        ▼
score（velocity / novelty / cross-source / author / manipulation*）
        ▼
summarize（Claude：每 alert 一個故事 JSON）
        ▼
report（Telegram push ＋ digests/YYYY-MM-DD.md commit）
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
│   ├── db/                 # schema.sql, repo.py
│   ├── ingest/             # base.py, reddit.py, rss.py, apewisdom.py, edgar.py
│   ├── extract/            # universe.py, tickers.py, brands.py
│   ├── enrich/             # market_data.py, materiality.py
│   ├── score/              # velocity.py, novelty.py, author.py, manipulation.py, composite.py
│   ├── summarize/          # story.py, prompts.py, budget.py
│   └── report/             # digest.py, telegram.py
├── digests/                # 每日 digest markdown 存檔
├── tests/
└── .github/workflows/daily.yml
```

### 7.3 數據模型（SQLite）

```sql
sources(id, kind, name, url, tier, enabled)
authors(id, source_kind, handle, account_created_at, first_seen,
        reputation, UNIQUE(source_kind, handle))
posts(id, source_id→sources, external_id, url, title, body,
      author_id→authors, posted_at, fetched_at, upvotes, num_comments,
      UNIQUE(source_id, external_id))
tickers(symbol PK, name, exchange, sector, market_cap, first_seen)
mentions(id, post_id→posts, symbol→tickers, method, confidence)
brands(id, name, parent_company, symbol→tickers NULL, is_public,
       materiality_pct, resolved_at)
brand_mentions(id, post_id→posts, brand_id→brands, confidence)
daily_stats(date, symbol, tier, mention_count, unique_authors,
            weighted_mentions, velocity_z, PK(date, symbol, tier))
prices(date, symbol, close, volume, market_cap, PK(date, symbol))
alerts(id, date, symbol, brand_id NULL, score, components_json,
       manipulation_risk, story_json, feedback NULL, created_at)
runs(id, started_at, finished_at, status, stats_json, llm_cost_usd)
```

---

## 8. 技術選型

| 部件 | 選擇 | 備註 |
|---|---|---|
| 語言 | Python 3.12＋uv | |
| Reddit | PRAW（官方 API 免費層） | 100 req/min 夠用 |
| RSS | feedparser + trafilatura（全文抽取） | |
| 行情 | yfinance | 市值、價量、回測數據 |
| SEC | edgartools 或直接 EDGAR full-text API | 免費 |
| DB | SQLite（WAL mode） | 單用戶零運維；需要先升 Postgres |
| LLM | claude-haiku（消歧義）＋ claude-sonnet（故事總結） | budget.py 統一計費護欄 |
| 排程 | GitHub Actions schedule | DB 用 actions/cache 持久化＋每週 commit 備份 |
| 通知 | python-telegram-bot | 免費、手機直達、支持 👍/👎 反饋 |
| 測試 | pytest；抽取層有 golden-file 測試集 | |

---

## 9. 里程碑與驗收

### M0 — 骨架（~2 日）
Repo scaffolding、pyproject、config 載入、DB schema、CLI 骨架、CI（lint+test）。
**驗收**：`stock-scout run --dry-run` 走通全流程（假數據）。

### M1 — Reddit MVP（~2 週）🎯 最重要里程碑
FR-1.1/1.3–1.7、FR-2、FR-4、FR-6、FR-7、NFR 全部。
sources.yaml 首發名單：
- leading：r/SecurityAnalysis, r/valueinvesting, r/UndervaluedStonks, r/Vitards, r/pennystocks(高風險組), r/Biotechplays, r/SPACs, r/Shortsqueeze(反指標參考)
- lagging：r/wallstreetbets, r/stocks, r/investing

**驗收**：連續 5 日自動運行成功；digest 準時到 Telegram；100 條 mention 人手抽查 precision ≥95%；單次運行 <15 分鐘、LLM 開支 <US$1。

### M2 — 行動信號＋擴源（~1 週）
EDGAR 13D/13G＋Form 4 群聚買入（`action_signal` 分項生效）；
Substack RSS（curate 20+ 作者）；Seeking Alpha RSS；FR-1.2。
**驗收**：action 信號出現喺分數拆解；跨源擴散分生效。

### M2.5 — Product Buzz Radar（~1.5 週）
FR-3 全部；產品類 subreddits＋Google Trends 驗證；digest 產品欄。
**驗收**：品牌→ticker 對應抽查錯誤率 <5%；materiality 過濾生效。

### M3 — 質量層（~1 週）
FR-5 反操縱三件套；作者信譽 track_record 開始用真數據計。
**驗收**：已知 pump 案例（歷史數據回放）被標 High risk。

### M4 — 回測（~1 週）
FR-8 全部。
**驗收**：一條命令出月度回測報告；權重 grid search 報告。

### M5 —（可選）Dashboard
簡單 web UI：alert 歷史、ticker 趨勢圖、作者排行榜。

---

## 10. 風險與緩解

| 風險 | 影響 | 緩解 |
|---|---|---|
| Reddit API 政策再收緊 | 主源斷供 | Raw data 已落庫；ApeWisdom 做後備；架構上源可插拔 |
| Ticker 抽取噪音失控 | Digest 全是垃圾 | Golden-file 測試集＋LLM 判別＋confidence 分級 |
| 被 pump 局污染 | 用戶接火棒 | FR-5 三件套＋風險標示唔靜默過濾＋digest 免責聲明 |
| 信號其實冇 alpha | 白做 | M4 回測係一級公民；由 day 1 儲全量數據 |
| GitHub Actions cache 丟 DB | 歷史斷檔 | 每週 DB 備份 commit；digest markdown 本身係二級存檔 |
| LLM 成本失控 | 超支 | budget.py 硬上限；Haiku 做量大工序 |

---

## 11. 未決事項（需用戶拍板）

| # | 問題 | 預設方案 |
|---|---|---|
| Q1 | 市場範圍：淨做美股，定加埋港股／台股？ | v1 淨做美股（數據源同 universe 最齊），港股 Phase 5 再議 |
| Q2 | 通知通道：Telegram 定 email？ | Telegram（支持互動反饋） |
| Q3 | 每日運行幾多次？ | 兩次（美股盤前 + 收市後） |
| Q4 | 市值上限 $10B 啱唔啱？ | 可 config 調；v1 用 $10B |
| Q5 | 要唔要包 r/pennystocks 呢類高風險源？ | 包，但該源 mention 自動加操縱風險基礎分 |
