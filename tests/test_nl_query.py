import pytest

from src.nl_query import ensure_select


def test_plain_select_passes():
    assert ensure_select("SELECT count(*) FROM runs").lower().startswith("select")


def test_strips_markdown_fence_and_trailing_semicolon():
    assert ensure_select("```sql\nSELECT * FROM runs;\n```") == "SELECT * FROM runs"


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM runs",
        "UPDATE runs SET status='x'",
        "SELECT 1; DROP TABLE runs",
        "PRAGMA table_info(runs)",
        "INSERT INTO runs VALUES (1)",
    ],
)
def test_non_select_is_blocked(sql):
    with pytest.raises(ValueError):
        ensure_select(sql)
