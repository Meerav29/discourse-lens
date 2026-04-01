-- Articles: one row per crawled URL
CREATE TABLE IF NOT EXISTS articles (
  id           TEXT PRIMARY KEY,   -- sha256(url)[:16]
  url          TEXT NOT NULL UNIQUE,
  domain       TEXT,
  title        TEXT,
  publish_date TEXT,               -- ISO date string, nullable
  crawl_ts     INTEGER,            -- unix timestamp
  word_count   INTEGER,
  language     TEXT DEFAULT 'en',
  raw_text     TEXT,
  status       TEXT DEFAULT 'ok'   -- ok | filtered | error
);

-- Chunks: one row per child chunk
CREATE TABLE IF NOT EXISTS chunks (
  id           TEXT PRIMARY KEY,   -- {article_id}#p{i}c{j}
  article_id   TEXT REFERENCES articles(id),
  parent_id    TEXT,               -- {article_id}#p{i}
  parent_text  TEXT,               -- full parent chunk text (for RAG context)
  child_text   TEXT,
  chunk_index  INTEGER,
  token_count  INTEGER,
  is_duplicate INTEGER DEFAULT 0
);

-- Projections: 2D UMAP coords + cluster info per chunk
CREATE TABLE IF NOT EXISTS projections (
  chunk_id                TEXT PRIMARY KEY REFERENCES chunks(id),
  x                       REAL,
  y                       REAL,
  cluster_id              INTEGER,
  cluster_label           TEXT,    -- LLM-generated 2-3 word label
  distance_from_centroid  REAL
);

-- Jobs: track ingestion pipeline state
CREATE TABLE IF NOT EXISTS jobs (
  id            TEXT PRIMARY KEY,   -- uuid4
  topic         TEXT,
  status        TEXT,               -- queued | crawling | processing | embedding | projecting | done | error
  progress      INTEGER DEFAULT 0,  -- 0-100
  article_count INTEGER DEFAULT 0,
  error_msg     TEXT,
  created_ts    INTEGER,
  updated_ts    INTEGER
);
