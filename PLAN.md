# Stock Scout — 股票爆紅偵測哨兵：計劃書

> 目標：偵測「大眾未知、但已有一小群專業人士討論緊」嘅潛力股，
> 監察各大論壇嘅提及頻率（frequency），並自動總結背後嘅原因同故事。

---

## 一、原構想嘅盲點同修正

喺寫計劃之前，先講清楚幾個原構想入面要修正嘅地方——呢啲直接影響成個系統設計。

### 1. WallStreetBets 係「落後指標」，唔係「領先指標」（最重要嘅一點）

原構想話要睇 WSB / r/stocks 嘅 frequency，但同時又話要搵「大眾未知」嘅股票——呢兩樣嘢係矛盾嘅。
一隻股票喺 WSB 高頻出現嗰陣，已經係「爆咗紅」，你係最後一批知嘅人。

**修正**：資料源要分兩層——

- **領先層（信號來源）**：細眾、專業嘅地方
  - Niche subreddits：r/SecurityAnalysis、r/valueinvesting、r/UndervaluedStonks、行業性 sub（r/uraniumsqueeze、r/shroomstocks 呢類）
  - Substack 專業作者（value / special situations / 行業研究）
  - FinTwit 上經人手篩選嘅專業帳號名單
  - 13F 檔案、內部人買入（SEC Form 4）——真正嘅「專業人士行動」
- **落後層（對照組）**：WSB、r/stocks、主流財經媒體
  - 用途唔係搵目標，而係做**排除條件**：一隻股票如果已經上咗 WSB 熱榜，就代表「大眾已知」，應該從候選名單剔走或降權。

### 2. 絕對 frequency 冇用，要睇「相對基線嘅加速度」

TSLA、NVDA 日日都係 mention 榜首。原始 frequency 只會俾你一張人人都知嘅名單。

**修正**：核心指標係——
- **Mention velocity z-score**：對比每隻 ticker 自己過去 30 日嘅滾動基線，今日提及量偏離幾多個標準差
- **Novelty**：呢隻 ticker 係咪喺監察範圍內「第一次／近乎第一次」出現
- **跨源擴散速度**：由 1 個源講緊，變成 3 個獨立源講緊，呢個擴散本身就係信號

### 3. 唔係「幾多人講」，係「邊個講」

「一小群專業人士討論緊」呢個定義，意味住必須追蹤**作者**，唔淨係計 post 數。
10 個有往績嘅專業作者，好過 1,000 個散戶跟風。

**修正**：建立作者信譽分（author reputation score）——
- 帳號年齡、歷史發文質量（post 長度、有冇附數據／估值分析）
- 歷史準確度（佢之前提過嘅股票，之後表現如何——呢個要儲數據先計到）
- Mention 計分時用作者信譽加權，而唔係一人一票

### 4. 你個偵測目標，同 Pump & Dump 嘅 profile 一模一樣（最大風險）

「細市值＋突然有人開始講＋大眾未知」——呢個正正係坐莊協同炒作（pump scheme）嘅標準劇本。
一個 naive 嘅 frequency detector 會變成幫人接火棒嘅工具。

**修正**：必須有反操縱過濾層——
- 新帳號集中度：講呢隻股嘅帳號係咪大部分都係近期註冊
- 文本相似度：post 之間係咪 copy-paste／模板化（bot 特徵）
- 價量先後次序：如果**股價成交量已經異動咗**討論先出現，係追落後；如果**討論先行**、價量未郁，先係我哋要嘅領先信號
- 每個 alert 都標明操縱風險分數，唔好靜靜地過濾咗算

### 5. Ticker 識別係成條 pipeline 最大嘅錯誤來源

「A」「IT」「ALL」「GO」「DD」「CEO」全部都係真 ticker。天真嘅大寫字匹配會產生海量垃圾。

**修正**：
- Cashtag（$TSLA）優先，可信度最高
- 大寫字匹配必須對照真實 ticker universe（NASDAQ/NYSE/AMEX 官方名單），再加常用英文字 blacklist
- 模糊情況交俾 LLM 做上下文判別（例如「DD」喺 WSB 通常係 due diligence 唔係 ticker）
- 公司名→ticker 嘅對應（好多專業文章淨係寫公司名，唔寫 ticker）

### 6. 資料取得嘅現實：X 好貴，Substack 冇 API

- **X/Twitter**：API 基本層每月 US$200 而且限制多，真正嘅 firehose 係天價；爬蟲違反 ToS。**建議第一版直接放棄 X**，後期先用「人手篩選帳號名單＋API 基本層」補上
- **Reddit**：官方 API 免費層夠用（每分鐘 100 requests），係第一版嘅主力
- **Substack**：冇官方 API，但每個 publication 都有 RSS（`/feed`），要人手 curate 一張作者名單
- **現成聚合數據**：ApeWisdom（免費 Reddit mention API）、Quiver Quant 等可以直接攞嚟做基線對照，唔使自己由零爬——第一日就有 30 日基線
- **真正嘅專業人士其實好多喺 Discord / Telegram 私羣**——呢啲入唔到場，要接受呢個盲區

