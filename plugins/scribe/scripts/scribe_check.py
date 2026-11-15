#!/usr/bin/env python3
"""scribe_check: deterministic gates over a set of Markdown documentation pages.

    scribe_check.py <docs path>... [--repo DIR] [--gate NAME,...] [--json]

Gates:

  links     relative links whose file does not exist, and #anchors that match
            no heading or explicit id in the target page
  evidence  <!-- evidence: path:line --> markers whose file is gone or whose
            line is past the end of it
  commands  commands in shell blocks that the repository no longer has: make
            targets, npm/pnpm/yarn scripts, just recipes, local script paths
  readers   pages that never say who they are for
  jargon    acronyms used on a page without being expanded on it

External links are not fetched. Each finding is printed as
`path:line: [gate/severity] message`, or as JSON with --json. Exit status is 1
when anything was found, 0 when clean, 2 on bad usage.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import unquote

GATES = ("links", "evidence", "commands", "readers", "jargon")
SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}
DOC_SUFFIXES = {".md", ".markdown", ".mdx"}

FENCE = re.compile(r"^\s*(```|~~~)\s*([\w+-]*)")
HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
CUSTOM_ID = re.compile(r"\{#([\w-]+)\}\s*$")
HTML_ID = re.compile(r"<a\s+(?:[^>]*?\s)?(?:id|name)=[\"']([^\"']+)[\"']", re.I)
INLINE_CODE = re.compile(r"`[^`]*`")
INLINE_LINK = re.compile(r"!?\[(?:[^\]\\]|\\.)*\]\(\s*(<[^>]*>|[^)\s]+)(?:\s+[\"'(][^)]*)?\)")
REF_DEF = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*(<[^>]*>|\S+)")
EVIDENCE = re.compile(r"<!--\s*evidence:\s*(.*?)\s*-->")
EVIDENCE_FILE = re.compile(r"^([^\s:]+):(\d+)(?:-(\d+))?$")
FRONT_MATTER_READER = re.compile(r"^(reader|audience)\s*:\s*\S", re.I | re.M)
READER_LINE = re.compile(
    r"(?i)^\W*(who this is for|who it is for|reader|audience)\b"
    r"|\bthis (page|guide|tutorial|reference|document|section) is for\b"
)
ACRONYM = re.compile(r"(?<![\w/.-])([A-Z][A-Z0-9]{1,5})s?(?![\w/.-])")
SHELL_LANGS = {"", "bash", "sh", "shell", "console", "zsh", "terminal", "shell-session"}
MAKE_TARGET = re.compile(r"^([A-Za-z0-9_./-]+(?:\s+[A-Za-z0-9_./-]+)*)\s*:(?!=)", re.M)
JUST_RECIPE = re.compile(r"^@?([A-Za-z0-9_-]+)(?:\s+[^:=\n]*)?:(?!=)", re.M)

# Acronyms a technical reader already knows. Anything else gets expanded once.
COMMON_ACRONYMS = {
    "API", "APIS", "CLI", "CPU", "CSS", "CSV", "DNS", "FAQ", "GPU", "HTML", "HTTP", "HTTPS",
    "ID", "IDE", "IP", "JSON", "MIT", "OK", "OS", "PDF", "PR", "RAM", "README", "REST", "SDK",
    "SQL", "SSH", "SSL", "TCP", "TLS", "TODO", "UDP", "UI", "URL", "URLS", "USB", "UTC", "UTF",
    "UX", "XML", "YAML", "TOML", "AND", "OR", "NOT", "GB", "MB", "KB", "TB", "PATH", "HOME",
    "GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "CI", "CD", "EOF", "PID", "LICENSE",
}

SHELL_SPLIT = re.compile(r"\s*(?:&&|\|\||;|\|)\s*")


@dataclass
class Finding:
    gate: str
    severity: str
    path: str
    line: int
    message: str

    def render(self) -> str:
        return f"{self.path}:{self.line}: [{self.gate}/{self.severity}] {self.message}"


# --- reading pages --------------------------------------------------------

class Page:
    """A Markdown page split into prose lines and fenced code blocks."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.text = path.read_text(encoding="utf-8", errors="replace")
        self.lines = self.text.splitlines()
        self.prose: list[tuple[int, str]] = []
        self.blocks: list[tuple[str, list[tuple[int, str]]]] = []
        fence, lang, block = None, "", []
        for number, line in enumerate(self.lines, 1):
            match = FENCE.match(line)
            if fence is None and match:
                fence, lang, block = match.group(1), match.group(2).lower(), []
            elif fence is not None and line.strip().startswith(fence):
                self.blocks.append((lang, block))
                fence = None
            elif fence is not None:
                block.append((number, line))
            else:
                self.prose.append((number, line))

    def front_matter(self) -> str:
        if self.lines[:1] != ["---"]:
            return ""
        for index, line in enumerate(self.lines[1:], 1):
            if line.strip() == "---":
                return "\n".join(self.lines[1:index])
        return ""

    def anchors(self) -> set[str]:
        """Every #fragment this page answers to, GitHub style."""
        found: set[str] = set()
        counts: dict[str, int] = {}
        for _, line in self.prose:
            found.update(HTML_ID.findall(line))
            heading = HEADING.match(line)
            if not heading:
                continue
            title = heading.group(2)
            custom = CUSTOM_ID.search(title)
            if custom:
                found.add(custom.group(1))
                title = CUSTOM_ID.sub("", title)
            slug = slugify(title)
            n = counts.get(slug, 0)
            counts[slug] = n + 1
            found.add(slug if n == 0 else f"{slug}-{n}")
        return found


