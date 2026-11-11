# maha

[Español](README.es.md) · **English**

[![CI](https://github.com/ManexMartikorena/m-harness/actions/workflows/ci.yml/badge.svg)](https://github.com/ManexMartikorena/m-harness/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/ManexMartikorena/m-harness)](https://github.com/ManexMartikorena/m-harness/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

**An AI agent for your terminal.** Ask for something in plain language and
`maha` reads your code, searches, writes, edits and runs commands to get it
done, **asking you before every change**. It works with the provider and
model you choose, and tells you what each turn cost.

> 🚧 **In development: `v0.10.0`.** Already usable to work on a project:
> chat, read and change files, run commands, follow the project's
> `AGENTS.md`, save and resume sessions and see the cost, with OpenAI-format
> models and with Claude; and in scripts, with `maha -p`. What comes next
> is in the [roadmap](#roadmap).

```
$ maha -m claude-haiku-5-5
maha 0.10.0 · opencode-go · claude-haiku-5-5 · /help for commands
> Lee notas.txt con read_file y dime qué pone, en una frase.
  → read_file(path="notas.txt")
  ✓ 2 lines
El archivo `notas.txt` tiene dos líneas: "uno" y "dos".
  [tokens: 8803 in · 82 out · 1 call · $0.0026 · session $0.0026]
> Cambia la segunda línea de notas.txt por 'tres' con edit_file.
  → edit_file(path="notas.txt", old_string="dos", new_string="tres")
  ┌ edit notas.txt
  │ @@ -1,2 +1,2 @@
  │  uno
  │ -dos
  │ +tres
  └ Allow? [y] yes · [a] always this session · [n] no: y
  ✓ 1 replacement
He cambiado la segunda línea de `notas.txt` por "tres". La primera línea ("uno") no se ha tocado.
  [tokens: 9115 in · 144 out · 1 call · $0.0007 · session $0.0033]
> /trace
  20261110-173406-17e4 · claude-haiku-5-5, glm-5.3-flash · 2 turns · 5 model calls · 2 tools
  1  18:34:06  2 calls · 1 tool · 8803 in (4364 cached) · 82 out · $0.0026 · 1.9 s
  2  18:34:08  2 calls · 1 tool · 9115 in (8927 cached) · 144 out · $0.0007 · 2.3 s
  title by glm-5.3-flash · 102 in · 11 out · <$0.0001
  total: 18020 in (13291 cached) · 237 out · $0.0033
  [trace: ~/.local/share/maha/traces/20261110-173406-17e4.jsonl]
> /exit
$ maha -c -p "¿Qué pone ahora en notas.txt? Una frase." --allow read_file
  [resumed 20261110-173406-17e4 · 8 messages · claude-haiku-5-5]
  → read_file(path="notas.txt")
  ✓ 2 lines
  [tokens: 7845 in · 111 out (29 reasoning) · 1 call · $0.0024 · session $0.0057]
`notas.txt` ahora contiene dos líneas: "uno" y "tres".
```

*(A real session, in Spanish: you can talk to `maha` in any language. The
totals are exact; each turn is rounded to four decimals. With `-p`, only
the answer goes to stdout; the lines in brackets and the calls go to
stderr. Claude Haiku 5.5 through OpenCode Go: most of each request comes
from the prompt cache (`cached` in `/trace`), and costs much less; the
`title by` line is the cheap model that named the session.)*

## What it does

- **Works on your project.** Reads, lists and searches files (`read_file`,
  `list_dir`, `glob`, `grep`; `glob` and `grep` skip what `.gitignore`
  ignores), writes and edits them (`write_file`, `edit_file`, showing the
  diff) and runs commands (`run_command`).
- **It knows your project.** Before your first message, the model reads
  the project's `AGENTS.md` (or `CLAUDE.md`, if there is none), your own
  `~/.config/maha/AGENTS.md` and where it works: directory, git root,
  platform and date. At start, `maha` says which instruction files it
  loaded, and they never change permissions. `/init` writes or improves the
  project's `AGENTS.md`, and `maha prompt` shows the whole system prompt.

  ```
  > /init tests run with unittest, never with pytest
    ┌ create AGENTS.md (49 lines)
    └ Allow? [y] yes · [a] always this session · [n] no: y
    [AGENTS.md takes effect in the next session: /new]
  ```
- **It plans, and asks when it must.** In work of several changes, the
  model keeps a task list that you see as it goes (`☑ ▸ ☐`); when it
  cannot go on without you, it asks with options, and you can always
  write your own answer.
- **Nothing changes without your permission.** Every write and every command
  asks first, showing the diff or the command: once, always in this session,
  or no. "Always" covers every later edit inside the working directory, but
  only that exact command; files that run code by themselves (`.git`, CI,
  editor and agent configs, `.venv`, `node_modules`, `*.pth`) and files
  with more than one hard link ask every time. Reading outside the working
  directory or a secret file asks too, every time, and the model learns
  nothing of those files before you approve; a secret is recognized by its name
  (`.env`, keys, `.ssh`…), not by its content. Commands run with a time
  limit, without a terminal (one that asks for something, such as a
  password or an editor, fails at once) and without your provider key in
  their environment, but **with your permissions: read the command before
  approving it**.
- **The model and provider you want.** It speaks two API formats, OpenAI's
  and Anthropic's, and picks the right one for each model, also when you
  switch with `/model` in the middle of a session. OpenCode Go and Zen and
  Anthropic's API come configured, and you can declare any compatible
  server. Choose how hard the model works with `--effort` or `/effort`.
- **It uses the provider's prompt cache.** With Anthropic's format, each
  step reads from the cache what the previous one wrote: much cheaper than
  sending the whole conversation again. With Claude, the model's reasoning
  is kept and given back intact, as Anthropic requires.
- **In scripts too.** `maha -p "…"` does one instruction and exits: only
  the answer on stdout, or JSON; what comes on stdin goes below it
  (`git diff | maha -p "review this diff"`). With nobody to ask, only the
  tools you allow with `--allow` run, and never what would ask every time.
  With limits per turn (steps, dollars, tokens and time) and an exit code
  that says how it ended.
- **It survives a provider that fails.** A 429 or a server failure before
  the answer starts is retried, up to three times; if it keeps failing and
  you have a fallback model, it answers the rest of the turn. It always
  tells you.
- **Sessions that are never lost.** Every conversation is saved
  automatically, turn by turn (including an answer you interrupt), and can
  be resumed from any directory, also at start (`maha -c`, `maha -r ID`).
  They export to Markdown or JSON and import on another computer. When you
  resume, approvals start from scratch. A cheap model titles each session
  after its first turn; `/rename` gives it your own title.
- **You know what you spend.** Every turn shows its tokens and cost, and the
  session its total: the cost the provider reports (with OpenCode Go, what
  counts against your monthly limit) or, if it reports none, the one from a
  catalog with the prices of every OpenCode Go, Zen and Anthropic model.
  `maha stats` adds it up by day and model.
- **Everything is recorded, without your secrets.** Each session leaves a
  trace of what the agent did; `/trace` summarizes it.

## Installation

You need [uv](https://docs.astral.sh/uv/) (it also installs Python 3.14 if
missing).

```
uv tool install git+https://github.com/ManexMartikorena/m-harness@v0.10.0
```

Then choose a provider and a model:

```toml
# ~/.config/maha/config.toml
provider = "opencode-go"   # or "opencode-zen"
model = "glm-5.3-flash"
```

and put the key in an environment variable (you get it in the OpenCode
console, at https://opencode.ai):

```
export OPENCODE_API_KEY=...
maha
```

`maha` works on the directory where you open it.

Optional, in the same file: a fallback model, how hard the model works
(`effort`: `low`, `medium`, `high`, `xhigh` or `max`; without it, the
model's own), the model that titles the sessions, more instruction files,
and limits for each turn.

```toml
fallback_model = "glm-5.3"
effort = "high"
small_model = "glm-5.3-flash"      # titles; by default, the provider's cheap one
instructions = ["CONTRIBUTING.md"] # added to the system prompt

[limits]
max_steps = 25       # calls to the model
max_cost = 0.50      # dollars
max_tokens = 400000  # input + output
timeout = 600        # seconds
```

**Which models work today:** those served with the OpenAI Chat Completions
format or with Anthropic's Messages API. In OpenCode Go and Zen that is GLM,
Kimi, DeepSeek, MiMo, Claude, MiniMax, Qwen and many more. GPT, Gemini and
Grok use other APIs that `maha` does not speak yet: `maha models` marks them
with `*`, and choosing one says so before calling.

**Claude with your own Anthropic account:** create a key in the Claude
Console (https://platform.claude.com/settings/keys), then:

```
export ANTHROPIC_API_KEY=...
```

```toml
# ~/.config/maha/config.toml
provider = "anthropic"
model = "claude-opus-5-5"
cache_ttl = "1h"   # optional: the prompt cache lasts an hour (5m by default)
```

You pay per use in your Console account. A Claude subscription (Pro, Max)
cannot be used: Anthropic does not allow its login in third-party tools.

### Another provider

Any server with the OpenAI format, declared in your configuration:

```toml
# ~/.config/maha/config.toml
provider = "local"
model = "your-model-id"

[providers.local]
base_url = "http://localhost:11434/v1"
# api_key_env = "MY_KEY"   # without it, no key is sent
```

A project can choose its provider, model, fallback, effort and cache in
`.maha/config.toml` (read from any folder of the project, up to its git
root), and tighten the limits (never loosen them), but never
declare providers: that way a foreign repository cannot send your key to
another server. What a project chooses is said at start, so it cannot raise
your cost unseen: `[from .maha/config.toml: effort max, cache 1h]`.

## Usage

| Command | What it does |
|---|---|
| `/help` | Lists the commands |
| `/model [ID]` | Shows the model, or changes it |
| `/effort [LEVEL]` | Shows or changes how hard the model works; `default` goes back to the model's own |
| `/sessions` | Recent sessions, from every directory |
| `/resume [ID]` | Resumes a session; without ID, the last one here |
| `/delete ID` | Deletes a session and its trace |
| `/trace [ID]` | What a session did and cost, turn by turn |
| `/new` | A new session without quitting, with the same model |
| `/init [TEXT]` | Writes or improves the project's `AGENTS.md`; TEXT, what to stress |
| `/rename [TITLE]` | Shows the session's title, or gives it one |
| `/export [FILE]` | This conversation in Markdown; by default, `ID.md` |
| `/exit` | Quits (also Ctrl+D) |

- After each answer, the tokens line shows: input and output tokens (and,
  within the output, the reasoning ones), tool calls, the cost of the turn
  and of the session. In `/trace`, "calls" are the calls to the model.
- While it waits for the answer, a spinner with "maha" spins.
- **Ctrl+C** in the middle of an answer interrupts it and returns to the
  prompt; the model knows you interrupted it. At the prompt, it quits.
- **Without a terminal** (`maha < instructions.txt`), everything with an
  effect is denied. For scripts, use `maha -p`.

### From the shell

| Command | What it does |
|---|---|
| `maha -p "…"` | One instruction and exit; stdin goes below it |
| `maha -c`, `maha -r ID` | Continue the last session here, or one by its id |
| `maha models [--all]` | The models of the catalog, with their API format, window and prices |
| `maha sessions` | Recent sessions; `sessions delete ID` deletes one |
| `maha trace [ID]` | What a session did and cost; without id, the last one here |
| `maha prompt` | The system prompt a session here would have, without calling the model |
| `maha stats [--days N]` | Cost and tokens by day and model |
| `maha export ID [--format md\|json]` | A session in Markdown or JSON, to stdout |
| `maha import FILE` | A session exported in JSON, as a new one |

With `-p`:
- `--output-format text|json|stream-json`: only the answer (default; calls
  and tokens go to stderr), one JSON object at the end, or one JSON event
  per line. In JSON, `session_id` is the session to continue with `-r`
  (`null` if the run kept nothing) and `trace_id` is what `maha trace`
  shows, also of a run that failed.
- `--allow TOOL` (repeatable): that tool runs without asking inside the
  directory. Outside it, a secret or a file that runs code are always
  denied.
- With `-p` or without it: `-m ID` (model), `--fallback-model ID`,
  `--effort LEVEL`, `--max-steps N`, `--max-cost USD`, `--max-tokens N` and `--timeout S`;
  and for the system prompt, `--append-system-prompt TEXT`,
  `--append-system-prompt-file FILE` (added at the end) and
  `--system-prompt-file FILE` (your own base instead of maha's; the
  instructions and the environment stay).
- Exit code: 0 fine, 1 error (also when the model declines), 2 wrong usage,
  3 a limit stopped the turn (also when the answer reached the model's
  output limit or the conversation filled its context window), 4 a call was denied; with Ctrl+C or a signal, 128 + the
  signal.

```
$ git diff | maha -p "review this diff" --output-format json | jq -r .result
```

### Where it keeps things

| What | Where |
|---|---|
| Configuration | `~/.config/maha/config.toml` |
| Own prices (optional) | `~/.config/maha/models.toml` |
| Sessions | `~/.local/share/maha/sessions/` |
| Traces | `~/.local/share/maha/traces/` |
| Diagnostic log | `~/.local/state/maha/maha.log` |

Everything is local. Sessions, traces and the log are readable only by your
user. It honors the `XDG_*` variables.

## Roadmap

`maha` grows milestone by milestone up to version 1.0. Next:

- **Context compaction**, for long conversations, and **undo**.
- **Skills and custom commands, memory across sessions, sandbox, permission
  modes, subagents, MCP and hooks.**
- **Web and images.**
- **A full-screen interface**, with a command menu and easy navigation.
- **Version 1.0**, installable for any user and documented.

The full plan, milestone by milestone, is in [the project](docs/PROYECTO.md#hoja-de-ruta)
(in Spanish).

## The project

`maha` is built from scratch and in the open: no agent frameworks, each piece
in its own PR, with its spec, its tests and a note that explains the
concept. To learn how an agent works inside, or to build your own, start
with **[how it was built](docs/PROYECTO.md)** (in Spanish).

## License

[MIT](LICENSE)