### 7. 冇回測，就唔知個信號有冇用

**修正**：由第一日開始，raw data 全部落庫（post 原文、時間、作者、當日價量）。
兩三個月後就可以答：「如果每次 alert 我都買入，持有 5／20／60 日，回報係點？」
冇呢一步，成個系統只係一個好睇嘅玩具。

### 8. 期望管理

學術研究對 Reddit/retail sentiment 嘅結論大致係：對細價股**短期**有一定預測力，但噪音極大、alpha 衰減快。
呢個工具嘅正確定位係 **idea discovery／研究助手**——幫你更早見到值得研究嘅名，
唔係一個可以直接跟買嘅交易信號，更加唔應該接自動交易。

### 9. 唔使 real-time，每日 batch 已經足夠

「爆紅」係以日計唔係以分鐘計嘅過程。每日跑 1–2 次 batch scan：
- 架構簡單十倍（一個 cron job，唔使 streaming infra）
- 成本近乎零（GitHub Actions 免費 schedule 已經夠）
- 你亦冇能力以分鐘級速度行動，real-time 係假需求

---

## 二、系統設計

```
┌─────────────── Ingestion（每日 1–2 次）───────────────┐
│  Reddit API (PRAW)   Substack RSS   ApeWisdom API      │
│  （後期：X curated list、Seeking Alpha RSS、SEC EDGAR）│
└──────────────────────────┬─────────────────────────────┘
                           ▼
              Ticker Extraction & Disambiguation
              （cashtag → universe match → LLM 判別）
                           ▼
                    Storage（SQLite）
        posts / mentions / tickers / authors / prices
                           ▼
                     Scoring Engine
   velocity z-score ＋ novelty ＋ 跨源擴散 ＋ 作者信譽加權
   － 已爆紅懲罰（WSB 熱榜）  － 操縱風險分  － 市值過濾
                           ▼
                  LLM Story Summarizer
     （攞 top posts 俾 Claude 總結：論點／催化劑／風險）
                           ▼
                    Daily Digest 輸出
          （Telegram bot 或 email，top 5–10 候選）
```

### 評分公式（初版，之後用回測調參）

```
score = w1 · velocity_zscore          # 相對自身基線嘅加速度
      + w2 · novelty_bonus            # 首次／近乎首次出現
      + w3 · cross_source_count       # 幾多個獨立源講緊
      + w4 · author_quality_avg       # 作者信譽加權平均
      − w5 · mainstream_penalty       # 已上 WSB 熱榜／主流媒體
      − w6 · manipulation_risk        # 反操縱風險分

前置過濾：市值 < US$10B（可調）、有真實成交量、非 OTC 垃圾股（可選）
```

### 每日 Digest 每隻候選股嘅格式

- Ticker、公司名、市值、行業
- 分數拆解（點解上榜：邊個源、邊啲作者、加速幾多）
- **LLM 總結嘅故事**：牛方論點、催化劑、時間表、主要風險、反方觀點
- 操縱風險警示
- 原文連結（俾你自己去驗證）

---

## 三、技術選型

| 部件 | 選擇 | 理由 |
|---|---|---|
| 語言 | Python 3.12 | 生態最齊（PRAW、feedparser、yfinance） |
| Reddit | PRAW + 官方免費 API | 免費層夠每日 batch 用 |
| RSS | feedparser | Substack / Seeking Alpha / blog 通用 |
| 行情 | yfinance | 免費攞市值、價量做過濾同回測 |
| 資料庫 | SQLite（單檔案） | 一人項目零運維；日後需要先升 Postgres |
| LLM | Claude API（Haiku 做判別、Sonnet 做總結） | 判別平、總結質量高；每日成本大約 US$0.1–0.5 |
| 排程 | GitHub Actions schedule | 免費、免伺服器；DB 檔案 commit 返 repo 或用 artifact |
| 通知 | Telegram bot（首選）或 email | Telegram 免費、即時、手機直達 |

---

## 四、分階段路線圖

### Phase 1 — Reddit MVP（目標：2–3 星期內每日收到 digest）
1. Ticker universe 載入（NASDAQ/NYSE/AMEX 名單＋blacklist）
2. Reddit ingestion：8–12 個 subreddit，分「領先層」同「對照層」
3. Ticker extraction（cashtag ＋ universe match；LLM 判別後補）
4. SQLite schema：posts / mentions / tickers / authors / daily_prices
5. 基線問題：用 ApeWisdom 歷史數據熱啟動 30 日基線
6. Scoring v1：velocity z-score ＋ novelty ＋ 市值過濾 ＋ WSB 懲罰
7. LLM 總結 ＋ Telegram digest
8. GitHub Actions 每日排程

