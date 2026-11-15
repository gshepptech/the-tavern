# Security Policy

## Reporting a vulnerability

If you discover a security issue in The Tavern - a plugin that executes
unintended commands, a hook that leaks data, an injection in a workflow script,
or anything else with a security impact - please report it privately.

Please open a [GitHub Security Advisory](https://github.com/gshepptech/the-tavern/security/advisories/new)
(Security, then Advisories, then *Report a vulnerability*). This keeps your report
private until a fix is available.

Please do **not** open a public issue for a vulnerability before it has been
addressed.

When reporting, include where possible:

- The plugin and file involved
- A description of the impact
- Steps to reproduce (a minimal repro is ideal)
- Any suggested remediation

## What to expect

- Acknowledgement of your report as soon as it is triaged.
- An assessment and, where warranted, a fix released on `main`.
- Credit in the release notes if you'd like it (and only if you'd like it).

## Scope notes

These plugins run inside Claude Code and can drive shell commands, file edits,
browsers (Scout, via Playwright), and remote systems (Sellsword). Treat that capability
the way you would any developer tool: review what a plugin does before granting it
permissions, and report anything that acts outside its stated remit.

Two capabilities deserve naming explicitly, because they are the largest surface
here and they are working as designed rather than as defects:

- **Unattended runs execute with permissions bypassed.** Ranger's headless runner
  and Sellsword's `/sellsword:goal` are built to work with no human present to answer a
  permission prompt, so they do not ask. A `PreToolUse` hook hard-blocks `git push`,
  remote mutation and PR creation for the whole of a Ranger run, and that block
  holds even in bypass mode - but **only git is guarded**. File writes, shell
  commands and network calls run unprompted. Run unattended mode in a container, a
  VM, or a throwaway clone, never on a machine you care about.
- **Sellsword operates on real infrastructure**, including SSH to remote hosts. Its host
  configuration lives in `.sellsword/hosts.yml` in your project.

A report that one of these acts *outside* its documented remit is in scope and
welcome. A report that unattended mode runs commands without asking is expected
behaviour, documented in the relevant plugin's README.
