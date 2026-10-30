# Puesta en marcha de una máquina

> Este documento monta el **puesto de desarrollo** de M-Harness. La
> distribución a otros usuarios se documentará en `docs/DISTRIBUCION.md` cuando
> el proyecto esté maduro.

Qué hay que hacer para dejar este proyecto funcionando en una máquina nueva o
en otra de las que se usan. **El `.env` no viaja por git**, así que todo lo que
hay aquí es exactamente lo que no se arregla con un `git pull`.

Última revisión: 2026-10-26 (hito 6).

## 0. Tras cada `git pull`

Lo último que hay que hacer, lo más reciente arriba:

- **PR #58 (2026-10-26):** `uv sync`. Suben ruff (0.17.2), pytest-asyncio
  (1.4.1) y virtualenv (21.14.13, por una alerta de seguridad), todas de
  desarrollo.
- **Hito 6, PR 4 (2026-10-26):** nada que hacer. Desde aquí `maha` guarda
  cada conversación en `~/.local/share/maha/sessions/` (§3). Las sesiones
  de un PC no están en el otro.
- **Hito 2, PR 3 (2026-10-20):** para conversar con `maha`, crear
  `~/.config/maha/config.toml` (§3.1) y el `.env` con `OPENCODE_API_KEY`
  (§2). Los tests no necesitan ninguno de los dos.
- **Hito 2, PRs 1 y 2 (2026-10-20):** `uv sync`. Llegan pydantic, httpx y
  respx.
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

Desde el hito 2. `cp .env.example .env` y rellenar. `maha` no lee el `.env`
por su cuenta: en desarrollo se carga con `uv run --env-file .env maha`.
Con `maha` instalado (`uv tool install`), la variable se exporta en el
shell.

| Variable | Para qué | Si falta |
| --- | --- | --- |
| `OPENCODE_API_KEY` (hito 2) | Clave del proveedor de modelos (OpenCode Go o Zen) | `maha` no puede hablar con el modelo. Los tests no la necesitan |

## 3. Datos locales de `maha`

No hay servicios ni base de datos. Cada máquina tiene sus propios datos, y nada
de esto entra en git:
- `~/.config/maha/`: configuración del usuario (§3.1).
- `~/.local/share/maha/`: sesiones (desde el hito 6, en `sessions/`, un
  fichero `.jsonl` por sesión, solo legibles por el usuario), trazas (desde
  el hito 7, en `traces/`, una por sesión y con su mismo nombre) y memoria.
  Respeta `XDG_DATA_HOME`. Una sesión guarda todo lo que leyó el agente,
  también un secreto que aprobaste leer: se borra con `/delete`, que borra
  también su traza. La traza enmascara la clave del proveedor, las
  variables con forma de credencial y las claves con forma conocida
  (`sk-…`, `ghp_…`…), pero no garantiza que no quede ningún secreto.
- `~/.local/state/maha/`: registro de la aplicación (desde el hito 7,
  `maha.log`, solo legible por el usuario, rotado a 1 MiB con una copia).
  Solo diagnóstico: fallos del disco al guardar una sesión o una traza, el
  `fsync` de una carpeta que falla y errores internos de una herramienta;
  nunca el texto de la conversación. Respeta `XDG_STATE_HOME`. Desde el
  hito 8, también `evals/<fecha-hora>/`: las sesiones y trazas de cada
  ejecución de `maha eval`, aparte de las tuyas (§4.1). Se pueden borrar
  cuando ya no hagan falta.

Lo que se haga en una máquina no está en la otra.

### 3.1 `~/.config/maha/config.toml`

Desde el hito 2. Elige proveedor y modelo. Sin `model`, `maha` no arranca y
dice qué escribir. Respeta `XDG_CONFIG_HOME`.

```toml
provider = "opencode-go"   # o "opencode-zen"; por defecto, "opencode-go"
model = "glm-5.3-flash"    # el id, tal cual lo da el proveedor (cambian a menudo)

# Opcional: un servidor propio con formato OpenAI.
# [providers.local]
# base_url = "http://localhost:11434/v1"
# api_key_env = "MI_CLAVE"   # sin ella, no se envía Authorization
```

Desde el hito 8, límites de cada turno (todos opcionales; sin ellos, solo
los 25 pasos de siempre):

```toml
[limits]
max_steps = 25       # llamadas al modelo
max_cost = 0.50      # dólares
max_tokens = 400000  # entrada + salida
timeout = 600        # segundos
```

Desde el hito 8, también opcional, un modelo de respaldo: responde cuando
el principal sigue fallando (429 o 5xx) tras tres reintentos. Va arriba,
antes de `[limits]`; `--fallback-model` lo cambia para una ejecución.

```toml
fallback_model = "glm-5.3"
```

Un proyecto puede tener `.maha/config.toml` con `provider`, `model` y
`fallback_model`, que ganan a los del usuario, y `[limits]`, de los que vale el más estricto de
los dos ficheros: un repositorio ajeno no puede aflojar los tuyos. Si declara `[providers]`, `maha` se niega a
arrancar: un repositorio ajeno podría enviar la clave a otro servidor (spec
del hito 2, §1.10).

Ids de modelo comprobados el 2026-10-20 en https://opencode.ai/docs/go/:
`glm-5.3-flash`, `glm-5.3`, `kimi-k3`, `deepseek-v4.1-flash`.

### 3.2 `~/.config/maha/models.toml` (opcional)

Desde el hito 7. Precios y ventana de contexto de los modelos, con el mismo
formato que el catálogo que trae `maha` (`src/mharness/adapters/catalog/models.toml`,
todos los modelos de OpenCode Go y Zen). Sirve para un proveedor propio o
para corregir un precio sin esperar a una versión: cada modelo que pongas
aquí sustituye entero al del paquete. Respeta `XDG_CONFIG_HOME`. Si tiene un
error, `maha` no arranca y dice qué y dónde. Nunca se lee de un proyecto.

```toml
[providers.local]
checked = 2026-10-27        # la fecha de tus precios

[models."local/qwen-local"]
context = 32_768
input = 0                   # USD por millón de tokens
output = 0
```

## 4. Comprobar que todo está en pie

Desde el hito 1:

```
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run lint-imports
uv run pytest
```

### 4.1 Evals (llamadas reales, cuestan dinero)

Desde el hito 8 (spec, §1.5 a §1.9). Usan la clave del `.env` y el
proveedor de tu configuración; nunca corren en el CI.

```
uv run --env-file .env maha eval --split train            # iterar: 1 pasada, sin la validación
uv run --env-file .env maha eval --models glm-5.3-flash,kimi-k2.7-code --repeat 5
uv run --env-file .env maha eval --models glm-5.3-flash,kimi-k2.7-code --repeat 5 --save
```

- La segunda línea es la comparación antes de un merge (AGENTS.md,
  "Evals"); la tercera guarda una línea base nueva en `evals/baselines/`,
  que entra en git (solo números).
- Sale con 1 si hay una regresión (⚠).
- `--retry-errors` repite una vez lo que rompió el proveedor (429, 5xx,
  red); `--keep` deja la copia de cada ejecución para mirarla; las sesiones
  y trazas quedan en `~/.local/state/maha/evals/`.

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
