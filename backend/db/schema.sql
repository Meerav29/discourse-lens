-- Schema version 3 (PRAGMA user_version = 3): every row belongs to an analysis.
-- Deleting an analysis cascades to its articles, chunks and projections
-- (requires PRAGMA foreign_keys = ON, set by backend.db.connect).

-- Analyses: one row per topic run (formerly "jobs")
CREATE TABLE IF NOT EXISTS analyses (
  id            TEXT PRIMARY KEY,   -- uuid4
  topic         TEXT NOT NULL,
  status        TEXT NOT NULL,      -- queued | crawling | processing | embedding | projecting | done | error | cancelled
  progress      INTEGER DEFAULT 0,  -- 0-100
  stage_detail  TEXT,               -- e.g. "Crawled 47 of 112 pages"
  article_count INTEGER DEFAULT 0,
  error_msg     TEXT,
  warning       TEXT,               -- non-fatal warning, e.g. low article yield
  created_ts    INTEGER NOT NULL,
  updated_ts    INTEGER NOT NULL
);

-- Articles: one row per crawled URL per analysis
CREATE TABLE IF NOT EXISTS articles (
  id           TEXT PRIMARY KEY,   -- sha256(analysis_id:url)[:16]
  analysis_id  TEXT NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
  url          TEXT NOT NULL,
  domain       TEXT,
  title        TEXT,
  publish_date TEXT,               -- ISO date string, nullable
  crawl_ts     INTEGER,            -- unix timestamp
  word_count   INTEGER,
  language     TEXT DEFAULT 'en',
  raw_text     TEXT,
  status       TEXT DEFAULT 'ok',  -- ok | filtered | error
  UNIQUE (analysis_id, url)
);
CREATE INDEX IF NOT EXISTS idx_articles_analysis ON articles(analysis_id);

-- Chunks: one row per child chunk
CREATE TABLE IF NOT EXISTS chunks (
  id           TEXT PRIMARY KEY,   -- {article_id}#p{i}c{j}
  analysis_id  TEXT NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
  article_id   TEXT REFERENCES articles(id) ON DELETE CASCADE,
  parent_id    TEXT,               -- {article_id}#p{i}
  parent_text  TEXT,               -- full parent chunk text (for RAG context)
  child_text   TEXT,
  chunk_index  INTEGER,
  token_count  INTEGER,
  is_duplicate INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_chunks_analysis ON chunks(analysis_id);
CREATE INDEX IF NOT EXISTS idx_chunks_article ON chunks(article_id);

-- Projections: 2D UMAP coords + cluster info per chunk
CREATE TABLE IF NOT EXISTS projections (
  chunk_id                TEXT PRIMARY KEY REFERENCES chunks(id) ON DELETE CASCADE,
  analysis_id             TEXT NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
  x                       REAL,
  y                       REAL,
  cluster_id              INTEGER,
  cluster_label           TEXT,    -- LLM-generated 2-3 word label
  distance_from_centroid  REAL
);
CREATE INDEX IF NOT EXISTS idx_projections_analysis ON projections(analysis_id);

-- Live log of what a pipeline run is doing; streamed to the UI over SSE.
CREATE TABLE IF NOT EXISTS analysis_events (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  analysis_id  TEXT NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
  ts           INTEGER NOT NULL,
  kind         TEXT NOT NULL,      -- stage | query | article | skip | cluster | warning | error
  message      TEXT NOT NULL,
  url          TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_analysis ON analysis_events(analysis_id, id);
