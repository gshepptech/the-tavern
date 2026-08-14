#!/usr/bin/env bash
#
# install-profile.sh - install a named set of The Tavern plugins in one step.
#
# Profiles are this repo's own convention, not a Claude Code feature. There is no
# bundle, group or collection field in the marketplace manifest schema, so a
# profile is nothing more than a list of plugin names that this script feeds to
# the supported CLI one at a time:
#
#     claude plugin marketplace add gshepptech/the-tavern --scope <scope>
#     claude plugin install <name>@the-tavern --scope <scope>
#
# Both commands are idempotent and both are what /plugin install does under the
# hood, so nothing here is doing anything you could not type yourself. The value
# is that you type one line instead of choosing from a table of nine tools you
# have never used, and that the warnings for the dangerous ones are unavoidable.
#
# Deliberately not offered: a curl-pipe-to-shell one-liner. Every plugin in this
# marketplace runs code on your machine, and a project that ships hooks has no
# business teaching people to execute remote scripts unread. If you have not
# cloned the repo, docs/profiles.md gives the equivalent copy-paste block.
#
# Written for bash 3.2, which is what macOS ships. No associative arrays.

set -euo pipefail

MARKETPLACE="the-tavern"
MARKETPLACE_SOURCE="gshepptech/the-tavern"

PROFILES="daily pipeline review unattended all"

# Plugins that run with permissions bypassed in their unattended modes. Any
# profile containing one of these earns the hard warning and a confirmation.
UNATTENDED_PLUGINS="sellsword ranger"

scope="user"
dry_run=0
assume_yes=0
profile=""

# --- profile definitions -----------------------------------------------------
#
# One function, one source of truth. docs/profiles.md is checked against this
# list by .github/scripts/check_profiles.py, so the two cannot drift.

profile_plugins() {
  case "$1" in
    daily)      echo "warden sage cleric" ;;
    pipeline)   echo "sage smith" ;;
    review)     echo "seer cleric" ;;
    unattended) echo "sellsword ranger" ;;
    all)        echo "sage smith warden sellsword cleric scout tactician seer ranger" ;;
    *)          return 1 ;;
  esac
}

profile_blurb() {
  case "$1" in
    daily)      echo "Solo, on a codebase you did not write. The everyday set." ;;
    pipeline)   echo "Spec a feature properly, then have it built out. Needs setup." ;;
    review)     echo "Assess and tidy. Nothing writes code unprompted." ;;
    unattended) echo "Work that runs while you are away. BYPASSES PERMISSIONS." ;;
    all)        echo "The whole crew. Includes both unattended tools." ;;
    *)          return 1 ;;
  esac
}

# --- output helpers ----------------------------------------------------------

say()  { printf '%s\n' "$*"; }
warn() { printf '%s\n' "$*" >&2; }
die()  { printf 'error: %s\n' "$*" >&2; exit 1; }

usage() {
  cat <<'USAGE'
Install a named set of The Tavern plugins.

  ./scripts/install-profile.sh <profile> [options]

Profiles:
  daily        warden, sage, cleric       Solo, on a codebase you did not write
  pipeline     sage, smith            Spec a feature, then build it out
  review       seer, cleric         Assess and tidy, minimal writing
  unattended   sellsword, ranger            Runs while you are away. Bypasses permissions
  all          all nine               The whole crew

Options:
  --scope <user|project|local>  Where to record the install. Default: user.
                                project writes .claude/settings.json, which is
                                committed and therefore applies to your whole team.
  --dry-run                     Print the commands that would run, run nothing.
  --yes                         Skip the confirmation prompt. Required for the
                                unattended and all profiles in a non-interactive
                                shell.
  --list                        Print the profiles and their contents.
  --help                        This.

Every plugin also installs on its own, and always will:

  claude plugin install sage@the-tavern

See docs/profiles.md for what each profile leaves out and why.
USAGE
}

