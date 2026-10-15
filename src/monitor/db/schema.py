"""The dims key: how a usage_fact row's nullable dimensions collapse into one stable string.

The primary key of usage_fact is (provider, bucket_start, bucket_width, dims_key).
Scope, key, and model are all nullable because vendors legitimately report usage
with no key attribution (console usage) or no scope (default workspace). A null in
a primary key column would break the key, so each nullable dimension becomes the
'~' marker and the three join with '|'. Two rows that differ only in a null
dimension share a dims key and collide, which is correct: they are the same
dimension combination.
"""

NULL_DIM = "~"
DIM_SEP = "|"


def dims_key(scope_id: str | None, api_key_id: str | None, model: str | None) -> str:
    """Collapse the three nullable dimensions into one stable key string."""
    return DIM_SEP.join(
        NULL_DIM if value is None else value for value in (scope_id, api_key_id, model)
    )
