ALTER TABLE news
    ADD COLUMN telegram_next_attempt_at timestamptz DEFAULT now(),
    ADD COLUMN telegram_message_id bigint;

COMMENT ON COLUMN news.telegram_next_attempt_at IS
    'NULL после начала отправки. Если is_posted=false, доставка ещё выполняется или требует проверки.';

DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'news_ai') THEN
        GRANT UPDATE (is_posted, telegram_next_attempt_at, telegram_message_id) ON news TO news_ai;
    END IF;
END $$;
