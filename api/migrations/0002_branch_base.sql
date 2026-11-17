-- DESIGN.md §14.11: the last message of main when a branch was opened. Take-aways
-- merged up to there are visible in the branch. NULL for branches stored before
-- this column existed: they see main up to their anchor only, as they always did.
ALTER TABLE branch ADD COLUMN base_message_id INTEGER REFERENCES message(id);