list_profiles() {
  say "The Tavern install profiles"
  say ""
  for p in $PROFILES; do
    printf '  %-12s %s\n' "$p" "$(profile_plugins "$p")"
    printf '  %-12s %s\n' "" "$(profile_blurb "$p")"
    say ""
  done
  say "Profiles are a convention of this repo, not a Claude Code feature."
  say "Each one expands to plain 'claude plugin install' calls. Run with"
  say "--dry-run to see exactly what would happen."
}

# --- argument parsing --------------------------------------------------------

while [ $# -gt 0 ]; do
  case "$1" in
    --scope)
      [ $# -ge 2 ] || die "--scope needs a value (user, project or local)"
      scope="$2"
      shift 2
      ;;
    --scope=*)
      scope="${1#--scope=}"
      shift
      ;;
    --dry-run) dry_run=1; shift ;;
    --yes|-y)  assume_yes=1; shift ;;
    --list)    list_profiles; exit 0 ;;
    --help|-h) usage; exit 0 ;;
    -*)        die "unknown option: $1 (try --help)" ;;
    *)
      [ -z "$profile" ] || die "one profile at a time, got '$profile' and '$1'"
      profile="$1"
      shift
      ;;
  esac
done

case "$scope" in
  user|project|local) ;;
  *) die "--scope must be user, project or local (got '$scope')" ;;
esac

if [ -z "$profile" ]; then
  usage
  exit 2
fi

plugins="$(profile_plugins "$profile" 2>/dev/null)" || {
  warn "error: unknown profile '$profile'"
  warn ""
  warn "Known profiles: $PROFILES"
  warn "Run with --list to see what each one contains."
  exit 2
}

# --- preflight ---------------------------------------------------------------

if [ "$dry_run" -eq 0 ] && ! command -v claude >/dev/null 2>&1; then
  die "'claude' is not on PATH. Install Claude Code first: https://docs.claude.com/en/docs/claude-code"
fi

contains_unattended=0
for p in $plugins; do
  for u in $UNATTENDED_PLUGINS; do
    [ "$p" = "$u" ] && contains_unattended=1
  done
done

# --- what you are about to do ------------------------------------------------

say "Profile:   $profile"
say "Plugins:   $plugins"
say "Scope:     $scope"
case "$scope" in
  project) say "           (writes .claude/settings.json - committed, applies to your team)" ;;
  local)   say "           (writes .claude/settings.local.json - gitignored, just you)" ;;
  user)    say "           (writes ~/.claude/settings.json - you, in every project)" ;;
esac
say ""

case " $plugins " in
  *" warden "*)
    say "Note: Warden installs UserPromptSubmit and Stop hooks that run local scripts"
    say "on every prompt and every response, in every project, from the moment it is"
    say "installed. That is the point of it, but it is not dormant like the others."
    say "'/warden:off' silences it; 'claude plugin uninstall warden@the-tavern' removes it."
    say ""
    ;;
esac

if [ "$contains_unattended" -eq 1 ]; then
  warn "WARNING - this profile includes tools that run with permissions bypassed."
  warn ""
  warn "  Ranger's headless runner and '/sellsword:goal' execute tools without asking:"
  warn "  file writes, shell commands, network calls. There is no human present to"
  warn "  answer a prompt, so nothing prompts. Sellsword reaches real infrastructure over"
  warn "  SSH. Ranger's git guard still hard-denies push, but only git is guarded."
  warn ""
  warn "  Ranger is also uncapped by default. '--max-hours=N' is the only flag that"
  warn "  ends a run on its own; '--max-cycles=N' counts shipped items, so a run that"
  warn "  keeps reverting never reaches it."
  warn ""
  warn "  Run unattended modes in a container, a VM, or a throwaway clone. Not on a"
  warn "  machine you care about while you walk away."
  warn ""
  warn "  Installing them is safe. Nothing runs until you invoke it. This warning is"
  warn "  about the first time you type '/ranger:run' or '/sellsword:goal'."
  warn ""
fi

if [ "$dry_run" -eq 1 ]; then
  say "Dry run. These are the commands that would run:"
  say ""
  say "  claude plugin marketplace add $MARKETPLACE_SOURCE --scope $scope"
  for p in $plugins; do
    say "  claude plugin install ${p}@${MARKETPLACE} --scope $scope"
  done
  say ""
  say "Nothing was changed."
  exit 0
