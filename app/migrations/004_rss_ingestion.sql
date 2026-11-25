ALTER TABLE raw_news ADD COLUMN is_feed_excerpt boolean NOT NULL DEFAULT false;

CREATE TABLE rss_retry_after (
    source_url text PRIMARY KEY,
    retry_at timestamptz NOT NULL
);

DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'news_web') THEN
        GRANT SELECT (is_feed_excerpt) ON raw_news TO news_web;
        GRANT SELECT, INSERT, UPDATE ON rss_retry_after TO news_parser;
    END IF;
END $$;
