"""GraftChat backend (DESIGN.md §9, §12): HTTP API, SQLite persistence, OpenRouter client.

Everything here is plumbing around ``core``: the tree rules and the context
builder live in ``core`` and are only *called* from this package.
"""