fi

if [ "$contains_unattended" -eq 1 ] && [ "$assume_yes" -eq 0 ]; then
  if [ -t 0 ]; then
    printf 'Continue? [y/N] '
    read -r reply
    case "$reply" in
      y|Y|yes|YES) ;;
      *) say "Nothing was changed."; exit 1 ;;
    esac
    say ""
  else
    die "the '$profile' profile includes a permissions-bypassing tool and stdin is not a terminal. Re-run with --yes if that is what you want."
  fi
fi

# --- install -----------------------------------------------------------------
#
# One plugin per invocation, deliberately. 'claude plugin install a b c' takes
# the first argument and silently discards the rest - no error, no warning, and
# you find out two plugins later. Verified against Claude Code 2.1.220.

say "Adding the marketplace..."
if ! claude plugin marketplace add "$MARKETPLACE_SOURCE" --scope "$scope"; then
  die "could not add the marketplace. Check your network and that you can reach github.com."
fi

installed=""
failed=""
for p in $plugins; do
  say ""
  say "Installing ${p}..."
  if claude plugin install "${p}@${MARKETPLACE}" --scope "$scope"; then
    installed="$installed $p"
  else
    failed="$failed $p"
  fi
done

# --- report ------------------------------------------------------------------

say ""
say "----------------------------------------"
if [ -n "$failed" ]; then
  warn "Installed:${installed:-  none}"
  warn "FAILED:   $failed"
  warn ""
  warn "A failure here is usually a stale local copy of the marketplace. Try:"
  warn "  claude plugin marketplace update $MARKETPLACE"
  warn "then re-run this script. It is idempotent - the ones that worked stay put."
  exit 1
fi

say "Installed:$installed"
say ""
say "Next:"

case " $plugins " in *" smith "*)
  say "  - Smith needs one-time project setup: run '/smith:setup', then restart"
  say "    Claude Code. It writes three MCP servers into .mcp.json and needs"
  say "    python3 on PATH. Smith will not build until you have done this."
  ;;
esac
case " $plugins " in *" scout "*)
  say "  - Scout needs one-time project setup: run '/scout:init' inside the project"
  say "    you want to test, then restart Claude Code. It downloads browsers"
  say "    (several hundred MB) and needs a dev server running before any"
  say "    browser command works."
  ;;
esac
case " $plugins " in *" warden "*)
  say "  - Warden is already working. It applies from your next turn, no command needed."
  ;;
esac
case " $plugins " in *" cleric "*)
  say "  - Cleric refuses to start on a dirty tree. Commit or stash, then '/cleric:run'"
  say "    for a dry run that changes nothing."
  ;;
esac
case " $plugins " in *" ranger "*)
  say "  - Ranger: start with '/ranger:run <brief> --dry-run'. It changes nothing and"
  say "    shows you the backlog and the top plan. Read that before an unattended run."
  ;;
esac
case " $plugins " in *" sellsword "*)
  say "  - Sellsword: '/sellsword:do <problem>' is the attended mode and asks before side effects."
  say "    '/sellsword:goal' is the unattended one. Start with '/sellsword:do'."
  ;;
esac
case " $plugins " in *" sage "*)
  say "  - Sage: '/sage:plan \"<feature>\"'. It is interactive and will ask you"
  say "    questions - brownfield mode aborts if nobody answers."
  ;;
esac
case " $plugins " in *" seer "*)
  say "  - Seer: '/seer:review <path>'. Start narrow. It never edits anything."
  ;;
esac
case " $plugins " in *" tactician "*)
  say "  - Tactician: '/tactician:make <task>' writes a Workflow script to .claude/workflows/."
  ;;
esac

say ""
say "Each plugin's README is self-contained - full setup, commands and caveats:"
say "  https://github.com/${MARKETPLACE_SOURCE}#per-plugin-docs"
say ""
say "Not what you wanted? Nothing here is sticky:"
for p in $plugins; do
  say "  claude plugin uninstall ${p}@${MARKETPLACE}"
done
