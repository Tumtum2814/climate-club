"""Fill HACS-required metadata only when a real public repository is known."""

import argparse
import json
import re
from pathlib import Path


def metadata(repo_url, codeowner):
    if not re.fullmatch(
        r"https://github\.com/[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+", repo_url
    ) or repo_url.endswith(".git"):
        raise ValueError(
            "Supply the exact public GitHub repository HTTPS URL without trailing slash or .git"
        )
    if not re.fullmatch(r"@[A-Za-z0-9][A-Za-z0-9-]*", codeowner):
        raise ValueError("Supply a real GitHub codeowner handle beginning with @")
    return {
        "documentation": repo_url,
        "issue_tracker": repo_url + "/issues",
        "codeowners": [codeowner],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-url", required=True)
    parser.add_argument("--codeowner", required=True)
    args = parser.parse_args()
    changes = metadata(args.repo_url, args.codeowner)
    manifest = (
        Path(__file__).resolve().parents[1]
        / "custom_components/unified_climate/manifest.json"
    )
    data = json.loads(manifest.read_text())
    manifest.write_text(json.dumps({**data, **changes}, indent=2) + "\n")
    print(
        "Local metadata updated; repository existence/public visibility not verified. Nothing published."
    )
