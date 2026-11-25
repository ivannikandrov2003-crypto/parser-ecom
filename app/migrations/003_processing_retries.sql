ALTER TABLE raw_news
    ADD COLUMN classification_failures integer NOT NULL DEFAULT 0,
    ADD COLUMN classification_failed_at timestamptz;

DROP INDEX raw_news_pending;
CREATE INDEX raw_news_pending ON raw_news (next_attempt_at, id)
    WHERE NOT checked AND classification_failed_at IS NULL;

ALTER TABLE search_outbox
    DROP CONSTRAINT search_outbox_operation_check,
    ADD CONSTRAINT search_outbox_operation_check CHECK (operation IN ('index', 'reindex', 'delete')),
    ADD COLUMN attempts integer NOT NULL DEFAULT 0,
    ADD COLUMN next_attempt_at timestamptz NOT NULL DEFAULT now();

CREATE INDEX search_outbox_due ON search_outbox (next_attempt_at, news_id);

DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'news_web') THEN
        GRANT SELECT (classification_failed_at) ON raw_news TO news_web;
        GRANT SELECT (news_id, operation, next_attempt_at) ON search_outbox TO news_web;
        GRANT UPDATE ON search_outbox TO news_ai;
        GRANT DELETE ON news TO news_ai;
    END IF;
END $$;
