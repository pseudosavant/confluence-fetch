import json
from pathlib import Path

import pytest

from confluence_fetch import runtime


@pytest.fixture
def distribution(monkeypatch, tmp_path):
    class Distribution:
        direct_url = None

        def read_text(self, name):
            assert name == "direct_url.json"
            return self.direct_url

        def locate_file(self, path):
            return tmp_path / "site-packages" / path

    installed = Distribution()
    monkeypatch.setattr(runtime.metadata, "distribution", lambda name: installed)
    monkeypatch.setattr(runtime, "__file__", str(installed.locate_file("confluence_fetch/runtime.py")))
    return installed


@pytest.mark.parametrize("source,development", [
    (None, False),
    ({"url": "file:///project", "dir_info": {}}, True),
    ({"url": "file:///project", "dir_info": {"editable": True}}, True),
    ({"url": "file:///project", "dir_info": {"editable": False}}, True),
    ({"url": "file:///package.tar.gz", "archive_info": {}}, True),
    ({"url": "file:///package.whl", "archive_info": {}}, False),
    ({"url": "https://example.org/package.whl", "archive_info": {}}, False),
    ({"url": "https://example.org/repo", "vcs_info": {"vcs": "git"}}, False),
])
def test_distribution_provenance(distribution, source, development):
    distribution.direct_url = json.dumps(source) if source is not None else None
    assert (runtime.local_development_reason() is not None) == development


def test_source_checkout_shadowing_installed_package_is_excluded(distribution, monkeypatch, tmp_path):
    monkeypatch.setattr(runtime, "__file__", str(tmp_path / "checkout/src/confluence_fetch/runtime.py"))
    assert "local checkout" in runtime.local_development_reason()


def test_checkout_with_matching_legacy_distribution_metadata_is_excluded(distribution):
    root = distribution.locate_file("pyproject.toml")
    root.parent.mkdir(parents=True)
    root.write_text('[project]\nname = "confluence-fetch"\n', encoding="utf-8")
    assert runtime.local_development_reason() == "local project checkout"


@pytest.mark.parametrize("bad", ["{", "[]", "null", '{}', '{"url": 42}'])
def test_unknown_distribution_provenance_is_excluded(distribution, bad):
    distribution.direct_url = bad
    assert runtime.local_development_reason() is not None


def test_missing_distribution_is_excluded(monkeypatch):
    def missing(name):
        raise runtime.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(runtime.metadata, "distribution", missing)
    assert runtime.local_development_reason() is not None


def test_actual_checkout_is_ineligible():
    assert Path(runtime.__file__).resolve().parts[-3] == "src"
    assert runtime.local_development_reason() is not None