def slugify(title: str) -> str:
    title = re.sub(r"<[^>]+>", "", title)
    title = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", title)
    title = title.replace("`", "").strip().lower()
    title = re.sub(r"[^\w\- ]", "", title)
    return title.replace(" ", "-")


def collect(paths: list[str]) -> list[Path]:
    pages: list[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            pages.extend(sorted(p for p in path.rglob("*") if p.suffix.lower() in DOC_SUFFIXES
                                and "node_modules" not in p.parts))
        elif path.suffix.lower() in DOC_SUFFIXES and path.is_file():
            pages.append(path)
    return pages


# --- gates ----------------------------------------------------------------

def gate_links(page: Page, cache: dict[Path, Page]) -> list[Finding]:
    findings = []
    for number, line in page.prose:
        stripped = INLINE_CODE.sub("", line)
        targets = [m.group(1) for m in INLINE_LINK.finditer(stripped)]
        ref = REF_DEF.match(stripped)
        if ref:
            targets.append(ref.group(1))
        for target in targets:
            target = target.strip("<>")
            if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.I) or target.startswith("//"):
                continue  # http, https, mailto and other schemes are not fetched
            file_part, _, fragment = target.partition("#")
            file_part = unquote(file_part.split("?")[0])
            if file_part:
                resolved = (page.path.parent / file_part).resolve()
                if not resolved.exists():
                    findings.append(Finding("links", "high", str(page.path), number,
                                            f"broken link: {target} (no such file)"))
                    continue
            else:
                resolved = page.path.resolve()
            if not fragment or resolved.is_dir() or resolved.suffix.lower() not in DOC_SUFFIXES:
                continue
            target_page = cache.get(resolved) or cache.setdefault(resolved, Page(resolved))
            if unquote(fragment) not in target_page.anchors():
                where = "this page" if not file_part else file_part
                findings.append(Finding("links", "high", str(page.path), number,
                                        f"missing anchor: #{fragment} is not a heading in {where}"))
    return findings


