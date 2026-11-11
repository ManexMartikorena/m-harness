Write or improve the AGENTS.md of this project.

AGENTS.md tells a coding agent what it needs to work here and cannot see at
a glance.

First look at the project with your tools: its build, lint and test commands
(package files, Makefiles, CI workflows), its layout, and its README,
CONTRIBUTING, AGENTS.md or CLAUDE.md.

Write AGENTS.md in {{root}}:{{scope}}
- If it already exists, improve it in place: keep what is right, fix what is
  wrong, add what is missing. Never throw it away.
- If there is only a CLAUDE.md, start from it.

What goes in, short and specific to this project:
- The commands to build, lint and run the tests, also a single test.
- The architecture the names do not tell: how the parts fit, where new code
  goes.
- The conventions that differ from the defaults of the language.
- The traps: what breaks easily, what must never be done.

For each line ask: would an agent miss this without help? If not, leave it
out. No generic advice, nothing the file tree already shows, no lists of
files. Under 200 lines. When it is written, say in two lines what it holds.{{extra}}
