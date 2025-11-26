CREATE EXTENSION IF NOT EXISTS vector;


CREATE TABLE IF NOT EXISTS arch_items (
id SERIAL PRIMARY KEY,
repo TEXT,
pr INTEGER,
filepath TEXT,
comment TEXT,
diff TEXT,
concerns JSONB,
arch_summary TEXT,
evidence TEXT,
embedding VECTOR(768)
);


CREATE INDEX IF NOT EXISTS arch_items_repo_pr_idx ON arch_items(repo, pr);
CREATE INDEX IF NOT EXISTS arch_items_concerns_gin ON arch_items USING GIN(concerns);
