from shipline.releases import FAILED, LocalReleaseStore, Release


def store(tmp_path, limit=20):
    return LocalReleaseStore(tmp_path / "r.json", limit=limit)


def add(s, tag, **kw):
    s.record(Release(tag=tag, image=f"repo:{tag}", actor="test", **kw))


def test_record_and_list_roundtrip(tmp_path):
    s = store(tmp_path)
    add(s, "a")
    add(s, "b")
    assert [r.tag for r in s.list()] == ["a", "b"]
    assert s.find("a").image == "repo:a"


def test_history_is_trimmed(tmp_path):
    s = store(tmp_path, limit=3)
    for t in "abcde":
        add(s, t)
    assert [r.tag for r in s.list()] == ["c", "d", "e"]


def test_previous_good_skips_failed(tmp_path):
    s = store(tmp_path)
    add(s, "a")
    add(s, "b", status=FAILED)
    add(s, "c")
    assert s.previous_good("c").tag == "a"


def test_repeated_rollbacks_step_back(tmp_path):
    s = store(tmp_path)
    for t in "abc":
        add(s, t)
    assert s.previous_good("c").tag == "b"
    add(s, "b", kind="rollback")
    # Running b now: next rollback should go to a, not bounce forward to c.
    assert s.previous_good("b").tag == "a"
    add(s, "a", kind="rollback")
    assert s.previous_good("a") is None


def test_previous_good_when_current_unknown(tmp_path):
    s = store(tmp_path)
    add(s, "a")
    add(s, "b")
    assert s.previous_good("hotfix-manual").tag == "b"
