-- Schema version 4 (PRAGMA user_version = 4): every row belongs to an analysis.
-- Deleting an analysis cascades to everything it collected
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
  status       TEXT DEFAULT 'ok',  -- ok | filtered | duplicate | error
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

-- Clusters: one row per topic found in an analysis (cluster_id -1 = unclustered,
-- which has no row here)
CREATE TABLE IF NOT EXISTS clusters (
  analysis_id    TEXT NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
  cluster_id     INTEGER NOT NULL,   -- 0 = largest
  label          TEXT NOT NULL,      -- short name from Claude
  description    TEXT,               -- one sentence from Claude
  article_count  INTEGER NOT NULL,
  terms          TEXT NOT NULL DEFAULT '[]',  -- JSON [[term, weight], ...] by c-TF-IDF
  PRIMARY KEY (analysis_id, cluster_id)
);

-- Placements: where each article sits on the map and which topic it belongs to
CREATE TABLE IF NOT EXISTS placements (
  article_id   TEXT PRIMARY KEY REFERENCES articles(id) ON DELETE CASCADE,
  analysis_id  TEXT NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
  x            REAL NOT NULL,
  y            REAL NOT NULL,
  cluster_id   INTEGER NOT NULL,     -- -1 = unclustered
  distance     REAL NOT NULL         -- cosine distance to its topic's centre (outlier score)
);
CREATE INDEX IF NOT EXISTS idx_placements_analysis ON placements(analysis_id);

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
