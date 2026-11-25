CREATE TABLE raw_news (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    header text NOT NULL,
    text text NOT NULL,
    source text NOT NULL UNIQUE,
    source_name text NOT NULL,
    published_at timestamptz(3) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    checked boolean NOT NULL DEFAULT false,
    is_ecom boolean,
    keywords jsonb,
    ai_summary text,
    duplicate_of_news_id bigint,
    duplicate_score double precision,
    claim_token uuid,
    claim_until timestamptz,
    next_attempt_at timestamptz NOT NULL DEFAULT now(),
    attempts integer NOT NULL DEFAULT 0
);

CREATE TABLE news (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    text text NOT NULL,
    is_posted boolean NOT NULL DEFAULT false,
    raw_news_id bigint NOT NULL UNIQUE REFERENCES raw_news(id),
    created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE raw_news ADD FOREIGN KEY (duplicate_of_news_id) REFERENCES news(id) ON DELETE SET NULL;

CREATE INDEX raw_news_pending ON raw_news (next_attempt_at, id) WHERE NOT checked;
CREATE INDEX raw_news_created ON raw_news (created_at);
CREATE INDEX raw_news_published ON raw_news (published_at DESC, source ASC);
CREATE INDEX raw_news_duplicate ON raw_news (duplicate_of_news_id) WHERE duplicate_of_news_id IS NOT NULL;
CREATE INDEX news_created ON news (created_at);
CREATE INDEX news_unposted ON news (id) WHERE NOT is_posted;

CREATE TABLE search_outbox (
    news_id bigint PRIMARY KEY,
    operation text NOT NULL CHECK (operation IN ('index', 'delete'))
);

CREATE TABLE collection_job (
    id integer PRIMARY KEY CHECK (id = 1),
    state text NOT NULL CHECK (state IN ('idle', 'queued', 'running', 'done', 'failed')),
    finished_at timestamptz,
    result jsonb
);

INSERT INTO collection_job (id, state) VALUES (1, 'idle');

DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'news_web') THEN
        GRANT SELECT (id, header, source, source_name, published_at, checked, next_attempt_at) ON raw_news TO news_web;
        GRANT SELECT (id, text, raw_news_id) ON news TO news_web;
        GRANT SELECT ON collection_job TO news_web;
        GRANT UPDATE (state) ON collection_job TO news_web;
        GRANT SELECT (source), INSERT ON raw_news TO news_parser;
        GRANT USAGE ON SEQUENCE raw_news_id_seq TO news_parser;
        GRANT SELECT, UPDATE ON collection_job TO news_parser;
        GRANT SELECT, UPDATE ON raw_news TO news_ai;
        GRANT SELECT, INSERT ON news TO news_ai;
        GRANT USAGE ON SEQUENCE news_id_seq TO news_ai;
        GRANT SELECT, INSERT, DELETE ON search_outbox TO news_ai;
        GRANT SELECT, DELETE ON raw_news, news TO news_cleanup;
        GRANT SELECT, INSERT, UPDATE ON search_outbox TO news_cleanup;
    END IF;
END $$;
