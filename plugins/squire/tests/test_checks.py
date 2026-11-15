from __future__ import annotations

import json

import pytest

import checks
from conftest import commit, write


@pytest.mark.parametrize("files, expected", [
    ({"Makefile": "build:\n\ttrue\nlint:\n\ttrue\ntest:\n\ttrue\nVAR := 1\n"}, ["make build", "make lint", "make test"]),
    ({"Makefile": "all:\n\ttrue\n", "go.mod": "module x\n"}, ["go build ./...", "go vet ./...", "go test ./..."]),
    ({"package.json": json.dumps({"scripts": {"test": "vitest", "lint": "eslint ."}})}, ["npm run lint", "npm test"]),
    ({"package.json": json.dumps({"scripts": {"test": "vitest"}}), "pnpm-lock.yaml": ""}, ["pnpm run test"]),
    ({"Cargo.toml": "[package]\n"}, ["cargo build", "cargo test"]),
    ({"pyproject.toml": "[project]\n"}, ["python3 -m pytest -q"]),
    ({"README.md": "hi\n"}, []),
])
def test_detect_prefers_the_makefile_then_the_language(tmp_path, files, expected):
    for rel, text in files.items():
        write(tmp_path, rel, text)
    assert [c["cmd"] for c in checks.detect(tmp_path)] == expected


def test_run_records_exit_code_tail_and_timeout(tmp_path):
    out = checks.run([{"name": "ok", "cmd": "echo hello"}, {"name": "bad", "cmd": "echo boom >&2; exit 3"},
                      {"name": "slow", "cmd": "sleep 5"}], tmp_path, timeout=1)
    assert [(r["name"], r["exit"]) for r in out] == [("ok", 0), ("bad", 3), ("slow", 124)]
    assert out[0]["tail"] == "hello"
    assert "boom" in out[1]["tail"]
    assert "timed out" in out[2]["tail"]


@pytest.mark.parametrize("path, exempt", [
    ("src/export.py", False),
    ("cmd/main.go", False),
    ("tests/test_export.py", True),
    ("src/export_test.go", True),
    ("web/src/Button.test.tsx", True),
    ("pkg/__tests__/a.js", True),
    ("docs/design.md", True),
    ("squire-runs/r1/state.json", True),
])
def test_tests_docs_and_the_run_dir_may_cite_ids(path, exempt):
    assert checks.is_exempt(path, "squire-runs/r1") is exempt


def test_id_leaks_report_added_production_lines_only(repo):
    base = checks.git(repo, "rev-parse", "HEAD").strip()
    write(repo, "calc.py", "def add(a, b):\n    return a + b\n\n\n# R-002: subtract\ndef sub(a, b):\n    return a - b\n")
    write(repo, "tests/test_sub.py", "# covers R-002\nfrom calc import sub\n")
    write(repo, "notes.md", "R-001 and R-002 are done\n")
    write(repo, "enc.py", "ENCODING = 'UTF-8'  # R-0010 is not R-001\n")
    commit(repo, "sub", "calc.py", "tests/test_sub.py", "notes.md", "enc.py")
    leaks = checks.id_leaks(repo, base, ["R-001", "R-002"], "squire-runs/t1")
    assert [(x["file"], x["line"], x["id"]) for x in leaks] == [("calc.py", 5, "R-002"), ("enc.py", 1, "R-001")]


def test_uncommitted_ignores_untracked_files_present_at_base(repo):
    write(repo, "scratch.txt", "mine\n")
    assert checks.uncommitted(repo, ["scratch.txt"], "squire-runs/t1") == []
    write(repo, "calc.py", "def add(a, b):\n    return b + a\n")
    write(repo, "new.py", "x = 1\n")
    write(repo, "squire-runs/t1/state.json", "{}")
    assert sorted(checks.uncommitted(repo, ["scratch.txt"], "squire-runs/t1")) == ["calc.py", "new.py"]
