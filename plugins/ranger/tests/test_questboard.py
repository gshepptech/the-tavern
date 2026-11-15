"""Ranger reading prior work from, and writing attempts to, the .questboard workspace.

Ranger is the only plugin in the marketplace that both reads and writes the
shared workspace. It reads at survey time so a scout does not re-propose work
some earlier run already tried and abandoned, and it writes an `attempt` note
on every committed item and every quarantined one. See docs/questboard-contract.md.

The lead drives an unattended loop, sometimes overnight, with permissions
bypassed. That raises the bar on this particular integration: a side channel
that can throw is a side channel that can end somebody's night. So the tests
below are mostly about the workspace being absent, empty or damaged, and about
the write never being able to affect a cycle.

The exhaustive semantics of questboard.py itself live in plugins/sage/tests/, and
every vendored copy is pinned to that one by the drift check at the bottom.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = PLUGIN_ROOT.parent.parent
QUESTBOARD = PLUGIN_ROOT / "scripts" / "questboard.py"
RUN_MD = PLUGIN_ROOT / "commands" / "run.md"
SCOUT_MD = PLUGIN_ROOT / "agents" / "scout.md"

# The exact command STEP 3a tells the lead to run.
SURVEY_READ = ("read", "--limit", "40")


def run(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(QUESTBOARD), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=30,
    )


def note(cwd: Path, name: str, content: str) -> None:
    directory = cwd / ".questboard" / "notes"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(content, encoding="utf-8")


def attempt(title: str, outcome: str, stamp: str = "20260727T103015Z") -> str:
    return json.dumps(
        {
            "questboard": 1,
            "id": f"{stamp}-ranger-a3f4",
            "kind": "attempt",
            "plugin": "ranger",
            "created": "2026-07-27T10:30:15Z",
            "title": title,
            "outcome": outcome,
        }
    )


# ---------------------------------------------------------------------------
# STEP 3a SURVEY: the three absence cases all produce an empty prior_work
# ---------------------------------------------------------------------------


def test_survey_read_on_an_absent_workspace_yields_no_prior_work(tmp_path: Path) -> None:
    result = run(*SURVEY_READ, cwd=tmp_path)
    assert result.returncode == 0
    assert json.loads(result.stdout) == []


def test_survey_read_on_an_empty_workspace_yields_no_prior_work(tmp_path: Path) -> None:
    (tmp_path / ".questboard" / "notes").mkdir(parents=True)
    result = run(*SURVEY_READ, cwd=tmp_path)
    assert result.returncode == 0
    assert json.loads(result.stdout) == []


def test_survey_read_on_a_damaged_workspace_yields_no_prior_work(tmp_path: Path) -> None:
    note(tmp_path, "20260727T090000Z-ranger-0001.json", "not json{")
    note(tmp_path, "20260727T100000Z-sellsword-0002.json", "")
    note(tmp_path, "20260727T110000Z-cleric-0003.json", '{"questboard": 4, "id": "x"}')
    note(tmp_path, "20260727T120000Z-ranger-0004.json", attempt("no outcome", outcome=""))

    result = run(*SURVEY_READ, cwd=tmp_path)
    assert result.returncode == 0
    assert json.loads(result.stdout) == []


def test_survey_read_never_creates_the_workspace(tmp_path: Path) -> None:
    """An unattended run must not opt a project into a directory it never had."""
    run(*SURVEY_READ, cwd=tmp_path)
    assert not (tmp_path / ".questboard").exists()


def test_survey_read_never_touches_a_damaged_note(tmp_path: Path) -> None:
    note(tmp_path, "20260727T090000Z-ranger-0001.json", "not json{")
    before = sorted(
        (p.name, p.read_bytes()) for p in (tmp_path / ".questboard" / "notes").iterdir()
    )
    run(*SURVEY_READ, cwd=tmp_path)
    after = sorted(
        (p.name, p.read_bytes()) for p in (tmp_path / ".questboard" / "notes").iterdir()
    )
    assert before == after


def test_one_bad_note_does_not_hide_the_prior_work_that_matters(tmp_path: Path) -> None:
    """The case that would actually cost a night: a corrupt file suppressing
    the record of three failed attempts, so the loop tries a fourth."""
    note(tmp_path, "20260727T090000Z-sellsword-0001.json", "not json{")
    note(
        tmp_path,
        "20260727T100000Z-ranger-0002.json",
        attempt("Rewrite the checkout reducer", "abandoned", "20260727T100000Z"),
    )
    notes = json.loads(run(*SURVEY_READ, cwd=tmp_path).stdout)
    assert [n["title"] for n in notes] == ["Rewrite the checkout reducer"]
    assert notes[0]["outcome"] == "abandoned"


def test_the_survey_read_honours_its_limit(tmp_path: Path) -> None:
    for index in range(50):
        stamp = f"20260727T{index // 60:02d}{index % 60:02d}00Z"
        note(tmp_path, f"{stamp}-ranger-{index:04d}.json", attempt(f"item {index}", "done", stamp))
    notes = json.loads(run(*SURVEY_READ, cwd=tmp_path).stdout)
    assert len(notes) == 40


# ---------------------------------------------------------------------------
# STEP 3h COMMIT and the stall path: writing an attempt
# ---------------------------------------------------------------------------


def test_a_committed_item_is_recorded_as_done(tmp_path: Path) -> None:
    result = run(
        "write", "--plugin", "ranger", "--kind", "attempt", "--outcome", "done",
        "--title", "Fix the empty state on /settings",
        "--summary", "Added the empty state. 3f2a1b0.",
        "--tag", "ui-ux",
        cwd=tmp_path,
    )
    assert result.returncode == 0
    notes = json.loads(run("read", cwd=tmp_path).stdout)
    assert notes[0]["kind"] == "attempt"
    assert notes[0]["outcome"] == "done"
    assert notes[0]["plugin"] == "ranger"


def test_a_quarantined_item_is_recorded_as_abandoned(tmp_path: Path) -> None:
    result = run(
        "write", "--plugin", "ranger", "--kind", "attempt", "--outcome", "abandoned",
        "--title", "Rewrite the checkout reducer",
        "--summary", "Three cycles, reviewer rejected each. Blocked on the legacy adapter.",
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert json.loads(run("read", cwd=tmp_path).stdout)[0]["outcome"] == "abandoned"


def test_a_cycles_worth_of_writes_never_collide(tmp_path: Path) -> None:
    """One note per cycle, and a long run is many cycles. Filenames carry two
    random bytes precisely so nothing has to lock."""
    for index in range(20):
        run(
            "write", "--plugin", "ranger", "--kind", "attempt", "--outcome", "done",
            "--title", f"item {index}",
            cwd=tmp_path,
        )
    assert len(json.loads(run("read", cwd=tmp_path).stdout)) == 20


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_a_write_that_cannot_happen_does_not_end_the_cycle(tmp_path: Path) -> None:
    tmp_path.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        result = run(
            "write", "--plugin", "ranger", "--kind", "attempt", "--outcome", "done",
            "--title", "x",
            cwd=tmp_path,
        )
        assert result.returncode == 0
    finally:
        tmp_path.chmod(stat.S_IRWXU)


# ---------------------------------------------------------------------------
# The prose contract: what run.md and scout.md commit the lead to
# ---------------------------------------------------------------------------


def test_run_md_uses_exactly_the_read_command_this_file_tests() -> None:
    """If the survey step drifts to different arguments, these tests stop
    covering what the lead actually runs."""
    text = RUN_MD.read_text(encoding="utf-8")
    assert 'questboard.py" read --limit 40' in text


def test_run_md_states_all_three_absence_cases_are_the_same(tmp_path: Path) -> None:
    text = RUN_MD.read_text(encoding="utf-8")
    assert "Treat all three the same way" in text
    assert "Never create `.questboard/` to read it" in text


def test_run_md_forbids_a_failed_write_from_affecting_a_cycle() -> None:
    text = RUN_MD.read_text(encoding="utf-8")
    assert "The write cannot fail the cycle." in text


def test_run_md_ignores_questboard_before_git_clean_can_delete_it() -> None:
    """STEP 3f runs `git clean -fd`. An untracked .questboard/ would go with it,
    taking every other plugin's notes. The gitignore line has to be added in
    preflight, and only when the directory already exists."""
    text = RUN_MD.read_text(encoding="utf-8")
    ignore_step = text.index("grep -qxF '.questboard/' .gitignore")
    clean_step = text.index("git clean -fd` new files")
    assert ignore_step < clean_step
    assert "test -d .questboard &&" in text


def test_scout_is_given_prior_work_and_told_not_to_ground_on_it() -> None:
    run_text = RUN_MD.read_text(encoding="utf-8")
    scout_text = SCOUT_MD.read_text(encoding="utf-8")
    assert "prior_work:" in run_text
    assert "prior_work" in scout_text
    assert "Never cite `prior_work` as your grounding." in scout_text


def test_scout_knows_an_empty_prior_work_is_normal() -> None:
    scout_text = SCOUT_MD.read_text(encoding="utf-8")
    assert "almost always empty, and that is the normal case" in scout_text


# ---------------------------------------------------------------------------
# The note templates the lead has to be able to read
# ---------------------------------------------------------------------------
#
# Sellsword, Cleric and Seer write their notes with the Write tool from a JSON
# template in their own command file, rather than shelling out to questboard.py.
# That is the right call for three plugins that ship no code and read nothing
# back, but it means the template IS the implementation, and a typo in one
# ships a note no reader will ever accept.
#
# Ranger is the reader those notes are written for, so the templates are its
# input contract, and checking them here is checking its own inputs. The plugins
# are optional: a checkout with only Ranger in it skips these.

sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))
import questboard  # noqa: E402  (path set above, deliberately)

TEMPLATE_HEADING = "### Leave a note in the shared workspace"
PROSE_WRITERS = {
    "sellsword": Path("sellsword") / "commands" / "do.md",
    "cleric": Path("cleric") / "commands" / "run.md",
    "seer": Path("seer") / "commands" / "review.md",
}


def note_template(command_file: Path) -> str:
    """The JSON block under the command file's note-writing heading."""
    text = command_file.read_text(encoding="utf-8")
    section = text[text.index(TEMPLATE_HEADING) :]
    opening = section.index("```json") + len("```json")
    return section[opening : section.index("```", opening)]