### Phase 2 — 擴源
- Substack RSS（人手 curate 20–50 個專業作者）
- Seeking Alpha RSS、獨立 blog
- SEC EDGAR：Form 4 內部人買入、13F 新建倉（真·專業人士信號）
- 跨源擴散分數正式生效

### Phase 3 — 質量層
- 作者信譽分（開始有歷史數據可計）
- 反操縱過濾（新號集中度、文本相似度、價量先後）
- LLM ticker 判別全面接管模糊 case

### Phase 4 — 回測與調參
- Alert 回放：歷史 alert 嘅 5/20/60 日前瞻回報
- 用回測結果調整評分權重 w1–w6
- False positive 標註流程

### Phase 5 —（可選）體驗
- 簡單 web dashboard（趨勢圖、歷史 alert、作者排行榜)
- X curated list 接入（如果願意俾 API 錢）

---

## 五、成本估算（每月）

| 項目 | 成本 |
|---|---|
| Reddit API / RSS / yfinance / ApeWisdom | US$0 |
| Claude API（每日 digest） | ~US$3–15 |
| GitHub Actions | US$0（免費額度內） |
| Telegram bot | US$0 |
| **合計（Phase 1–4）** | **~US$3–15/月** |
| X API（Phase 5 先考慮） | +US$200/月 |

---

## 六、產品／服務爆紅偵測（Product Buzz Radar）

除咗直接偵測「股票討論」，仲有一類領先性更強嘅信號：**產品或服務本身突然爆紅**，
而討論嘅人根本冇諗過買股票。呢個係 Peter Lynch 式「buy what you know」嘅系統化版本，
對沖基金界叫 alternative data。

### 往績例子

| 產品 buzz | 股票 | 領先時間 |
|---|---|---|
| r/fitness／健身圈狂推 Celsius 能量飲品 | CELH | 約一年 |
| TikTok 美妝圈爆 e.l.f. | ELF | 數季 |
| r/running 口碑：Hoka／On Running | DECK / ONON | 約一年 |
| App Store 排行榜：Duolingo、Temu | DUOL / PDD | 一至兩季 |
| 社交媒體減肥話題：Ozempic | NVO | 數月 |

### 點解呢類信號更好

1. **領先時間更長**：buzz → 銷量 → 季度業績 → 股價，成條鏈以月／季計；
   論壇股票討論嘅領先時間通常只有幾日
2. **操縱風險大幅降低**：冇人會為咗炒股去護膚品 sub 做媒——
   直接繞過咗 pump & dump 問題（品牌 marketing astroturf 仍然存在，但性質唔同）
3. **共用現有引擎**：同一套 velocity z-score／novelty 邏輯，
   只係抽取對象由 ticker 變成品牌／產品名

### 新增嘅難點：品牌 → 股票對應層（entity resolution）

產品爆紅 ≠ 有得買。必須加一層對應同過濾：

```
品牌/產品名 → 母公司 → 係咪上市？ → materiality 檢查
                                      （產品佔母公司收入比重夠唔夠大？）
```

- Stanley 水杯爆紅 → 私人公司 → 冇交易可做
- TikTok → 字節跳動未上市 → 冇交易可做（最多諗周邊受益者）
- 某產品爆紅但只佔母公司收入 1% → 股價唔會反應 → 過濾走

呢層判斷（品牌識別、母公司查找、收入比重估算）正正係 LLM 加財報數據最擅長嘅工作。

### 信號源（照成本／難度排序）

| 源 | 成本 | 備註 |
|---|---|---|
| Reddit 產品類 subs（r/running、r/SkincareAddiction、r/fitness、r/BuyItForLife、r/GamingLeaksAndRumours、r/LocalLLaMA…） | 免費 | 直接用現有 Reddit infra，加多批 subreddit 即可 |
| Google Trends（pytrends） | 免費 | 做加速度驗證；亦係 TikTok buzz 嘅代理指標 |
| App Store／Google Play 排行榜 | 免費 | Apple 有官方 RSS；排名衝榜速度係已驗證信號 |
| Steam（遊戲同時在線／銷量榜） | 免費 API | 對遊戲股（TTWO 等）直接有效 |
| Amazon Movers & Shakers | 爬蟲（灰色） | 後期先考慮 |
| TikTok 直接數據 | 實際不可行 | Research API 限學術；用 Google Trends 做 proxy |
| YouTube 開箱／評測影片速度 | 免費 quota | YouTube Data API |

