from __future__ import annotations

from pathlib import Path

import pytest

from conftest import SPEC
from spec_index import index


def ids(text: str) -> list[str]:
    return [r["id"] for r in index(text)["requirements"]]


def test_heading_requirements_carry_text_and_acceptance():
    reqs = index(SPEC)["requirements"]
    assert [r["id"] for r in reqs] == ["R-001", "R-002"]
    first = reqs[0]
    assert first["title"] == "Add"
    assert "MUST return the sum" in first["text"]
    assert "A-001" not in first["text"], "Source lines are references, not requirement text"
    assert first["acceptance"] == ["`add(2, 3)` returns 5.", "`add(-1, 1)` returns 0."]
    assert first["line"] == 7


def test_list_item_requirements_take_nested_items_as_criteria():
    spec = """## Requirements

- **FR-1**: `slug(s)` lowercases its input.
  - `slug("AB")` is `"ab"`.
  - An empty string stays empty.
- **FR-2**: `slug(s)` replaces spaces with dashes.
"""
    reqs = index(spec)["requirements"]
    assert [r["id"] for r in reqs] == ["FR-1", "FR-2"]
    assert reqs[0]["acceptance"] == ['`slug("AB")` is `"ab"`.', "An empty string stays empty."]
    assert reqs[1]["acceptance"] == []


def test_list_item_with_an_acceptance_block():
    spec = """- FR-7: Export orders as CSV.
  Acceptance:
  - The header row is `id,total`.
"""
    (req,) = index(spec)["requirements"]
    assert req["acceptance"] == ["The header row is `id,total`."]
    assert req["text"] == "Export orders as CSV."


def test_table_rows_define_requirements():
    spec = """| ID | Requirement | Acceptance |
|----|-------------|------------|
| NFR-1 | p95 latency under 200 ms | a 100-request run reports p95 < 200 ms |
"""
    (req,) = index(spec)["requirements"]
    assert req["id"] == "NFR-1"
    assert req["acceptance"] == ["a 100-request run reports p95 < 200 ms"]


@pytest.mark.parametrize("noise", [
    "See R-009 for the details.\n",
    "```\n### R-009: inside a fence\n```\n",
    "## Appendix: notes\n\n### R-009: an appendix entry\n",
    "---\nid: R-009\n---\n",
])
def test_references_fences_appendices_and_frontmatter_are_not_requirements(noise):
    real = "### R-001: real\n\nAcceptance:\n- holds\n\n"
    text = noise + real if noise.startswith("---") else real + noise
    assert ids(text) == ["R-001"]


def test_a_heading_after_the_appendix_is_indexed_again():
    spec = "## Appendix\n\n### R-009: skipped\n\n# Next part\n\n### R-010: kept\n"
    assert ids(spec) == ["R-010"]


def test_duplicate_and_missing_acceptance_are_warned():
    spec = "### R-001: one\n\ntext\n\n### R-001: again\n\nmore\n"
    out = index(spec)
    assert ids(spec) == ["R-001"]
    assert any("defined twice" in w for w in out["warnings"])
    assert any("no acceptance criteria" in w for w in out["warnings"])


def test_a_spec_without_ids_indexes_nothing():
    assert index("# Notes\n\n- make it fast\n- make it nice\n")["requirements"] == []


def test_the_readme_example_mixes_heading_and_list_requirements():
    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
    example = readme.split("```markdown\n", 1)[1].split("```", 1)[0]
    reqs = index(example)["requirements"]
    assert [r["id"] for r in reqs] == ["R-001", "FR-2"]
    assert len(reqs[0]["acceptance"]) == 2
    assert reqs[1]["acceptance"] == ["A request with no session gets 401.", "A non-admin session gets 403."]