def fill(template: str, plugin: str) -> str:
    """Substitute the <angle bracket> placeholders an agent would fill in."""
    template = re.sub(
        r'"created":\s*"<[^"]*>"', '"created": "2026-07-27T10:30:15Z"', template
    )
    template = re.sub(
        r'"id":\s*"<[^"]*>"', f'"id": "20260727T103015Z-{plugin}-a3f4"', template
    )
    return re.sub(r"<[^>\"]*>", "placeholder", template)


@pytest.mark.parametrize("plugin,relative", sorted(PROSE_WRITERS.items()))
def test_a_prose_written_note_template_produces_a_readable_note(
    plugin: str, relative: Path
) -> None:
    command_file = REPO_ROOT / "plugins" / relative
    if not command_file.is_file():
        pytest.skip(f"{plugin} is not present in this checkout")

    template = note_template(command_file)
    # The template has to tell the agent the exact timestamp format, because
    # nothing validates it at write time.
    assert "YYYY-MM-DDTHH:MM:SSZ" in template

    note_obj = json.loads(fill(template, plugin))
    assert questboard.note_problems(note_obj) == [], note_obj
    assert note_obj["plugin"] == plugin
    assert note_obj["kind"] in questboard.KINDS


@pytest.mark.parametrize("plugin,relative", sorted(PROSE_WRITERS.items()))
def test_a_prose_writer_uses_the_contract_filename_shape(
    plugin: str, relative: Path
) -> None:
    command_file = REPO_ROOT / "plugins" / relative
    if not command_file.is_file():
        pytest.skip(f"{plugin} is not present in this checkout")
    text = command_file.read_text(encoding="utf-8")
    assert f".questboard/notes/<that timestamp>-{plugin}-<4 hex chars you pick>.json" in text


