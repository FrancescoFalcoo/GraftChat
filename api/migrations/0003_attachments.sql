-- Images attached to a user message. They are sent to the model with that message
-- every time it is part of a context (api/service.py); the call log refers to them
-- by id ("attachment:<id>") instead of copying the bytes.
CREATE TABLE attachment (
    id         INTEGER PRIMARY KEY,
    message_id INTEGER NOT NULL REFERENCES message(id) ON DELETE CASCADE,
    position   INTEGER NOT NULL,
    kind       TEXT NOT NULL CHECK (kind IN ('image')),
    mime       TEXT NOT NULL,
    name       TEXT NOT NULL,
    size       INTEGER NOT NULL,
    data       BLOB NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (message_id, position)
);
CREATE INDEX attachment_by_message ON attachment(message_id);
