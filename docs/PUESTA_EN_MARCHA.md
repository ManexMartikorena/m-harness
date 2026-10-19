# Puesta en marcha de una máquina

> Este documento monta el **puesto de desarrollo** de M-Harness. La
> distribución a otros usuarios se documentará en `docs/DISTRIBUCION.md` cuando
> el proyecto esté maduro.

Qué hay que hacer para dejar este proyecto funcionando en una máquina nueva o
en otra de las que se usan. **El `.env` no viaja por git**, así que todo lo que
hay aquí es exactamente lo que no se arregla con un `git pull`.

Última revisión: 2026-10-19.

## 0. Tras cada `git pull`

Lo último que hay que hacer, lo más reciente arriba:

- (nada todavía)

## 1. Entorno

- **Linux (Ubuntu).** En Windows, **WSL2** con Ubuntu. Hay que clonar y
  trabajar dentro del sistema de ficheros de WSL (`~/…`), no en `/mnt/c/…`:
  es mucho más lento y mezcla finales de línea.
- **git** y **GitHub CLI** (`gh`).
- **uv** (https://docs.astral.sh/uv/). Python lo instala uv:
  `uv python install 3.14`.
- Desde el hito 1:
  - `uv sync` tras clonar y tras cada pull que cambie `pyproject.toml` o
    `uv.lock`;
  - `uv run pre-commit install`, una vez por clon.

## 2. `.env`

Desde el hito 2. Copiar `.env.example` a `.env` y rellenar. `maha` no lee el
`.env` por su cuenta: en desarrollo se carga con
`uv run --env-file .env maha`.

| Variable | Para qué | Si falta |
| --- | --- | --- |
| `OPENCODE_API_KEY` (hito 2) | Clave del proveedor de modelos (OpenCode Go o Zen) | `maha` no puede hablar con el modelo. Los tests no la necesitan |

## 3. Datos locales de `maha`

No hay servicios ni base de datos. Cada máquina tiene sus propios datos, y nada
de esto entra en git:
- `~/.config/maha/`: configuración del usuario.
- `~/.local/share/maha/`: sesiones, trazas y memoria.
- `~/.local/state/maha/`: registro de la aplicación.

Lo que se haga en una máquina no está en la otra.

## 4. Comprobar que todo está en pie

Desde el hito 1:

```
uv run ruff check . && uv run ruff format --check .
uv run mypy src
uv run lint-imports
uv run pytest
```

## 5. GitHub (una vez por repositorio)

1. Crear el repo público `ManexMartikorena/m-harness` y hacer el primer push.
2. En *Settings*:
   - **General → Pull Requests:**
     - dejar solo *Allow merge commits*;
     - activar *Automatically delete head branches*.
   - **Advanced Security:** comprobar que *Secret scanning* y *Push protection*
     están activados.
   - **Rules → regla para `main`:**
     - exigir PR antes de integrar;
     - exigir que pase el CI, desde el hito 1, cuando exista el workflow.

## 6. Agente de código

- Trabaja siguiendo `AGENTS.md` (Claude Code lo lee a través de `CLAUDE.md`).
  Todo el contexto está en el repo: no se usa la memoria local del agente en
  ningún PC.
- `gh` autenticado para push, PRs y consultar el CI:
  `gh auth login --hostname github.com --git-protocol https --web`. El login no
  viaja por git: se hace una vez por PC.
