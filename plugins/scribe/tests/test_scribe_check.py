"""Tests for scribe_check.py against small documentation trees built per test."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "scribe_check.py"
sys.path.insert(0, str(SCRIPT.parent))
import scribe_check  # noqa: E402

READER = "---\nreader: a developer installing the tool for the first time\n---\n\n"


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "Makefile").write_text(
        "BIN := app\n.PHONY: build test\nbuild:\n\tgo build\ntest lint: build\n\tgo test\n"
    )
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "package.json").write_text(json.dumps({"scripts": {"dev": "vite", "test": "vitest"}}))
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "seed.sh").write_text("#!/bin/sh\n")
    (tmp_path / "src.py").write_text("\n".join(f"line {i}" for i in range(10)))
    return tmp_path


def write(repo: Path, name: str, body: str, reader: bool = True) -> Path:
    path = repo / "docs" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text((READER if reader else "") + body)
    return path


def check(repo: Path, *gates: str) -> list[scribe_check.Finding]:
    return scribe_check.run([str(repo / "docs")], repo, list(gates or scribe_check.GATES))


def messages(findings) -> list[str]:
    return [f.message for f in findings]


# --- links ------------------------------------------------------------------

def test_links_clean(repo):
    write(repo, "a.md", "# Install\n\n## Step one\n\nSee [b](b.md#usage), [here](#step-one) and "
                        "[site](https://example.com/x#y).\n")
    write(repo, "b.md", "# B\n\n## Usage\n")
    assert check(repo, "links") == []


def test_broken_file_link(repo):
    write(repo, "a.md", "See [setup](setup.md) and ![img](img/shot.png).\n")
    found = messages(check(repo, "links"))
    assert any("setup.md (no such file)" in m for m in found)
    assert any("img/shot.png" in m for m in found)


def test_missing_anchor_in_other_page_and_same_page(repo):
    write(repo, "a.md", "# A\n\n[x](b.md#nope) [y](#also-nope)\n")
    write(repo, "b.md", "# B\n")
    found = messages(check(repo, "links"))
    assert "missing anchor: #nope is not a heading in b.md" in found
    assert "missing anchor: #also-nope is not a heading in this page" in found


@pytest.mark.parametrize(
    ("heading", "anchor"),
    [
        ("## Getting `started` quickly!", "getting-started-quickly"),
        ("## Config: env vars", "config-env-vars"),
        ("## Custom {#my-id}", "my-id"),
        ("<a id=\"explicit\"></a>", "explicit"),
    ],
)
def test_anchor_styles(repo, heading, anchor):
    write(repo, "a.md", f"{heading}\n\n[jump](#{anchor})\n")
    assert check(repo, "links") == []


def test_duplicate_headings_get_numbered(repo):
    write(repo, "a.md", "## Example\n\n## Example\n\n[second](#example-1) [third](#example-2)\n")
    assert messages(check(repo, "links")) == ["missing anchor: #example-2 is not a heading in this page"]


def test_links_in_code_are_ignored(repo):
    write(repo, "a.md", "Use `[x](gone.md)`.\n\n```\n[y](also-gone.md)\n```\n")
    assert check(repo, "links") == []


def test_reference_definitions_are_checked(repo):
    write(repo, "a.md", "See [the guide][g].\n\n[g]: missing-guide.md\n")
    assert any("missing-guide.md" in m for m in messages(check(repo, "links")))


# --- evidence ---------------------------------------------------------------

def test_evidence_markers(repo):
    write(repo, "a.md",
          "It retries three times. <!-- evidence: src.py:3 -->\n"
          "It logs. <!-- evidence: src.py:2-40 -->\n"
          "It caches. <!-- evidence: gone.py:1 -->\n"
          "It prints help. <!-- evidence: ran `app --help` -->\n")
    found = messages(check(repo, "evidence"))
    assert found == [
        "evidence points at gone.py, which no longer exists",
        "evidence src.py:2-40 is past the end of src.py (10 lines)",
    ]


def test_evidence_examples_in_code_are_ignored(repo):
    write(repo, "a.md", "Write `<!-- evidence: gone.py:1 -->` after a claim.\n\n"
                        "```\nPort 80. <!-- evidence: gone.py:2 -->\n```\n")
    assert check(repo, "evidence") == []


# --- commands ---------------------------------------------------------------

def test_commands_clean(repo):
    write(repo, "a.md", "```bash\n$ make build test\nmake -j4 lint\nBIN=x make build\n"
                        "./scripts/seed.sh --fast\ncd web && npm run dev\nnpm test\n```\n")
    assert check(repo, "commands") == []


def test_stale_make_target(repo):
    write(repo, "a.md", "```sh\nmake deploy\n```\n")
    [finding] = check(repo, "commands")
    assert "make target `deploy` does not exist" in finding.message
    assert finding.line == 6


def test_stale_npm_script_respects_cd(repo):
    write(repo, "a.md", "```bash\ncd web\nnpm run build\n```\n")
    [finding] = check(repo, "commands")
    assert "package.json in web has no `build` script" in finding.message


def test_missing_script_path(repo):
    write(repo, "a.md", "```\npython3 scripts/migrate.py\nbash scripts/seed.sh\n```\n")
    assert messages(check(repo, "commands")) == [
        "stale command `python3 scripts/migrate.py`: `scripts/migrate.py` does not exist in ."
    ]


def test_no_makefile(repo):
    (repo / "Makefile").unlink()
    write(repo, "a.md", "```bash\nmake build\n```\n")
    assert "has no Makefile" in check(repo, "commands")[0].message


def test_non_shell_blocks_are_skipped(repo):
    write(repo, "a.md", "```python\nmake deploy\n```\n")
    assert check(repo, "commands") == []


def test_just_recipes(repo):
    (repo / "justfile").write_text("build:\n  go build\n\nrelease version:\n  echo {{version}}\n")
    write(repo, "a.md", "```bash\njust build\njust release 1.2\njust publish\n```\n")
    assert messages(check(repo, "commands")) == [
        "stale command `just publish`: just recipe `publish` does not exist"
    ]


# --- readers and jargon -----------------------------------------------------

@pytest.mark.parametrize(
    ("body", "flagged"),
    [
        ("# Page\n\nText.\n", True),
        ("# Page\n\n**Who this is for:** operators.\n", False),
        ("# Page\n\nThis guide is for people deploying to production.\n", False),
    ],
)
def test_readers(repo, body, flagged):
    write(repo, "a.md", body, reader=False)
    assert bool(check(repo, "readers")) is flagged


def test_reader_front_matter(repo):
    write(repo, "a.md", "# Page\n")
    assert check(repo, "readers") == []


def test_jargon(repo):
    write(repo, "a.md",
          "The CRD controls it. Run the CLI over HTTP.\n"
          "A PVC (persistent volume claim) holds data.\n"
          "Service level objective (SLO) targets matter. The SLO is 99.9%.\n"
          "`RBAC` in code is fine.\n")
    found = check(repo, "jargon")
    assert messages(found) == ["CRD is used but never expanded or defined on this page"]
    assert found[0].line == 5


def test_glossary_defines_terms_everywhere(repo):
    write(repo, "a.md", "The CRD controls it.\n")
    write(repo, "glossary.md", "## CRD\n\nCustom resource definition.\n")
    assert check(repo, "jargon") == []


# --- driver -----------------------------------------------------------------

def test_findings_ranked_by_severity(repo):
    write(repo, "a.md", "The XYZ thing. [x](gone.md)\n", reader=False)
    gates = [f.gate for f in check(repo)]
    assert gates == ["links", "readers", "jargon"]


def test_cli_exit_codes_and_json(repo):
    write(repo, "a.md", "# A\n\n[x](gone.md)\n")
    run = lambda *args: subprocess.run(  # noqa: E731
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True, cwd=repo
    )
    dirty = run("docs", "--json", "--gate", "links")
    assert dirty.returncode == 1
    [finding] = json.loads(dirty.stdout)
    assert finding["path"] == "docs/a.md" and finding["line"] == 7

    (repo / "docs" / "a.md").write_text(READER + "# A\n")
    clean = run("docs", "--gate", "links")
    assert clean.returncode == 0
    assert run("docs", "--gate", "bogus").returncode == 2