### 實施位置

排喺 **Phase 2.5**（擴源之後、質量層之前）：
1. 加產品類 subreddits 落現有 ingestion
2. 抽取層加品牌／產品 NER（LLM 做，唔係 ticker match）
3. Entity resolution + materiality 檢查（LLM + yfinance 收入數據）
4. Google Trends 做第二重驗證後先入 digest
5. Digest 入面同股票討論信號分開一欄，標明「產品 buzz」類型

## 七、更多領先數據源（brainstorm）

原則：搵「**行動早過公告、採用早過收入**」嘅數據——邊啲人／系統會喺大眾之前知道啲嘢，
而佢哋嘅行為又有公開痕跡。

### Tier A — 免費、結構化、高信號（優先接入）

| 源 | 信號 | 攞法 |
|---|---|---|
| SEC 13D/13G | Activist 建倉 >5%，最強專業人士行動信號 | EDGAR API，免費 |
| SEC Form 4 群聚買入 | 多名高管同期自掏腰包，歷史預測力極高 | EDGAR API，免費 |
| FCC 設備認證 | 新硬件上市前數月必經認證，早過發佈會 | FCC ID 數據庫，公開 |
| 政府合約 | 國防／IT 承包商贏單早過新聞稿 | USASpending.gov API，免費 |
| ClinicalTrials.gov | 試驗狀態變更領先公司公告 | 官方 API，免費 |
| Wikipedia 頁面瀏覽量 | 注意力代理，有學術支持，無人操縱 | Wikimedia API，免費 |
| GitHub / npm / PyPI 速度 | 開發者採用領先軟件股收入幾季（MDB、DDOG 類） | 免費 API |
| Hacker News 提及 | Dev tool 爆紅時華爾街未識 | Algolia HN API，免費 |
| 職位空缺速度 | Greenhouse/Lever careers page 係公開 JSON；招聘加速＝擴張，撤廣告＝警號 | 直接 poll，免費 |
| Value Investors Club | 頂級 value idea，45 日延遲版免費，學術證明延遲版仍有 alpha | 網站，延遲免費 |
| 台灣月營收 | 全球獨有嘅月度披露；半導體供應鏈 read-through，領先美股客戶季報 | 公開交易所數據 |

### Tier B — 有價值，第二批考慮

| 源 | 信號 | 障礙 |
|---|---|---|
| Earnings call read-through | 大公司 call 提到嘅細供應商，LLM 讀 transcript 做 mapping | 要 transcript 來源＋mapping 工夫 |
| 投資 podcast transcripts | 專業 podcast 提到嘅細股，聽眾少質素高 | RSS＋轉錄成本 |
| App 評論速度＋評分趨勢 | 比排行榜更細緻嘅需求信號 | 爬蟲工夫 |
| 二手市場溢價（StockX/eBay） | 炒價＝需求爆錶（GPU→NVDA、波鞋→DECK） | 爬蟲，覆蓋面窄 |
| 缺貨／waitlist 監察 | Product page 長期 sold out 係最誠實需求信號 | 要逐產品 curate |
| 短倉利率／short interest 變化 | 專業空頭行動 | FINRA 數據雙週先出 |
| 高管 LinkedIn 動向 | 大廠猛人跳去無名細公司 | LinkedIn 反爬，難 scale |
| 專利申請速度 | 公司投入方向 | 噪音大，行業差異大 |
| 公司專機航跡（ADS-B Exchange） | M&A 前 CEO jet 飛對方城市（有學術研究） | 難 scale，趣味＞實用 |

### Tier C — 明確跳過

衛星圖／泊車位計數（貴，機構玩法）、信用卡消費 panel（貴）、
expert networks（入唔到場）、Similarweb 全量 web traffic（貴）、
Discord/Telegram 私羣（入唔到場，接受盲區）。

### 接入次序建議

呢啲源全部餵入同一套 velocity/novelty 引擎，唔另起爐灶：

1. **Phase 2 加入**：EDGAR（13D/13G、Form 4 群聚）——同原計劃嘅 SEC 部分合併
2. **Phase 2.5 加入**：Wikipedia 瀏覽量（做任何候選股嘅免費驗證層）、HN、GitHub/npm
3. **Phase 3 之後逐個試**：FCC、政府合約、ClinicalTrials、職位空缺、VIC、台灣月營收
4. 每加一個源，先用回測驗證佢有冇增量價值，冇就摘走——源多唔等於好，noise 亦會多

## 八、合規注意

- 只用官方 API 同公開 RSS；唔爬 X、唔爬需要登入嘅內容
- 純個人研究用途；**唔接自動交易**
- Digest 內容唔好公開轉發（Reddit API 條款對再分發有限制）