def gate_evidence(page: Page, repo: Path) -> list[Finding]:
    findings = []
    for number, line in page.prose:
        # A marker shown as an example in code is not a claim's evidence.
        for marker in EVIDENCE.findall(INLINE_CODE.sub("", line)):
            for item in (part.strip() for part in marker.split(",")):
                anchor = EVIDENCE_FILE.match(item)
                if not anchor:
                    continue  # "ran `cmd`" and other non-file evidence is not checkable here
                rel, start, end = anchor.group(1), int(anchor.group(2)), anchor.group(3)
                target = repo / rel
                if not target.is_file():
                    findings.append(Finding("evidence", "high", str(page.path), number,
                                            f"evidence points at {rel}, which no longer exists"))
                    continue
                length = len(target.read_text(encoding="utf-8", errors="replace").splitlines())
                last = int(end) if end else start
                if start < 1 or last > length:
                    findings.append(Finding("evidence", "medium", str(page.path), number,
                                            f"evidence {item} is past the end of {rel} ({length} lines)"))
    return findings


def make_targets(directory: Path) -> set[str] | None:
    for name in ("GNUmakefile", "makefile", "Makefile"):
        path = directory / name
        if path.is_file():
            targets: set[str] = set()
            for match in MAKE_TARGET.finditer(path.read_text(errors="replace")):
                targets.update(match.group(1).split())
            return targets
    return None


def package_scripts(directory: Path) -> set[str] | None:
    path = directory / "package.json"
    if not path.is_file():
        return None
    try:
        return set((json.loads(path.read_text()).get("scripts") or {}).keys())
    except ValueError:
        return None


def just_recipes(directory: Path) -> set[str] | None:
    for name in ("justfile", "Justfile", ".justfile"):
        path = directory / name
        if path.is_file():
            return set(JUST_RECIPE.findall(path.read_text(errors="replace")))
    return None


def check_command(words: list[str], cwd: Path, repo: Path) -> str | None:
    """Return why a command no longer matches the repository, or None."""
    if not words:
        return None
    tool, args = words[0], [w for w in words[1:] if not w.startswith("-")]
    where = cwd.relative_to(repo) if cwd != repo else Path(".")

    if tool == "make":
        wanted = [a for a in args if "=" not in a]
        targets = make_targets(cwd)
        if targets is None:
            return f"`make` is documented but {where} has no Makefile"
        missing = [t for t in wanted if t not in targets]
        if missing:
            return f"make target `{missing[0]}` does not exist in {where / 'Makefile'}"
    elif tool in ("npm", "pnpm", "yarn", "bun") and args:
        script = None
        if args[0] == "run" and len(args) > 1:
            script = args[1]
        elif tool == "npm" and args[0] in ("test", "start"):
            script = args[0]
        if script:
            scripts = package_scripts(cwd)
            if scripts is None:
                return f"`{tool}` script `{script}` is documented but {where} has no package.json"
            if script not in scripts:
                return f"package.json in {where} has no `{script}` script"
    elif tool == "just" and args:
        recipes = just_recipes(cwd)
        if recipes is None:
            return f"`just` is documented but {where} has no justfile"
        if args[0] not in recipes:
            return f"just recipe `{args[0]}` does not exist"

    script = None
    if tool.startswith(("./", "scripts/", "bin/")):
        script = tool
    elif tool in ("python", "python3", "bash", "sh", "node", "uv") and args:
        candidate = args[1] if tool == "uv" and args[0] == "run" and len(args) > 1 else args[0]
        if re.search(r"\.(py|sh|js|mjs|ts)$", candidate):
            script = candidate
    if script and not (cwd / script).exists():
        return f"`{script}` does not exist in {where}"
    return None


def gate_commands(page: Page, repo: Path) -> list[Finding]:
    findings = []
    for lang, block in page.blocks:
        if lang not in SHELL_LANGS:
            continue
        cwd = repo
        for number, raw in block:
            line = re.sub(r"^\s*[$%>]\s+", "", raw).strip()
            if not line or line.startswith("#"):
                continue
            for part in SHELL_SPLIT.split(line):
                try:
                    words = shlex.split(part, comments=True)
                except ValueError:
                    continue
                while words and re.match(r"^[A-Z_][A-Z0-9_]*=", words[0]):
                    words = words[1:]  # leading VAR=value assignments
                if words[:1] == ["cd"] and len(words) > 1:
                    target = (cwd / words[1]).resolve()
                    if target.is_dir() and repo.resolve() in (target, *target.parents):
                        cwd = repo / target.relative_to(repo.resolve())
                    continue
                problem = check_command(words, cwd, repo)
                if problem:
                    findings.append(Finding("commands", "high", str(page.path), number,
                                            f"stale command `{part}`: {problem}"))
    return findings


