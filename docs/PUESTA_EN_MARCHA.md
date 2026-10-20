# Puesta en marcha de una máquina

> Este documento monta el **puesto de desarrollo** de M-Harness. La
> distribución a otros usuarios se documentará en `docs/DISTRIBUCION.md` cuando
> el proyecto esté maduro.

Qué hay que hacer para dejar este proyecto funcionando en una máquina nueva o
en otra de las que se usan. **El `.env` no viaja por git**, así que todo lo que
hay aquí es exactamente lo que no se arregla con un `git pull`.

Última revisión: 2026-10-20.

## 0. Tras cada `git pull`

Lo último que hay que hacer, lo más reciente arriba:

- **Hito 1, CI (2026-10-20):** `gh auth refresh --hostname github.com
  --scopes workflow`. Sin él, no se puede hacer push de `.github/workflows/`
  (§6).
- **Hito 1, pieza 8 (2026-10-20):** `uv sync` y `uv run pre-commit install`
  (una vez por clon). La primera ejecución de los hooks descarga Go y compila
  gitleaks: necesita red y tarda un poco (25 s en el WSL del PC de Windows).
- **Hito 1, pieza 1 (2026-10-20):** uv 0.13.1 o posterior. Comprobar con
  `uv --version`; si es más viejo, `uv self update` (o el método con que se
  instaló uv). Con uno viejo, `uv sync` falla con un aviso claro. Después,
  `uv sync`.

## 1. Entorno

- **Linux: Ubuntu 26.04 LTS**, la misma versión que el CI. En Windows,
  **WSL2** con Ubuntu 26.04: `wsl --install -d Ubuntu-26.04`. Hay que clonar
  y trabajar dentro del sistema de ficheros de WSL (`~/…`), no en
  `/mnt/c/…`: es mucho más lento y mezcla finales de línea. Windows nativo no
  es una plataforma soportada (spec del hito 1, §1.14).
- **git** y **GitHub CLI** (`gh`).
- **uv 0.13.1 o posterior** (https://docs.astral.sh/uv/). `pyproject.toml`
  lo exige (`required-version`). Python lo instala uv: `uv sync` descarga
  3.14 si falta, la versión que fija `.python-version`.
- Desde el hito 1:
  - `uv sync` tras clonar y tras cada pull que cambie `pyproject.toml` o
    `uv.lock`;
  - `uv run pre-commit install`, una vez por clon. Desde entonces, cada
    `git commit` pasa ruff, gitleaks y las comprobaciones de YAML y TOML.
    La primera vez descarga Go y compila gitleaks (necesita red); queda en
    `~/.cache/pre-commit/`.

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
uv run mypy
uv run lint-imports
uv run pytest
```

## 5. GitHub (una vez por repositorio)

Aplicado el 2026-10-19. Se deja escrito para poder rehacerlo.

1. Repo público `ManexMartikorena/m-harness`, con descripción y topics.
2. *Settings → General:*
   - **Pull Requests:**
     - solo *Allow merge commits*, con el título y la descripción del PR como
       mensaje;
     - *Always suggest updating pull request branches*;
     - *Automatically delete head branches* **desactivado**: las ramas
       integradas se conservan.
   - Sin Wiki ni Projects.
3. *Advanced Security:* secret scanning, push protection, alertas de
   Dependabot y reporte privado de vulnerabilidades, activados.
4. *Rules → Rulesets:*
   - **main protegida:**
     - solo por PR y solo merge commit;
     - conversaciones resueltas antes de integrar;
     - sin force push ni borrado.

     - *Require status checks to pass* (desde el 2026-10-20, tras el PR 1
       del hito 1): `checks (3.14)`, `checks (3.15)` y `secrets`.
       - *Require branches to be up to date before merging*: **activada**. Si
         `main` cambió desde que se abrió el PR, hay que pulsar "Update
         branch" y el CI vuelve a pasar con el código combinado.
       - *Do not require status checks on creation*: **desactivada** (solo
         afecta a ramas nuevas, y la regla protege `main`).
   - **tags de versión** (`v*`): no se mueven ni se borran.
5. *Actions:* tras crear o cambiar el CI, lanzarlo una vez a mano sobre
   `main` (*Actions → CI → Run workflow*, o
   `gh workflow run ci.yml --ref main`). Solo así gitleaks revisa el
   historial entero; en un PR mira solo sus commits. Hecho el 2026-10-20:
   41 commits, sin secretos.

## 6. Agente de código

- Trabaja siguiendo `AGENTS.md` (Claude Code lo lee a través de `CLAUDE.md`).
  Todo el contexto está en el repo: no se usa la memoria local del agente en
  ningún PC.
- En Windows, el agente se instala y se lanza **dentro de WSL**, desde el
  clon de `~/`. Así, los comandos que ejecuta son los de Linux.
- `gh` autenticado para push, PRs y consultar el CI, **con el scope
  `workflow`**:
  `gh auth login --hostname github.com --git-protocol https --web --scopes workflow`.
  Sin ese scope, GitHub rechaza el push de cualquier cambio en
  `.github/workflows/` ("refusing to allow an OAuth App to create or update
  workflow … without `workflow` scope"). Si el login ya existe:
  `gh auth refresh --hostname github.com --scopes workflow`. El login no
  viaja por git: se hace una vez por PC (en Windows, dentro de WSL).
