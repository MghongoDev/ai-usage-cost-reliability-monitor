"""Tests for the dims key: the rule that lets usage_fact's primary key survive null dimensions."""

from monitor.db import dims_key


class TestDimsKey:
    def test_all_dimensions_present_join_with_separator(self) -> None:
        assert dims_key("ws_1", "key_1", "claude-opus-5-5") == "ws_1|key_1|claude-opus-5-5"

    def test_null_dimensions_become_the_marker(self) -> None:
        assert dims_key(None, None, None) == "~|~|~"

    def test_null_in_the_middle_still_produces_a_stable_key(self) -> None:
        assert dims_key(None, "key_1", None) == "~|key_1|~"

    def test_empty_string_is_not_treated_as_null(self) -> None:
        # An empty dimension is a real (if odd) value; only None collapses.
        assert dims_key("", "key_1", "model") == "|key_1|model"

    def test_values_containing_the_separator_collide(self) -> None:
        # Known limitation, pinned deliberately: a value containing '|' can
        # collide with a different dimension split. Vendor identifiers are
        # opaque tokens (apikey_01..., claude-opus-5-5) that never contain
        # '|', so the rule is safe for this data. If that ever changes, the
        # fix is length-prefixing each value here and in the generated column.
        assert dims_key("a|b", "c", "d") == dims_key("a", "b|c", "d")

    def test_a_null_dimension_and_the_literal_marker_share_a_key(self) -> None:
        # The whole point of the rule: a null scope and an explicit '~' scope
        # are the same dimension combination, so they collide on the PK.
        assert dims_key(None, "key_1", "model") == dims_key("~", "key_1", "model")

    def test_rows_differing_in_a_real_dimension_do_not_share_a_key(self) -> None:
        # Distinct dimensions must not collide, or distinct buckets would
        # silently merge on upsert.
        assert dims_key("ws_1", "key_1", "model") != dims_key("ws_2", "key_1", "model")
