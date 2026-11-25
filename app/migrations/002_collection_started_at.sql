ALTER TABLE collection_job ADD COLUMN started_at timestamptz;

UPDATE collection_job SET started_at = finished_at WHERE finished_at IS NOT NULL;