def gate_readers(page: Page) -> list[Finding]:
    if FRONT_MATTER_READER.search(page.front_matter()):
        return []
    if any(READER_LINE.search(line) for _, line in page.prose[:40]):
        return []
    return [Finding("readers", "medium", str(page.path), 1,
                    "the page never says who it is for (add `reader:` front matter or a "
                    "'Who this is for' line)")]


def gate_jargon(page: Page, glossary: set[str]) -> list[Finding]:
    prose = "\n".join(INLINE_CODE.sub("", line) for _, line in page.prose
                      if not line.lstrip().startswith(("<!--", "[")))
    findings, seen = [], set()
    for number, line in page.prose:
        if line.lstrip().startswith("<!--"):
            continue
        clean = re.sub(r"\]\([^)]*\)", "]", INLINE_CODE.sub("", line))
        for acronym in ACRONYM.findall(clean):
            if acronym in seen or acronym in COMMON_ACRONYMS or acronym in glossary:
                continue
            seen.add(acronym)
            expanded = (
                re.search(rf"\b{acronym}s?\s*\(", prose)
                or re.search(rf"\(\s*{acronym}s?\s*\)", prose)
                or re.search(rf"\b{acronym}\b\s*(?:is|means|stands for)\b", prose)
            )
            if not expanded:
                findings.append(Finding("jargon", "low", str(page.path), number,
                                        f"{acronym} is used but never expanded or defined on this page"))
    return findings


def glossary_terms(pages: list[Page]) -> set[str]:
    """Acronyms defined on a page named glossary count as defined everywhere."""
    terms: set[str] = set()
    for page in pages:
        if "glossary" in page.path.stem.lower():
            terms.update(ACRONYM.findall(page.text))
    return terms


# --- driver ---------------------------------------------------------------

def run(paths: list[str], repo: Path, gates: list[str]) -> list[Finding]:
    files = collect(paths)
    cache: dict[Path, Page] = {}
    pages = [cache.setdefault(f.resolve(), Page(f)) for f in files]
    # Keep the path the caller gave, not the resolved one, so output stays relative.
    for page, original in zip(pages, files):
        page.path = original
    glossary = glossary_terms(pages) if "jargon" in gates else set()

    findings: list[Finding] = []
    for page in pages:
        if "links" in gates:
            findings += gate_links(page, cache)
        if "evidence" in gates:
            findings += gate_evidence(page, repo)
        if "commands" in gates:
            findings += gate_commands(page, repo)
        if "readers" in gates:
            findings += gate_readers(page)
        if "jargon" in gates:
            findings += gate_jargon(page, glossary)
    findings.sort(key=lambda f: (SEVERITY_RANK[f.severity], f.path, f.line))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scribe_check.py", description=__doc__.split("\n\n")[0])
    parser.add_argument("paths", nargs="+", help="Markdown files or directories to check")
    parser.add_argument("--repo", default=".", help="repository root for commands and evidence (default: .)")
    parser.add_argument("--gate", default=",".join(GATES), help=f"comma-separated subset of {', '.join(GATES)}")
    parser.add_argument("--json", action="store_true", help="print findings as a JSON array")
    args = parser.parse_args(argv)

    gates = [g.strip() for g in args.gate.split(",") if g.strip()]
    unknown = [g for g in gates if g not in GATES]
    if unknown:
        parser.error(f"unknown gate: {', '.join(unknown)}")
    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        parser.error(f"--repo {args.repo} is not a directory")

    findings = run(args.paths, repo, gates)
    if args.json:
        print(json.dumps([asdict(f) for f in findings], indent=2))
    else:
        for finding in findings:
            print(finding.render())
        print(f"{len(findings)} finding(s) across gates: {', '.join(gates)}", file=sys.stderr)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
