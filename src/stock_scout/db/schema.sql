-- Stock Scout schema (Supabase / Postgres). Applied by `stock-scout init-db`.

CREATE TABLE IF NOT EXISTS sources (
    id          SERIAL PRIMARY KEY,
    kind        TEXT NOT NULL,              -- reddit | rss | apewisdom | edgar
    name        TEXT NOT NULL,
    url         TEXT,
    tier        TEXT NOT NULL,              -- leading | lagging | action
    enabled     BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (kind, name)
);

CREATE TABLE IF NOT EXISTS authors (
    id                  SERIAL PRIMARY KEY,
    source_kind         TEXT NOT NULL,
    handle              TEXT NOT NULL,
    account_created_at  TIMESTAMPTZ,
    first_seen          TIMESTAMPTZ NOT NULL DEFAULT now(),
    reputation          REAL NOT NULL DEFAULT 0.5,
    UNIQUE (source_kind, handle)
);

CREATE TABLE IF NOT EXISTS posts (
    id           BIGSERIAL PRIMARY KEY,
    source_id    INTEGER NOT NULL REFERENCES sources(id),
    external_id  TEXT NOT NULL,
    url          TEXT,
    title        TEXT,
    body         TEXT,
    author_id    INTEGER REFERENCES authors(id),
    posted_at    TIMESTAMPTZ NOT NULL,
    fetched_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    upvotes      INTEGER,
    num_comments INTEGER,
    UNIQUE (source_id, external_id)
);
CREATE INDEX IF NOT EXISTS idx_posts_posted_at ON posts (posted_at);

CREATE TABLE IF NOT EXISTS tickers (
    symbol      TEXT PRIMARY KEY,
    name        TEXT,
    exchange    TEXT,
    sector      TEXT,
    market_cap  BIGINT,
    is_otc      BOOLEAN NOT NULL DEFAULT FALSE,
    first_seen  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS mentions (
    id         BIGSERIAL PRIMARY KEY,
    post_id    BIGINT NOT NULL REFERENCES posts(id),
    symbol     TEXT NOT NULL REFERENCES tickers(symbol),
    method     TEXT NOT NULL,               -- cashtag | exact | llm
    confidence REAL NOT NULL,
    UNIQUE (post_id, symbol)
);
CREATE INDEX IF NOT EXISTS idx_mentions_symbol ON mentions (symbol);

CREATE TABLE IF NOT EXISTS brands (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    parent_company  TEXT,
    symbol          TEXT REFERENCES tickers(symbol),
    is_public       BOOLEAN,
    materiality_pct REAL,
    resolved_at     TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS brand_mentions (
    id         BIGSERIAL PRIMARY KEY,
    post_id    BIGINT NOT NULL REFERENCES posts(id),
    brand_id   INTEGER NOT NULL REFERENCES brands(id),
    confidence REAL NOT NULL,
    UNIQUE (post_id, brand_id)
);

CREATE TABLE IF NOT EXISTS daily_stats (
    date              DATE NOT NULL,
    symbol            TEXT NOT NULL REFERENCES tickers(symbol),
    tier              TEXT NOT NULL,
    mention_count     INTEGER NOT NULL DEFAULT 0,
    unique_authors    INTEGER NOT NULL DEFAULT 0,
    weighted_mentions REAL NOT NULL DEFAULT 0,
    velocity_z        REAL,
    PRIMARY KEY (date, symbol, tier)
);

CREATE TABLE IF NOT EXISTS prices (
    date       DATE NOT NULL,
    symbol     TEXT NOT NULL REFERENCES tickers(symbol),
    close      REAL,
    volume     BIGINT,
    market_cap BIGINT,
    PRIMARY KEY (date, symbol)
);

CREATE TABLE IF NOT EXISTS alerts (
    id                BIGSERIAL PRIMARY KEY,
    date              DATE NOT NULL,
    symbol            TEXT REFERENCES tickers(symbol),
    brand_id          INTEGER REFERENCES brands(id),
    score             REAL NOT NULL,
    components_json   JSONB NOT NULL,
    manipulation_risk REAL NOT NULL DEFAULT 0,
    story_json        JSONB,
    slack_message_ts  TEXT,
    feedback          TEXT,                 -- up | down
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (date, symbol)
);

CREATE TABLE IF NOT EXISTS runs (
    id           BIGSERIAL PRIMARY KEY,
    started_at   TIMESTAMPTZ NOT NULL,
    finished_at  TIMESTAMPTZ,
    status       TEXT NOT NULL DEFAULT 'running',   -- running | ok | failed
    stats_json   JSONB,
    llm_cost_usd REAL NOT NULL DEFAULT 0
);
