import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


def load_check_stale():
    module_path = Path(__file__).resolve().parents[1] / "tools" / "check_stale.py"
    spec = importlib.util.spec_from_file_location("check_stale", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def configure_repo(module, repo_root: Path):
    module.REPO_ROOT = repo_root
    module.WIKI_DIR = repo_root / "wiki"
    module.SOURCES_DIR = module.WIKI_DIR / "sources"
    module.RAW_DIR = repo_root / "raw"
    module.REFRESH_CACHE = repo_root / "graph" / ".refresh_cache.json"


def write_repo(repo_root: Path, content: str = "same content"):
    raw_file = repo_root / "raw" / "docs" / "example.md"
    source_page = repo_root / "wiki" / "sources" / "example.md"
    raw_file.parent.mkdir(parents=True)
    source_page.parent.mkdir(parents=True)
    (repo_root / "graph").mkdir()
    raw_file.write_text(content, encoding="utf-8")
    source_page.write_text(
        "---\n"
        "title: Example\n"
        "type: source\n"
        "source_file: raw/docs/example.md\n"
        "---\n",
        encoding="utf-8",
    )
    return raw_file


class CheckStaleCacheTests(unittest.TestCase):
    def test_stale_detection_uses_repo_relative_cache_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            module = load_check_stale()
            repo_root = tmp_path / "repo"
            raw_file = write_repo(repo_root)
            configure_repo(module, repo_root)

            cache = {"raw/docs/example.md": module.sha256(raw_file.read_text(encoding="utf-8"))}
            module.REFRESH_CACHE.write_text(json.dumps(cache), encoding="utf-8")

            self.assertEqual(module.find_stale_sources(), [])

    def test_absolute_cache_keys_are_migrated_to_relative_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            module = load_check_stale()
            old_repo = tmp_path / "old" / "repo"
            old_raw_file = write_repo(old_repo)
            old_absolute_key = str(old_raw_file)
            old_hash = module.sha256(old_raw_file.read_text(encoding="utf-8"))

            new_repo = tmp_path / "new" / "repo"
            write_repo(new_repo)
            configure_repo(module, new_repo)
            module.REFRESH_CACHE.write_text(json.dumps({old_absolute_key: old_hash}), encoding="utf-8")

            self.assertEqual(module.find_stale_sources(), [])
            self.assertEqual(
                json.loads(module.REFRESH_CACHE.read_text(encoding="utf-8")),
                {"raw/docs/example.md": old_hash},
            )


if __name__ == "__main__":
    unittest.main()
