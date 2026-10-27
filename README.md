# maha

[Español](README.es.md) · **English**

[![CI](https://github.com/ManexMartikorena/m-harness/actions/workflows/ci.yml/badge.svg)](https://github.com/ManexMartikorena/m-harness/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/ManexMartikorena/m-harness)](https://github.com/ManexMartikorena/m-harness/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

**An AI agent for your terminal.** Ask for something in plain language and
`maha` reads your code, searches, writes, edits and runs commands to get it
done, **asking you before every change**. It works with the provider and
model you choose, and tells you what each turn cost.

> 🚧 **In development: `v0.7.0`.** Already usable to work on a project:
> chat, read and change files, run commands, save and resume sessions, and
> see the cost. What comes next is in the [roadmap](#roadmap).

```
$ maha
maha 0.7.0 · opencode-go · glm-5.3-flash · /help for commands
> Lee notas.txt con read_file y dime qué pone, en una frase.
  → read_file(path="notas.txt")
  ✓ 2 lines
El archivo notas.txt contiene dos líneas con las palabras "uno" y "dos".
  [tokens: 2547 in · 53 out (20 reasoning) · 1 call · $0.0003 · session $0.0003]
> Cambia la segunda línea de notas.txt por 'tres' con edit_file.
  → edit_file(path="notas.txt", old_string="dos", new_string="tres")
  ┌ edit notas.txt
  │ @@ -1,2 +1,2 @@
  │  uno
  │ -dos
  │ +tres
  └ Allow? [y] yes · [a] always this session · [n] no: y
  ✓ 1 replacement
Hecho: la segunda línea de notas.txt ahora dice "tres" (el archivo queda con "uno" y "tres").
  [tokens: 2689 in · 128 out (72 reasoning) · 1 call · $0.0002 · session $0.0004]
> /trace
  20261027-151848-9e34 · glm-5.3-flash · 2 turns · 4 model calls · 2 tools
  1  16:18:48  2 calls · 1 tool · 2547 in · 53 out · $0.0003 · 2.7 s
  2  16:18:51  2 calls · 1 tool · 2689 in · 128 out · $0.0002 · 2.9 s
  total: 5236 in · 181 out · $0.0004
  [trace: ~/.local/share/maha/traces/20261027-151848-9e34.jsonl]
```

*(A real session, in Spanish: you can talk to `maha` in any language. The
totals are exact; each turn is rounded to four decimals.)*

## What it does

- **Works on your project.** Reads, lists and searches files (`read_file`,
  `list_dir`, `glob`, `grep`; `glob` and `grep` skip what `.gitignore`
  ignores), writes and edits them (`write_file`, `edit_file`, showing the
  diff) and runs commands (`run_command`).
- **Nothing changes without your permission.** Every write and every command
  asks first, showing the diff or the command: once, always in this session,
  or no. "Always" covers every later edit inside the working directory, but
  only that exact command. Reading outside the working directory or a
  secret file asks too, every time; a secret is recognized by its name
  (`.env`, keys, `.ssh`…), not by its content. Commands run with a time
  limit, without a terminal (one that asks for something, such as a
  password or an editor, fails at once) and without your provider key in
  their environment, but **with your permissions: read the command before
  approving it**.
- **The model and provider you want.** OpenAI format out of the box, with
  OpenCode Go and Zen already configured, and any compatible server you
  declare. Switch models with `/model` or in the configuration.
- **Sessions that are never lost.** Every conversation is saved
  automatically, turn by turn (including an answer you interrupt), and can
  be resumed from any directory.
  When you resume, approvals start from scratch.
- **You know what you spend.** Every turn shows its tokens and cost, and the
  session its total: the cost the provider reports (with OpenCode Go, what
  counts against your monthly limit) or, if it reports none, the one from a
  catalog with the prices of every OpenCode Go and Zen model.
- **Everything is recorded, without your secrets.** Each session leaves a
  trace of what the agent did; `/trace` summarizes it.

## Installation

You need [uv](https://docs.astral.sh/uv/) (it also installs Python 3.14 if
missing).

```
uv tool install git+https://github.com/ManexMartikorena/m-harness@v0.7.0
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

**Which models work today:** those served with the OpenAI Chat Completions
format. In OpenCode Go and Zen that is GLM, Kimi, DeepSeek, MiMo, MiniMax M3.1
Flash and several more; Claude, GPT, Gemini and Grok use other APIs that
`maha` does not speak yet (Anthropic's comes in milestone 9).

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

A project can choose its provider and model in `.maha/config.toml`, but never
declare providers: that way a foreign repository cannot send your key to
another server.

## Usage

| Command | What it does |
|---|---|
| `/help` | Lists the commands |
| `/model [ID]` | Shows the model, or changes it |
| `/sessions` | Recent sessions, from every directory |
| `/resume [ID]` | Resumes a session; without ID, the last one here |
| `/delete ID` | Deletes a session and its trace |
| `/trace [ID]` | What a session did and cost, turn by turn |
| `/exit` | Quits (also Ctrl+D) |

- After each answer, the tokens line shows: input and output tokens (and,
  within the output, the reasoning ones), tool calls, the cost of the turn
  and of the session. In `/trace`, "calls" are the calls to the model.
- While it waits for the answer, a spinner with "maha" spins.
- **Ctrl+C** in the middle of an answer interrupts it and returns to the
  prompt; the model knows you interrupted it. At the prompt, it quits.
- **Without a terminal** (`maha < instructions.txt`), everything with an
  effect is denied.

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

- **Non-interactive mode and evals:** `maha -p "…"` for scripts, resuming at
  start, JSON output, cost limits, `maha stats`.
- **More providers:** the Anthropic format, reasoning effort.
- **Project instructions** (`AGENTS.md`, `/init`), context compaction and
  **undo**.
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
