-- Documents next to images (DESIGN.md §14.13). A document keeps its original bytes (to
-- download it again) and the text extracted from it, which is what the model receives.
-- SQLite cannot change a CHECK constraint, so the table is rebuilt.
CREATE TABLE attachment_new (
    id         INTEGER PRIMARY KEY,
    message_id INTEGER NOT NULL REFERENCES message(id) ON DELETE CASCADE,
    position   INTEGER NOT NULL,
    kind       TEXT NOT NULL CHECK (kind IN ('image', 'document')),
    mime       TEXT NOT NULL,
    name       TEXT NOT NULL,
    size       INTEGER NOT NULL,
    data       BLOB NOT NULL,
    text       TEXT,                                    -- extracted text; documents only
    created_at TEXT NOT NULL,
    UNIQUE (message_id, position),
    CHECK ((kind = 'document') = (text IS NOT NULL))
);
INSERT INTO attachment_new (id, message_id, position, kind, mime, name, size, data, text, created_at)
    SELECT id, message_id, position, kind, mime, name, size, data, NULL, created_at FROM attachment;
DROP TABLE attachment;
ALTER TABLE attachment_new RENAME TO attachment;
CREATE INDEX attachment_by_message ON attachment(message_id);
