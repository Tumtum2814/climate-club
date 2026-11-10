from pathlib import Path
from zipfile import ZipFile

import pytest

from scripts.build import build
from scripts.prepare_release import metadata

ROOT = Path(__file__).resolve().parents[1]


def test_source_zip_contains_installable_integration_and_card_not_dependencies(
    tmp_path,
):
    output = tmp_path / "release.zip"
    build(ROOT, output)
    assert output.is_file()
    with ZipFile(output) as archive:
        assert archive.testzip() is None
        paths = set(archive.namelist())
        assert "custom_components/unified_climate/manifest.json" in paths
        assert (
            "custom_components/unified_climate/frontend/unified-climate-card.js"
            in paths
        )
        assert "README.md" in paths
        assert not any("node_modules" in p or "__pycache__" in p for p in paths)


def test_release_metadata_requires_explicit_github_repo_and_codeowner():
    # Synthetic identifiers for parsing only; never published or placed in manifest.
    result = metadata("https://github.com/fixture/repo", "@fixture")
    assert result["documentation"] == "https://github.com/fixture/repo"
    assert result["issue_tracker"] == "https://github.com/fixture/repo/issues"
    assert result["codeowners"] == ["@fixture"]
    with pytest.raises(ValueError):
        metadata("https://example.com/owner/repo", "@fixture")
