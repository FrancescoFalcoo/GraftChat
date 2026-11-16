-- Schema of DESIGN.md §6. Column names and meanings mirror core/models.py one-to-one.

CREATE TABLE conversation (
    id         INTEGER PRIMARY KEY,
    title      TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE message (
    id              INTEGER PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES conversation(id),
    branch_id       INTEGER REFERENCES branch(id),      -- NULL = main thread
    parent_id       INTEGER REFERENCES message(id),     -- previous message in the same thread
    role            TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'merge')),
    content         TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    CHECK (role <> 'merge' OR branch_id IS NULL)        -- merge nodes live on main
);

-- A thread is a chain: at most one child per message, one root per thread (§14.1).
CREATE UNIQUE INDEX message_one_child ON message(parent_id) WHERE parent_id IS NOT NULL;
CREATE UNIQUE INDEX message_one_root
    ON message(conversation_id, IFNULL(branch_id, 0)) WHERE parent_id IS NULL;
CREATE INDEX message_by_conversation ON message(conversation_id);

CREATE TABLE branch (
    id                INTEGER PRIMARY KEY,
    conversation_id   INTEGER NOT NULL REFERENCES conversation(id),
    anchor_message_id INTEGER NOT NULL REFERENCES message(id),
    anchor_start      INTEGER NOT NULL,
    anchor_end        INTEGER NOT NULL,
    anchor_quote      TEXT NOT NULL,
    status            TEXT NOT NULL CHECK (status IN ('open', 'merged', 'discarded')),
    merge_message_id  INTEGER REFERENCES message(id),
    created_at        TEXT NOT NULL,
    CHECK (anchor_start >= 0 AND anchor_end > anchor_start),
    CHECK ((status = 'merged') = (merge_message_id IS NOT NULL))
);
CREATE INDEX branch_by_conversation ON branch(conversation_id);

CREATE TABLE takeaway_point (
    id             INTEGER PRIMARY KEY,
    branch_id      INTEGER NOT NULL REFERENCES branch(id),
    position       INTEGER NOT NULL,
    title          TEXT NOT NULL,
    text_generated TEXT NOT NULL,
    text_final     TEXT NOT NULL,
    included       INTEGER NOT NULL CHECK (included IN (0, 1)),
    UNIQUE (branch_id, position)
);

CREATE TABLE llm_call_log (
    id              INTEGER PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES conversation(id),
    branch_id       INTEGER REFERENCES branch(id),
    purpose         TEXT NOT NULL CHECK (purpose IN ('chat', 'takeaway', 'experiment')),
    condition       TEXT CHECK (condition IN ('A', 'B', 'C', 'D')),
    model           TEXT NOT NULL,
    input_tokens    INTEGER NOT NULL,
    output_tokens   INTEGER NOT NULL,
    cost_estimate   REAL NOT NULL,
    prompt_json     TEXT NOT NULL,
    response_text   TEXT NOT NULL,
    created_at      TEXT NOT NULL
);
CREATE INDEX llm_call_log_by_time ON llm_call_log(created_at);
