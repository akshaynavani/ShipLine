import pytest

from shipline.errors import ShipLineError
from shipline.manifests import render_directory, template_vars


def values(**extra):
    return template_vars(
        app="hello", namespace="ns", image="repo:tag1", tag="tag1", git_sha="abc", env=extra
    )


def test_render_substitutes_builtins(cfg):
    out = render_directory(cfg.path("k8s"), values())
    assert "image: repo:tag1" in out
    assert "namespace: ns" in out


def test_shipline_var_env_is_exposed():
    v = values(SHIPLINE_VAR_REPLICAS="3", OTHER="x")
    assert v["REPLICAS"] == "3"
    assert "OTHER" not in v


def test_undefined_variable_is_an_error(tmp_path):
    (tmp_path / "a.yaml").write_text("apiVersion: v1\nkind: X\nmetadata:\n  name: ${NOPE}\n")
    with pytest.raises(ShipLineError, match="NOPE"):
        render_directory(tmp_path, values())


def test_document_without_kind_rejected(tmp_path):
    (tmp_path / "a.yaml").write_text("foo: bar\n")
    with pytest.raises(ShipLineError, match="apiVersion and kind"):
        render_directory(tmp_path, values())


def test_multiple_files_joined_in_order(tmp_path):
    (tmp_path / "20-b.yaml").write_text("apiVersion: v1\nkind: B\n")
    (tmp_path / "10-a.yaml").write_text("apiVersion: v1\nkind: A\n")
    out = render_directory(tmp_path, values())
    assert out.index("kind: A") < out.index("kind: B")
    assert "\n---\n" in out