@pytest.mark.parametrize("plugin,relative", sorted(PROSE_WRITERS.items()))
def test_a_prose_writer_is_told_the_write_cannot_affect_its_run(
    plugin: str, relative: Path
) -> None:
    command_file = REPO_ROOT / "plugins" / relative
    if not command_file.is_file():
        pytest.skip(f"{plugin} is not present in this checkout")
    section = command_file.read_text(encoding="utf-8")
    section = section[section.index(TEMPLATE_HEADING) :]
    assert "Never let this" in section
    assert "One file, nothing else in `.questboard/`." in section or "carry on" in section


def test_sellsword_is_told_not_to_put_operational_detail_in_a_note() -> None:
    """Sellsword reaches real infrastructure. A note is a project-local file other
    tools read, so it is the wrong place for anything from .sellsword/access.yml."""
    for relative in (Path("sellsword") / "commands" / "do.md", Path("sellsword") / "commands" / "goal.md"):
        command_file = REPO_ROOT / "plugins" / relative
        if not command_file.is_file():
            pytest.skip("sellsword is not present in this checkout")
        text = command_file.read_text(encoding="utf-8")
        assert "credentials" in text and "access.yml" in text


# ---------------------------------------------------------------------------
# Vendoring and declaration
# ---------------------------------------------------------------------------


def test_ranger_copy_of_questboard_matches_every_other_copy() -> None:
    copies = sorted(REPO_ROOT.glob("plugins/*/scripts/questboard.py"))
    assert QUESTBOARD in copies
    digests = {
        str(path.relative_to(REPO_ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in copies
    }
    assert len(set(digests.values())) == 1, f"vendored copies have drifted: {digests}"


def test_ranger_declares_what_it_reads_and_writes() -> None:
    declaration = json.loads((PLUGIN_ROOT / "questboard.json").read_text())
    assert declaration == {
        "questboard": 1,
        "plugin": "ranger",
        "reads": ["spec", "finding", "attempt"],
        "writes": ["attempt"],
    }
