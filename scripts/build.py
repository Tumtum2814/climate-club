"""Build a manual-install/source archive, excluding caches and dependencies."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def build(root, output):
    root, output = Path(root), Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    excluded = {
        ".git",
        ".venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        "dist",
    }
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            relative = path.relative_to(root)
            if (
                path.is_file()
                and not excluded.intersection(relative.parts)
                and path.suffix not in (".pyc", ".DS_Store")
                and path.name != ".DS_Store"
            ):
                archive.write(path, relative.as_posix())
    return output


if __name__ == "__main__":
    print(
        build(
            Path(__file__).resolve().parents[1],
            Path(__file__).resolve().parents[1] / "dist/unified-climate.zip",
        )
    )
