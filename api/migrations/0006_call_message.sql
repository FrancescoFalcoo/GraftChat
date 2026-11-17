-- Which model call produced which answer, for the usage figures of the interface.
-- Kept outside llm_call_log (which mirrors core.models.LLMCallLog) and outside core: it is
-- bookkeeping of the API. Answers stored before this migration simply have no row.

CREATE TABLE call_message (
    call_id    INTEGER PRIMARY KEY REFERENCES llm_call_log(id),
    message_id INTEGER NOT NULL UNIQUE REFERENCES message(id)
);
