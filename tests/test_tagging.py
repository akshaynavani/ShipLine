from datetime import UTC, datetime

import pytest

from shipline.errors import ShipLineError
from shipline.tagging import git_sha, make_tag, parse_tag_time, validate_tag
from tests.conftest import fail


def test_make_tag_format():
    when = datetime(2026, 3, 4, 5, 6, 7, tzinfo=UTC)
    assert make_tag("abc1234", when) == "abc1234-20260304T050607Z"


def test_parse_tag_time_roundtrip():
    tag = make_tag("abc1234", datetime(2026, 1, 1, tzinfo=UTC))
    assert parse_tag_time(tag) == datetime(2026, 1, 1, tzinfo=UTC)
    assert parse_tag_time("v1.2.3") is None


@pytest.mark.parametrize("bad", ["latest", "-leading-dash", "has space", "x" * 200])
def test_validate_rejects(bad):
    with pytest.raises(ShipLineError):
        validate_tag(bad)


def test_git_sha_marks_dirty(runner, tmp_path):
    runner.on("rev-parse", respond="abc1234\n")
    runner.on("status", "--porcelain", respond=" M app.py\n")
    assert git_sha(runner, tmp_path) == "abc1234-dirty"


def test_git_sha_without_repo(runner, tmp_path):
    runner.on("rev-parse", respond=fail("not a git repository", 128))
    assert git_sha(runner, tmp_path) == "nogit"
