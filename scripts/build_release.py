from __future__ import annotations

import argparse
import shutil
from pathlib import Path

try:
    import tomllib  # type: ignore[attr-defined]
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]


PROJECT_FILES = [
    "pyproject.toml",
    "ecosystem.config.cjs",
    "config.example.toml",
    ".env.example",
]

PROJECT_DIRS = [
    "app",
    "scripts",
    "docs",
]

PLACEHOLDER_DIRS = [
    "logs",
    "data/digests",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a deployable release zip for Daily arXiv Notify."
    )
    parser.add_argument(
        "--output-dir",
        default="dist",
        help="Directory where release artifacts are written.",
    )
    parser.add_argument(
        "--exclude-local-config",
        action="store_true",
        help="Exclude local config.toml and .env from the release bundle.",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Delete any existing output directory before building.",
    )
    return parser.parse_args()


def load_project_metadata(repo_root: Path) -> tuple[str, str]:
    with (repo_root / "pyproject.toml").open("rb") as fh:
        pyproject = tomllib.load(fh)
    project = pyproject["project"]
    return str(project["name"]), str(project["version"])


def ensure_exists(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Required project path not found: {path}")


def copy_tree(src: Path, dst: Path) -> None:
    shutil.copytree(
        src,
        dst,
        ignore=shutil.ignore_patterns(
            "__pycache__",
            "*.pyc",
            "*.pyo",
            "*.pyd",
            ".pytest_cache",
            "*.egg-info",
        ),
    )


def write_deploy_notes(target_dir: Path, archive_name: str) -> None:
    content = f"""# Deploy Notes

Archive: `{archive_name}`

## 1. Extract

Unzip this archive to the deployment directory.

## 2. Prepare config

- By default, this release bundle already includes local `config.toml` and `.env`.
- If you built the archive with `--exclude-local-config`, copy:
  - `config.example.toml` -> `config.toml`
  - `.env.example` -> `.env`
  and fill in the required values.

## 3. Install dependencies

```bash
python -m pip install .
```

## 4. Run once manually

```bash
daily-arxiv-notify run-once --config config.toml --dry-run
```

## 5. Start with PM2

```bash
pm2 start ecosystem.config.cjs
pm2 save
```
"""
    (target_dir / "DEPLOY.md").write_text(content, encoding="utf-8")


def build_release(
    *,
    repo_root: Path,
    output_dir: Path,
    exclude_local_config: bool,
    clean: bool,
) -> Path:
    project_name, project_version = load_project_metadata(repo_root)
    release_name = f"{project_name}-{project_version}"
    release_root = output_dir / release_name

    if clean and output_dir.exists():
        shutil.rmtree(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)
    if release_root.exists():
        shutil.rmtree(release_root)
    release_root.mkdir(parents=True, exist_ok=True)

    for relative_file in PROJECT_FILES:
        source = repo_root / relative_file
        ensure_exists(source)
        shutil.copy2(source, release_root / relative_file)

    for relative_dir in PROJECT_DIRS:
        source = repo_root / relative_dir
        ensure_exists(source)
        copy_tree(source, release_root / relative_dir)

    if not exclude_local_config:
        for optional_file in ("config.toml", ".env"):
            source = repo_root / optional_file
            if source.exists():
                shutil.copy2(source, release_root / optional_file)

    for relative_dir in PLACEHOLDER_DIRS:
        (release_root / relative_dir).mkdir(parents=True, exist_ok=True)

    write_deploy_notes(release_root, f"{release_name}.zip")

    archive_path = shutil.make_archive(
        base_name=str(output_dir / release_name),
        format="zip",
        root_dir=output_dir,
        base_dir=release_name,
    )
    return Path(archive_path)


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parent.parent
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = repo_root / output_dir

    archive_path = build_release(
        repo_root=repo_root,
        output_dir=output_dir,
        exclude_local_config=args.exclude_local_config,
        clean=args.clean,
    )
    print(f"Release archive created: {archive_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
