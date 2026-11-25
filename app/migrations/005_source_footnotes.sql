ALTER TABLE raw_news ADD COLUMN source_footnotes jsonb NOT NULL DEFAULT '[]'::jsonb;

DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'news_web') THEN
        GRANT SELECT (source_footnotes) ON raw_news TO news_web;
    END IF;
END $$;
