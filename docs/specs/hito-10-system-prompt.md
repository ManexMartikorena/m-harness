Estado: PROPUESTA (2026-11-04) → APROBADA (2026-11-04, por el humano, con la
decisión 2 revisada a su petición: una capa por familia de modelo, §1.3)

# Spec — Hito 10: System prompt por capas

Referencias: `docs/DESIGN.md` §3 (árbol: `application/prompt.py`), §5 (el
system prompt no es un mensaje), §8 (composición por capas), §9 (evals),
§10 (entrada no confiable, secretos) y §14 (hito 10, P4 y P5);
`docs/ANALISIS.md` §5 (pieza 5) y requisito 10; `docs/COMPARATIVA.md` §2,
§6, §9 y §10; specs 6 (§1.8: el modelo no sabe en qué directorio trabaja
tras retomar), 8 (evals, `-p`) y 9 (§1.8, caché del prompt);
la auditoría profunda tras el hito 9 (B7: `complete()` sin uso); `AGENTS.md`.

## 0. Alcance

**El problema.** Hoy `maha` no manda ningún system prompt
(`application/agent.py`: "No system prompt until hito 10"). El modelo no
sabe quién es, cómo debe trabajar, en qué directorio está, qué día es ni
qué convenciones tiene el proyecto. Las instrucciones de un `AGENTS.md` se
pierden si el agente no decide leerlas.

**Lo que hace este hito.** Un system prompt hecho de capas: una base
escrita en el repo, las instrucciones del usuario y del proyecto
(`AGENTS.md`, y `CLAUDE.md` por compatibilidad), instrucciones extra de la
configuración y el entorno. Se construye una vez por sesión, se puede ver
(`maha prompt`) y se mide con evals. Además: `/init` para escribir el
`AGENTS.md`, dos herramientas nuevas (lista de tareas y pregunta a la
persona), títulos de sesión con un modelo pequeño y `/rename`.

**Términos.**
- **System prompt:** el texto fijo que va delante de la conversación en
  cada llamada. No es un mensaje: va aparte en `ModelRequest.system`
  (DESIGN §5).
- **Capa:** una parte del system prompt con un origen propio (la base, un
  fichero, el entorno).
- **Plantilla:** un fichero `.md` del repo con huecos (`{{cwd}}`) que el
  código rellena.
- **Instrucciones de proyecto:** un `AGENTS.md`, el estándar abierto
  (https://agents.md/), que el proyecto escribe para los agentes.
- **Modelo pequeño:** uno barato y rápido, para tareas de apoyo como poner
  título a una sesión.

Dentro de alcance:
- **Las capas** (§1.1 a §1.7): base, familia del modelo, usuario,
  proyecto, extra y entorno.
- **Ver y ajustar el prompt** (§1.8): `maha prompt`, la línea de
  instrucciones al arrancar y `--append-system-prompt` y
  `--system-prompt-file`.
- **`/init`** (§1.9).
- **`todo_write`** y **`ask_user`** (§1.10, §1.11).
- **Títulos de sesión** con un modelo pequeño, y **`/rename`** (§1.12).
- **Trazas y líneas base con la huella del prompt** (§1.13).
- **Evals** (§5): la batería con el prompt nuevo, y tres tareas nuevas.
- Nota 10 de la guía: el system prompt.

**Fuera de alcance** (y por qué):
- **`AGENTS.md` de subcarpetas, cargados al leer un fichero de allí:**
  meten texto a mitad de la conversación; va con la gestión del contexto,
  hito 11 (decisión 6).
- **Reglas por ruta** (`.claude/rules/` con `paths`): se cargan bajo
  demanda, como las skills; hito 13 (decisión 6).
- **Instrucciones por URL:** son red; hito 19 (web).
- **Imports `@fichero` de `CLAUDE.md`:** no se expanden (decisión 5).
- **Contar tokens del prompt:** hito 11 (`/context`). Aquí se cuentan bytes.

## 1. Decisiones de fondo

### 1.0 Hechos comprobados (2026-11-04)

Leídos en la documentación oficial y, para OpenCode, en su código
(`anomalyco/opencode`, rama `dev`, commit `8568952`).

| Hecho | Fuente |
|---|---|
| OpenCode lee `AGENTS.md` del proyecto y `~/.config/opencode/AGENTS.md`; usa `CLAUDE.md` solo si no hay `AGENTS.md` (y `~/.claude/CLAUDE.md` si no hay el global) | https://opencode.ai/docs/rules/ |
| OpenCode recoge todos los `AGENTS.md` del directorio actual hacia arriba, hasta la raíz del proyecto, con la cabecera `Instructions from: <ruta>` | código, `packages/core/src/config/plugin/instruction.ts` |
| OpenCode no expande las referencias `@` de `AGENTS.md` | https://opencode.ai/docs/rules/ |
| `instructions` de OpenCode acepta rutas, globs y URLs | https://opencode.ai/docs/config/ |
| Claude Code junta los `CLAUDE.md` del directorio actual y de encima, de la raíz hacia abajo; lee `AGENTS.md` solo si no hay `CLAUDE.md` | https://code.claude.com/docs/en/memory.md |
| Claude Code expande `@ruta` hasta 4 niveles; recomienda menos de 200 líneas; salta un fichero de más de 4 MiB | https://code.claude.com/docs/en/memory.md |
| Codex baja de la raíz git al directorio actual, un fichero por carpeta, con un tope total de 32 KiB (`project_doc_max_bytes`) | https://developers.openai.com/codex/guides/agents-md |
| El entorno de OpenCode: directorio de trabajo, raíz del proyecto, si es un repo git y la plataforma; la fecha sin hora; ni git status ni árbol | código, `packages/core/src/instructions/builtins.ts` |
| OpenCode elige un prompt por familia según el id (`gpt`, `claude`, `kimi`…) | código, `packages/core/src/plugin/optimize.ts` |
| Claude Code: `--system-prompt(-file)` sustituye, `--append-system-prompt(-file)` añade; en los dos modos; el prompt se construye en la primera petición y se reutiliza | https://code.claude.com/docs/en/cli-reference.md |
| Un cambio en el system prompt invalida la caché de todo lo que va detrás | https://code.claude.com/docs/en/prompt-caching.md |
| `/init` crea o mejora en el sitio el `AGENTS.md`/`CLAUDE.md`, sin reemplazarlo a ciegas | https://opencode.ai/docs/rules/, https://code.claude.com/docs/en/commands.md |
| Títulos: OpenCode usa `small_model` (o uno más barato del proveedor, o el principal); parte del primer mensaje (2.000 caracteres); Claude Code no titula los `claude -p` | https://opencode.ai/docs/config/, código `session/title.ts`, https://code.claude.com/docs/en/sessions.md |
| `todowrite` de OpenCode: `todos: [{content, status}]`, con `pending`, `in_progress`, `completed` y `cancelled`; sin permiso por defecto | https://opencode.ai/docs/tools/, código `tool/plugin/todo.ts` |
| `AskUserQuestion` de Claude Code: 1 a 4 preguntas, `header` de 12 caracteres como máximo, 2 a 4 opciones con `label` y `description`, `multiSelect`, y siempre "Other" para texto libre | https://code.claude.com/docs/en/agent-sdk/user-input.md |
| Claude Code apaga su lista de tareas en los modelos nuevos: "keeps track of multi-step work without a written checklist" | https://code.claude.com/docs/en/agent-sdk/todo-tracking.md |

### 1.1 Las capas, y en qué orden

Seis capas, de la más fija a la más variable. La caché compara el
principio exacto de la petición (§1.0), así que lo que menos cambia va
primero:

| # | Capa | De dónde sale |
|---|---|---|
| 1 | **Base** | `src/mharness/prompts/base.md`, del repo, o el fichero de la persona (§1.3) |
| 1b | **Familia** | `src/mharness/prompts/families/<familia>.md`, si existe (§1.3) |
| 2 | **Usuario** | `~/.config/maha/AGENTS.md` (§1.4) |
| 3 | **Proyecto** | los `AGENTS.md` de la raíz git al directorio actual (§1.4) |
| 4 | **Extra** | `instructions` de la configuración (§1.5) |
| 5 | **Entorno** | directorio, raíz git, plataforma, shell y fecha (§1.7) |

`--append-system-prompt` va detrás de todo (§1.8). Cada capa de
instrucciones va delimitada, con su origen:

```
<instructions source="AGENTS.md">
Los tests se lanzan con `uv run pytest`.
</instructions>
```

Las capas de ANALISIS §5 que faltan (skills y memoria) llegan en los hitos
13 y 14, en este mismo orden, detrás de "Extra".

### 1.2 Una vez por sesión

El prompt se construye al crear el agente de una sesión (al arrancar, con
`/new` y con `/resume`) y **no cambia** hasta la siguiente. `/model` solo
cambia la capa de familia. *(Corregido al implementarlo: decía "`/model`
no lo toca", pero con la capa de familia otro modelo puede necesitar otra;
la caché del proveedor es de cada modelo, así que cambiar de modelo ya la
pierde. Las instrucciones siguen las del principio de la sesión.)*
- **Por qué:** si cambia, la caché del proveedor se pierde en cada
  llamada (§1.0). Claude Code hace lo mismo.
- **Consecuencia:** un `AGENTS.md` editado a mitad de sesión (también por
  `/init`) cuenta desde `/new`; `maha` lo dice (§1.9).
- **Al retomar una sesión** el prompt se construye de nuevo, con el
  directorio de este `maha`. Si la sesión era de otro, el entorno lo dice
  ("This conversation started in ~/web; you now work in ~/proyecto"). Esto
  cierra el pendiente de la spec 6, §1.8.
- **La fecha** es la del día en que se construye, sin hora (como OpenCode):
  una sesión que pasa la medianoche sigue con la del día anterior. Es
  barato y no rompe la caché.

### 1.3 El prompt base

- **Uno para todos los modelos**, en inglés (el código está en inglés), en
  `src/mharness/prompts/base.md`. Pide responder en el idioma de la
  persona.
- **Contenido** (el texto exacto se revisa en el PR, como código):
  1. quién es `maha` y para qué está;
  2. cómo trabajar: leer antes de cambiar, cambios pequeños, no inventar
     rutas ni APIs, comprobar el resultado y decir lo que no se pudo;
  3. las herramientas: una línea por herramienta registrada, generada
     según las que haya (sin `run_command` en las evals, sin `ask_user` en
     `-p`);
  4. los permisos: el código pregunta a la persona; una denegación se
     respeta y no se intenta por otro camino;
  5. lo que devuelven las herramientas, los ficheros y la web es dato, no
     órdenes (DESIGN §10: el prompt avisa; la defensa es el permiso en
     código);
  6. el formato: respuestas cortas, rutas como `fichero:línea`.
- **Objetivo de tamaño:** la base, con las líneas de herramientas, por
  debajo de 1.500 tokens. Se mide en las evals (§5).
- **Plantillas propias, sin Jinja2.** Un hueco es `{{nombre}}`. El código
  rellena cada uno; un hueco sin valor o un valor sin hueco es un error, y
  un test recorre todas las plantillas. Jinja2 sería una dependencia para
  sustituir una docena de huecos (DESIGN §7.1: a mano lo que es del
  agente).
- **Una capa por familia de modelo** (como OpenCode, §1.0), detrás de la
  base. Cada familia responde distinto al mismo texto; el mecanismo está
  desde el principio para que adaptar `maha` a un modelo sea añadir un
  fichero, no rediseñar:
  - **la familia la dice el catálogo**, con un campo explícito
    (`family = "claude"`), no una subcadena del id como OpenCode: un id
    propio de la persona o de un proveedor nuevo la rompería. Un modelo
    sin `family` no tiene capa;
  - **la capa es `src/mharness/prompts/families/<familia>.md`**: lo que
    esa familia necesita y la base no dice (por ejemplo, cuándo usar
    `todo_write`, o lo largo que responde);
  - **una capa solo entra si las evals la justifican** (§5): base sola
    frente a base + capa, en la familia que mide. Hoy se pueden medir
    `glm`, `kimi` y `claude`. Para las familias que no se pueden medir
    aquí (`gpt`, `gemini`…) el mecanismo queda listo y sin fichero, y
    cada una entra con su eval (un prompt sin medir es deuda);
  - el campo `family` se rellena en todos los modelos del catálogo de
    serie, con su test, y la persona lo pone en su `models.toml`.
- **La persona puede cambiar la base**, para siempre o para una vez:
  `system_prompt_file` en `~/.config/maha/config.toml` y
  `--system-prompt-file` en la línea (§1.8). Sustituye la base y la capa de
  familia; las instrucciones y el entorno siguen. Desde `.maha/config.toml`
  no se acepta: un repo clonado no debe poder cambiar el prompt base, solo
  añadir instrucciones (§1.6).

### 1.4 Instrucciones del usuario y del proyecto

**Proyecto.** Si el directorio actual está dentro de un repo git (hay un
`.git`, carpeta o fichero, en él o encima), se recorren las carpetas de la
raíz git al directorio actual; si no, solo el directorio actual. En cada
carpeta, el primero que exista de:
1. `AGENTS.md`;
2. si no hay, por compatibilidad: `CLAUDE.md`, `.claude/CLAUDE.md` y
   `CLAUDE.local.md`, los que haya, en ese orden.

Van de la raíz hacia abajo: el más cercano, el último (en caso de choque,
el modelo tiende a seguir lo último; es lo que hacen Codex y Claude Code).

**Usuario.** `$XDG_CONFIG_HOME/maha/AGENTS.md` (por defecto
`~/.config/maha/AGENTS.md`); si no existe, `~/.claude/CLAUDE.md`.

**`compat_claude = false`** en la configuración apaga los ficheros de
Claude.

**Cómo se leen:**
- solo ficheros normales; un enlace se sigue si apunta dentro de la raíz
  git (o del directorio actual sin git) y no a un secreto
  (`domain/paths.py`);
- en UTF-8; si no lo es, se salta con aviso;
- **tope: 64 KiB entre todos.** Lo que pasa del tope se corta, con la
  marca `[truncated: 1234 bytes more]` en el prompt y un aviso al
  arrancar. 64 KiB caben de sobra: el `AGENTS.md` de este repo tiene
  15,6 KB; Codex pone 32 KiB por defecto (§1.0);
- un error de disco no para `maha`: el fichero se salta con aviso.

### 1.5 Instrucciones extra

```toml
instructions = ["CONTRIBUTING.md", "docs/estilo/*.md"]
```

- Rutas o globs (con `domain/wildcard.py`), relativos al directorio
  actual; `~` vale en la del usuario.
- **En `.maha/config.toml` (el proyecto) solo valen rutas dentro del
  proyecto y que no sean secretos.** El fichero del proyecto no es de
  fiar (config.py): un `instructions = ["~/.ssh/id_ed25519"]` mandaría la
  clave al proveedor. Lo que no cumple es un error de configuración.
- Se suman las dos listas, usuario y proyecto, sin repetir ficheros.
- Un patrón que no casa con nada da un aviso, no un error.
- Cuentan para el tope de 64 KiB.

### 1.6 Confianza

Un `AGENTS.md` es texto que el proyecto da al agente **para que lo siga**:
es su razón de ser. Un repo clonado puede traer uno malicioso. Por eso:
- las instrucciones **nunca** cambian herramientas, permisos ni límites:
  son código (AGENTS.md, reglas). Un `AGENTS.md` que diga "no preguntes"
  no quita ninguna pregunta;
- al arrancar, `maha` dice qué ficheros ha cargado (§1.8): nada entra sin
  que se vea;
- los ficheros de instrucciones del proyecto no salen nunca de la raíz
  git, y ninguno es un secreto (§1.4, §1.5).

### 1.7 El entorno

```
<environment>
Working directory: /home/ana/proyecto
Git repository: yes (root: /home/ana/proyecto)
Platform: linux
Shell: /bin/bash
Today's date: 2026-11-04
</environment>
```

- **Sin git status, sin árbol de ficheros y sin el nombre del modelo:**
  cambian a mitad de sesión y romperían la caché; el modelo los pide con
  sus herramientas si los necesita (como OpenCode, §1.0).
- **La raíz git se detecta mirando el disco** (`.git`), sin lanzar `git`.

### 1.8 Ver y ajustar el prompt

- **Al arrancar**, en la terminal y en `-p` (stderr), una línea:
  `[instructions: AGENTS.md · ~/.config/maha/AGENTS.md]`. Sin ficheros, no
  se escribe nada. Con avisos (cortado, no UTF-8), una línea por aviso.
- **`maha prompt`** escribe el system prompt que tendría una sesión en
  este directorio, con esta configuración y estas opciones (también `-m`,
  que elige la capa de familia), sin llamar al modelo. Para depurar y para aprender.
- **`--append-system-prompt TEXTO`** y **`--append-system-prompt-file
  RUTA`**: añaden una capa al final. **`--system-prompt-file RUTA`**:
  sustituye la base y la capa de familia, como `system_prompt_file` de la
  configuración del usuario, al que gana (§1.3); las instrucciones y el
  entorno siguen. En la
  terminal y en `-p`, solo por la línea de comandos (como el resto de lo
  que cambia el comportamiento sin persona, DESIGN §8).

### 1.9 `/init`

- Un turno normal cuyo mensaje es la plantilla `src/mharness/prompts/init.md`
  (en la conversación se ve `/init`). El agente mira el repo con sus
  herramientas y escribe `AGENTS.md`; escribir pide permiso, como siempre.
- **La plantilla pide** (como OpenCode, §1.0): comandos de build, lint y
  test; la arquitectura que no se deduce de los nombres; convenciones;
  trampas. Cada línea tiene que responder "¿lo pasaría por alto un agente
  sin ayuda?". Si ya hay `AGENTS.md`, se mejora en el sitio; si solo hay
  `CLAUDE.md`, se parte de él.
- `/init TEXTO` añade lo que la persona quiera destacar.
- Al terminar: `[AGENTS.md takes effect in the next session: /new]` (§1.2).

### 1.10 `todo_write`: la lista de tareas

```json
{"todos": [
  {"content": "Añadir calcular_iva_reducido", "status": "completed"},
  {"content": "Actualizar los tests", "status": "in_progress"},
  {"content": "Apuntarlo en el CHANGELOG", "status": "pending"}
]}
```

- **La lista entera en cada llamada** (como OpenCode): sin ids que
  sincronizar. `status`: `pending`, `in_progress`, `completed` o
  `cancelled`. Entre 1 y 50 tareas; `content` de 1 a 200 caracteres; como
  mucho una `in_progress`. Lo que no cumple vuelve al modelo como error de
  validación (AGENTS.md).
- **Permiso `READ`:** no toca nada fuera de `maha`.
- **Al modelo** le vuelve un resumen: `3 tasks: 1 completed, 1 in
  progress, 1 pending`.
- **En la terminal**, la lista con casillas, en lugar de la línea de la
  llamada:
  ```
    ☑ Añadir calcular_iva_reducido
    ▸ Actualizar los tests
    ☐ Apuntarlo en el CHANGELOG
  ```
- **Vive en la conversación:** la última llamada a `todo_write` del
  historial es la lista. Al retomar una sesión, la lista vuelve sola.
- **Para todos los modelos.** Claude Code la apaga en los modelos nuevos
  (§1.0); aquí se mide: las evals comparan pasos y coste (§5).

### 1.11 `ask_user`: preguntar a la persona

```json
{"questions": [{
  "question": "¿Qué base de datos usa el proyecto?",
  "header": "Base de datos",
  "options": [
    {"label": "SQLite", "description": "Un fichero local"},
    {"label": "PostgreSQL", "description": "Un servidor"}
  ],
  "multi_select": false
}]}
```

- **Esquema** (como `AskUserQuestion`, §1.0): de 1 a 4 preguntas; `header`
  de hasta 12 caracteres; de 2 a 4 opciones con `label` y `description`;
  `multi_select`. La terminal añade siempre "Other", para escribir otra
  cosa.
- **Un puerto nuevo, `UserQuestions`**, que implementa la terminal. La
  herramienta lo recibe en `bootstrap.py`; no conoce la terminal.
- **Solo se registra si hay alguien que responda:** en la terminal
  interactiva, con la entrada en una terminal. En `-p`, en las evals y con
  `maha < fichero` no existe (DESIGN §10: lo no registrado no existe para
  el modelo). Así el modelo no pierde un paso preguntando a nadie.
- **Permiso `READ`:** preguntar no es un efecto.
- **La respuesta vuelve como resultado:** `Base de datos: SQLite`. Ctrl+C
  corta el turno, como en una aprobación; la espera no cuenta para el
  tiempo límite del turno (decisión de la auditoría, B4).

### 1.12 Títulos de sesión y `/rename`

- **Tras el primer turno** de una sesión interactiva, el modelo pequeño
  escribe un título de hasta 60 caracteres (`TITLE_MAX`) a partir del
  primer mensaje (hasta 2.000 caracteres, delimitado como dato). Plantilla:
  `src/mharness/prompts/title.md`. Usa `ModelClient.complete()`, que se
  conservó para esto (auditoría, B7).
- **En segundo plano:** no hace esperar a nadie. Si falla, se queda el de
  hoy (la primera línea) y el fallo va a `maha.log`.
- **Se guarda** como una entrada nueva del fichero de la sesión,
  `TitleEntry`; `/sessions` y `maha sessions` la enseñan. El texto pasa por
  `printable()` y se limpia de saltos de línea.
- **Su coste cuenta** en el uso de la sesión y en la traza.
- **El modelo pequeño:** `small_model` en la configuración; si no hay, el
  que el catálogo da al proveedor (`small_model` en `[providers.X]`); si
  tampoco, el de la sesión. En el catálogo: `opencode-go` y
  `opencode-zen`, `glm-5.3-flash` (0,15 $/M de entrada, el que ya mide las
  evals; en Zen, el de pago, no el gratuito que puede entrenar con los
  datos); `anthropic`, `claude-haiku-5-5`. Un `small_model` en el fichero
  del proyecto se avisa al arrancar, como los otros ajustes que suben el
  coste (auditoría, M4).
- **Sin título automático** en `-p` y en las evals (como Claude Code,
  §1.0): ahí la primera línea basta.
- **`/rename TÍTULO`** pone el título a mano, con las mismas reglas; un
  título a mano no lo pisa el automático.

### 1.13 Trazas y líneas base

- **Al empezar cada sesión** (y en cada `/new` y `/resume`), la traza
  apunta un registro `prompt`: la huella (SHA-256, 12 caracteres), las
  capas con su origen y sus bytes. El texto entero no: se ve con `maha
  prompt`, y una traza no debe guardar dos veces los `AGENTS.md`.
- **La línea base guarda la huella de la base** (plantilla, capa de
  familia y líneas de herramientas, sin entorno ni instrucciones). Si una pasada de evals
  tiene otra, el informe lo dice: `[the base prompt changed since the
  baseline]`.

## 2. En la industria

- **OpenCode** compone base + entorno + `AGENTS.md`, con un prompt por
  familia de modelo, y mete lo que cambia como mensajes nuevos.
- **Claude Code** tiene un system prompt fijo y mete `CLAUDE.md` y el
  entorno como un mensaje de usuario detrás, para no tocar la parte en
  caché; `--system-prompt` y `--append-system-prompt` lo ajustan.
- **Codex** junta los `AGENTS.md` de la raíz git hacia abajo, con un tope
  de bytes.
- **Frameworks:** plantillas con Jinja2 (LangChain `PromptTemplate`),
  prompts versionados en Langfuse o LangSmith. Se elegirían con muchos
  prompts editados por gente que no programa, o con experimentos A/B en
  producción.
- **`AGENTS.md`** es hoy el estándar abierto que leen casi todos los
  agentes (https://agents.md/).

`maha` hace lo de OpenCode con una diferencia: todo va en el system prompt
y se fija por sesión, que da la misma caché que el mensaje de Claude Code y
deja la conversación limpia.

## 3. Diseño de detalle

### 3.1 Ficheros

| Fichero | Capa | Qué |
|---|---|---|
| `src/mharness/prompts/base.md`, `init.md`, `title.md` y `families/` (nuevos) | — (datos del paquete) | Las plantillas. Las lee `bootstrap.py` con `importlib.resources` y las pasa como texto |
| `domain/prompt.py` (nuevo) | domain | `render(plantilla, valores)` estricto; `Layer(source, text)`; `compose(layers)`; el tope de 64 KiB y la marca de corte; `Environment`; `fingerprint()` |
| `domain/session.py` | domain | `TitleEntry` (automático o a mano) |
| `domain/todo.py` (nuevo) | domain | `Todo` y `TodoList` (Pydantic), las reglas y el resumen |
| `domain/question.py` (nuevo) | domain | `Question`, `Option` y `Answer` |
| `ports/project.py` (nuevo) | ports | `ProjectInfo`: `environment()` e `instructions()` |
| `ports/questions.py` (nuevo) | ports | `UserQuestions`: `ask(questions) -> answers` |
| `adapters/project/local.py` (nuevo) | adapters | Busca la raíz git y lee los ficheros de instrucciones (§1.4, §1.5) |
| `adapters/tools/todo.py`, `adapters/tools/question.py` (nuevos) | adapters | `TodoWrite` y `AskUser` |
| `adapters/cli/questions.py` (nuevo) | adapters | Las preguntas en la terminal |
| `application/prompt.py` (nuevo) | application | `SystemPromptBuilder`: junta las capas con `ProjectInfo` y las plantillas |
| `application/titles.py` (nuevo) | application | El título en segundo plano, con `complete()` |
| `application/agent.py` | application | `system` en `__init__` y en `_request()` |
| `application/sessions.py` | application | El prompt al crear cada agente; el título; `/rename` |
| `application/evals.py`, `adapters/evals/toml_suite.py` | application, adapters | Sin capa de usuario; la huella en la línea base |
| `adapters/cli/*` | adapters | `/init`, `/rename`, la lista de tareas, la línea de instrucciones, `maha prompt` y las opciones nuevas |
| `domain/catalog.py` | domain | `ModelInfo.family` |
| `adapters/catalog/models.toml`, `toml_catalog.py` | adapters | `family` en cada modelo; `small_model` por proveedor |
| `config.py` | — | `instructions`, `compat_claude` y `small_model` |
| `bootstrap.py` | — | El cableado |

### 3.2 Configuración nueva

```toml
# ~/.config/maha/config.toml o .maha/config.toml
instructions = ["CONTRIBUTING.md"]   # §1.5; en el proyecto, solo dentro de él
compat_claude = true                 # §1.4; false apaga CLAUDE.md
small_model = "glm-5.3-flash"        # §1.12; en el proyecto, con aviso
system_prompt_file = "~/prompts/mi-base.md"  # §1.3; solo en la del usuario
```

En `models.toml` (el de serie y el de la persona), cada modelo gana
`family = "glm"` (§1.3).

Opciones de la línea de comandos: `--append-system-prompt`,
`--append-system-prompt-file` y `--system-prompt-file` (§1.8). Subcomando:
`maha prompt`. Comandos: `/init` y `/rename`.

### 3.3 Eventos y entradas

- `TitleEntry(title, manual)` en el fichero de la sesión.
- El registro `prompt` de la traza (§1.13).
- `todo_write` no necesita evento propio: la terminal pinta la lista con
  los argumentos de `ToolCallProposed`.

## 4. Plan de tests

Con fakes y ficheros temporales; ninguna llamada real.

1. `render()`: rellena; un hueco sin valor y un valor sin hueco fallan.
   Todas las plantillas del paquete se rellenan con los valores que les da
   el código.
2. `compose()`: el orden de §1.1; los delimitadores con su origen; el tope
   de 64 KiB corta y marca; vacío sin instrucciones.
3. Instrucciones del proyecto, en un árbol temporal: de la raíz git hacia
   abajo; `AGENTS.md` gana a `CLAUDE.md` en su carpeta; `CLAUDE.md` de
   otra carpeta sí entra; sin git, solo el directorio actual;
   `compat_claude = false`; un enlace que sale de la raíz o a un secreto
   no se lee; un fichero no UTF-8 se salta con aviso.
4. Usuario: el de `maha`; si falta, `~/.claude/CLAUDE.md`.
5. `instructions`: globs; del proyecto, una ruta fuera o un secreto es un
   error de configuración; sin repetidos; un patrón vacío avisa.
6. El entorno: raíz git por `.git` carpeta y fichero (worktree); la fecha
   sin hora; la nota de "started in" al retomar otra carpeta.
7. El agente manda `system` en cada llamada, igual en todas las de la
   sesión, también tras `/model`; `/new` y `/resume` lo reconstruyen.
8. Los dos adaptadores colocan `system` donde lo espera su API (ya
   probado; se añade un test con el prompt real).
9. `todo_write`: las reglas (vacía, 51, dos `in_progress`, `content` largo)
   vuelven al modelo como error; el resumen; la terminal pinta las
   casillas.
10. `ask_user`: el esquema; la terminal con opciones, "Other" y
    `multi_select`; Ctrl+C; no se registra en `-p`, en evals ni sin
    terminal.
11. Títulos: tras el primer turno, una vez; un fallo deja la primera
    línea; un título a mano gana; el coste entra en la sesión; nada en
    `-p`; escapes y saltos limpiados.
12. `small_model`: configuración, catálogo, el de la sesión; aviso desde el
    proyecto.
13. `/init`: el turno lleva la plantilla y el texto extra; el aviso final.
14. `maha prompt` da el mismo texto que la primera llamada de una sesión
    en ese directorio.
15. La traza apunta el registro `prompt`; la línea base, la huella; el
    aviso de prompt cambiado.
16. Las evals no cargan la capa del usuario (un `AGENTS.md` en el
    `XDG_CONFIG_HOME` del test no aparece).
17. Arquitectura: import-linter con los paquetes nuevos; el test de
    parámetros de herramientas cubre las dos nuevas.
18. Capa de familia: un modelo con `family` y su fichero la lleva detrás de
    la base; sin fichero o sin `family`, no; `system_prompt_file` y
    `--system-prompt-file` quitan base y familia; desde el proyecto,
    `system_prompt_file` es un error de configuración. Todos los modelos
    del catálogo de serie tienen `family`, y cada fichero de `families/`
    es de una familia que existe en el catálogo.

## 5. Evals

El prompt cambia el comportamiento del agente en todo: la batería entera.

- **Tres tareas nuevas** (fixtures pequeños e inventados):
  - `21-convenciones-agents` (train): un `AGENTS.md` con una convención
    que no se deduce del código (por ejemplo, apuntar cada cambio en
    `CHANGELOG.md`); la comprobación mira que se siguió;
  - `22-convenciones-claude` (train): lo mismo con solo `CLAUDE.md`;
  - `23-varios-pasos` (validation): una tarea de varios pasos (renombrar,
    tests y documentación), donde la lista de tareas puede ayudar. Con
    ella, la validación pasa de 4 a 5 de 23 (22 %).
- **Capas de familia** (PR 1, §1.3): con el train (las tareas de
  validación no se miran), una repetición al iterar, para cada familia
  medible (`glm`, `kimi`, `claude`): base sola frente a base + capa. Una
  capa entra solo si mejora éxito, pasos o coste sin empeorar nada, y se
  confirma con la pasada de 5 repeticiones. Los números de cada
  experimento se anotan aquí; si ninguna capa gana, el mecanismo queda
  sin ficheros y se dice.
- **Dos pasadas, una por PR que cambia el comportamiento** (§6): tres
  modelos (`glm-5.3-flash`, `kimi-k2.7-code`, `claude-haiku-5-5`), 5
  repeticiones, contra las líneas base del 2026-11-04. Unos 1,3 $ por
  pasada.
- **Aceptación:**
  - sin ⚠ en las 20 tareas de antes;
  - las tres nuevas, al menos 4/5 en cada modelo;
  - coste y pasos: el prompt añade tokens en cada llamada, la mayoría en
    caché. Una ⚠ de coste se explica con los números (tokens del prompt,
    parte en caché) y la decide el mantenedor;
  - el tamaño de la base, anotado (objetivo, menos de 1.500 tokens).
- **El conjunto de validación no se mira al escribir el prompt.**
- **Líneas base nuevas** al final del hito, con la batería de 23.

El resultado se anota aquí al implementar.

### Resultados (PR 1)

**Pasada 1, 2026-11-04** (`b82ec5c`, prompt base sin capas de familia;
3 modelos, 5 repeticiones, 22 tareas, contra las líneas base del
2026-11-04; sesiones en `~/.local/state/maha/evals/20261104-182436-daa8`
del WSL):

| Modelo | Éxito | Pasos por ejecución | Coste por ejecución |
|---|---|---|---|
| `glm-5.3-flash` | 96 % → 98 % (108/110) | 4,4 → 7,2 (⚠ +65 %) | ⚠ +129 % (0,0007 → 0,0015 $) |
| `kimi-k2.7-code` | 97 % → 98 % (108/110) | 5,3 → 6,5 (+22 %, ruido) | +32 % (ruido) |
| `claude-haiku-5-5` | 100 % → 99 % (109/110, ruido) | 3,4 → 4,3 (⚠ +26 %) | ⚠ +56 % (0,0029 → 0,0045 $) |

- Las tareas 21 y 22 (`AGENTS.md` y `CLAUDE.md`): 15/15 en cada modelo.
- Ninguna ⚠ de éxito; las de pasos y coste, explicadas: en las sesiones de
  train, GLM buscaba cómo lanzar los tests sin `run_command` y escribía
  tests que nadie pidió (tarea 10, de 3 a 9 pasos; tarea 06, "no tengo
  herramienta para ejecutar comandos"). La base pedía "run the tests"
  aunque no hubiera con qué. Arreglado en la base (`d9367e7`): comprobar
  solo con las herramientas que hay; lanzar los tests, en la línea de
  `run_command`.

**Iteración, 2026-11-04** (`d9367e7`; solo train, 1 repetición): pasos por
ejecución en train, GLM 6,6 → 4,5, Kimi 6,0 → 4,4 y Haiku 4,1 → 3,7, ya
cerca de los de la línea base sin prompt (4,4, 5,3 y 3,4); el coste baja
igual. Fallo: GLM, la 08, una vez (lógica).

**Capas de familia:** en los fallos de train de la pasada 1 no hay un
patrón de una familia (GLM, un nombre sin definir en la 12; Kimi, una
respuesta equivocada en la 13; Haiku, ninguno en train). El único patrón
era de la base, y se arregló en la base. Sin un fallo que corregir, ninguna
capa: el mecanismo queda listo y sin ficheros (§1.3).

**Pasada 2 (confirmación)**: la del 2026-11-04 (18:49) se cortó con 164
de 330 ejecuciones y no vale (`20261104-184916-c436`). Repetida el
**2026-11-10** con `9a9333d` (el prompt y el bucle, los de `d9367e7`;
`9a9333d` solo guarda el informe en `report.txt`); 3 modelos, 5
repeticiones, 22 tareas, contra las líneas base del 2026-11-04; sesiones,
`runs.json` (330 ejecuciones) y `report.txt` en
`~/.local/state/maha/evals/20261110-105014-44f6` del WSL. Siete errores
del proveedor (`ReadError`, 120 s sin datos), repetidos con
`--retry-errors`; ninguno queda en el resultado.

Las 20 tareas de antes, frente a la línea base y a la pasada 1:

| Modelo | Éxito | Pasos por ejecución (base → pasada 1 → 2) | Coste por ejecución |
|---|---|---|---|
| `glm-5.3-flash` | 96 % → 98 % (98/100) | 4,4 → 7,2 → 5,1 (+16 %) | ⚠ +95 % (0,0007 → 0,0013 $) |
| `kimi-k2.7-code` | 97 % → 99 % (99/100) | 5,3 → 6,5 → 4,5 (−17 %) | −23 % (0,0055 → 0,0043 $) |
| `claude-haiku-5-5` | 100 % → 100 % (100/100) | 3,4 → 4,3 → 3,7 (+7 %) | ⚠ +34 % (0,0029 → 0,0039 $) |

- Las tareas 21 y 22: 5/5 en cada modelo.
- Ninguna ⚠ de éxito ni de pasos. Fallos, los tres de lógica: GLM en la
  18 y la 20, Kimi en la 14.
- **Las dos ⚠ de coste, con números** (por ejecución, de las trazas; la
  línea base de GLM es la pasada `20261104-140237-e95c` y la de Haiku,
  `20261104-134120-732d`):
  - **GLM:** entrada 6.617 → 10.541 tokens (en caché 4.791 → 7.316),
    salida 469 → 1.017, de ellos razonamiento 68 → 658. Unos 0,0003 $
    de la subida son el prompt (más entrada por llamada); los otros
    0,0003 $, que GLM razona más (en la pasada 1, con casi el mismo
    prompt, eran 195 tokens). En dinero: 0,0006 $ más por ejecución.
  - **Haiku:** escribe en caché 1.508 → 3.642 tokens por ejecución. Cada
    ejecución de las evals es una sesión nueva: la primera llamada paga
    escribir el prompt en la caché, y las siguientes lo leen (el 68 % de
    la entrada sale de la caché). En una conversación, esa escritura se
    paga una vez por sesión, no por turno. 0,0010 $ más por ejecución.
- El prompt base: 2.285 bytes (traza de la verificación, 2026-11-10),
  unos 600 tokens a 4 bytes por token, una estimación; por debajo del
  objetivo de 1.500.
- **Decisión del mantenedor (2026-11-10): se aceptan las dos ⚠ de
  coste.** Motivo: el prompt cuesta tokens en cada llamada, la mayoría
  leídos de la caché; la escritura en caché de Haiku se paga una vez por
  sesión, y cada ejecución de las evals es una sesión; el resto de la
  subida de GLM es razonamiento, que varía entre pasadas. Éxito y pasos,
  sin ⚠.

**Verificación a mano del PR 1** (§7, puntos 1 a 4 y 9; 2026-11-10, en
un directorio desechable con git, OpenCode Go): todos bien. Sin
`AGENTS.md`, el modelo acierta el directorio y la fecha; con `AGENTS.md`,
y luego con solo `CLAUDE.md`, la línea `[instructions: …]` lo nombra y
el modelo lo sigue; `maha prompt` enseña las capas,
`--append-system-prompt` va al final y `--system-prompt-file` cambia la
base; al retomar desde otra carpeta, el modelo dice la nueva; con
`claude-haiku-5-5`, la segunda llamada lee 2.863 tokens de la caché.
Ese dato solo estaba en el JSONL de la traza: desde `3163936`, `/trace`
y `maha trace` lo enseñan (`5899 in (2863 cached)`).

### Resultados (PR 2)

Tres pasadas completas y tres de train, todas del 2026-11-10, en el WSL
(`~/.local/state/maha/evals/`). Las sesiones de validación no se miraron
al ajustar.

**Pasada 1** (`f9db6bb`; `20261110-125516-bd6d`): sin ⚠ de éxito; la 23,
5/5 en cada modelo. Pero Kimi usaba `todo_write` de más: 55 llamadas, en
10 tareas, también en trabajos de una o dos ediciones (`is_even`,
`slugify`), con listas de una tarea o con tareas como "Verificar con los
tests". Frente al PR 1, +12 % de pasos y +21 % de coste. Ninguno de sus
fallos de train usó la lista.

**El ajuste** (`faf0955`), con sesiones de train y una tarea larga a mano
en un directorio desechable:
- la guía y la descripción: solo para trabajo de tres cambios o más; cada
  tarea es un cambio, nunca una lectura ni una comprobación; cada
  actualización, en la misma respuesta que la llamada que empieza la
  siguiente tarea, y la última con el último cambio;
- GLM y Haiku dejaban la lista sin cerrar en la tarea larga. El resultado
  de `todo_write` recuerda mantenerla al día mientras quedan tareas, como
  hace Claude Code. Con eso, los tres modelos terminan la tarea larga con
  la lista al día.
- Train, una repetición: Kimi, de 4,71 a 4,17 pasos por ejecución; sin
  listas en las tareas cortas.

**Pasada 2, de confirmación** (`faf0955`; `20261110-134033-fb60`). Las
20 tareas de antes, frente a la línea base y a la pasada del PR 1:

| Modelo | Éxito (base → PR 1 → PR 2) | Pasos (base → PR 1 → PR 2) | Coste por ejecución |
|---|---|---|---|
| `glm-5.3-flash` | 96 % → 98 % → 93 % (93/100) | 4,4 → 5,1 → 4,9 | ⚠ +78 % (0,0007 → 0,0012 $); −9 % frente al PR 1 |
| `kimi-k2.7-code` | 97 % → 99 % → 97 % (97/100) | 5,3 → 4,5 → 4,4 | −15 %; +10 % frente al PR 1 |
| `claude-haiku-5-5` | 100 % → 100 % → 100 % | 3,4 → 3,7 → 3,7 | ⚠ +48 % (0,0029 → 0,0043 $); +11 % frente al PR 1 |

- Las tres tareas nuevas: 5/5 en cada modelo (la 23, de varios pasos,
  también).
- Ninguna ⚠ de éxito. GLM, 93 % (p = 0,27, dentro del ruido): sus fallos
  de train, en la 12, la 13, la 16 y la 20, son de lógica o de la
  respuesta, y ninguna de esas sesiones usó la lista. Para no quedarse
  con la duda, su train otra vez con 5 repeticiones
  (`20261110-145733-8128`): 88/90 (98 %). Juntas, 174/180 (96,7 %); la
  12 y la 13 son las que GLM ya fallaba antes. Es ruido.
- `todo_write` en train, por cada 18 ejecuciones: Kimi, de 6,2 llamadas a
  0,8; GLM, 0,4; Haiku, 0,4.
- **El coste, frente al PR 1:** +10 % en Kimi y +11 % en Haiku: las dos
  herramientas nuevas van en cada llamada (sus descripciones y su
  esquema), la mayoría desde la caché. GLM baja.
- **Decisión del mantenedor (2026-11-10): se aceptan las dos ⚠ de
  coste.** Motivo: la mayor parte es el prompt de sistema, ya aceptado en
  el PR 1; lo que añade este PR son las dos herramientas nuevas en cada
  llamada, la mayoría leída de la caché; éxito y pasos, sin ⚠. Antes de
  aceptarlas, el mantenedor pidió no tomar la decisión fácil: de ahí el
  ajuste de `todo_write` y la pasada de confirmación.

**Verificación a mano del PR 2** (§7, puntos 6 y 7; 2026-11-10, en una
pseudoterminal y en directorios desechables con git, OpenCode Go): una
tarea de varios pasos pinta la lista (`▸` la tarea en curso, `☐` las
pendientes) y la deja al día al terminar; `ask_user` enseña la pregunta
con sus opciones y "Other"; elegir un número y escribir "Other" con texto
propio llegan al modelo; Ctrl+C en la pregunta da `[interrupted]`, y en
el turno siguiente el modelo sabe que quedó sin respuesta.

## 6. Orden de piezas para el implementador

**PR 1 — las capas** (`feature/hito-10-capas`)
1. `domain/prompt.py`: `render`, `Layer`, `compose`, tope y huella.
   *Commit:* "Componer el system prompt por capas en el dominio"
2. `family` en el catálogo (dominio, `models.toml` de serie y el de la
   persona) y la capa de familia. *Commit:* "Dar a cada modelo del
   catálogo su familia"
3. `prompts/base.md` y el test de plantillas. *Commit:* "Escribir el prompt
   base de maha"
4. `ports/project.py` y `adapters/project/local.py`: raíz git y entorno.
   *Commit:* "Detectar la raíz git y el entorno del directorio"
5. Las instrucciones del proyecto y del usuario, con `compat_claude`.
   *Commit:* "Leer AGENTS.md y, si falta, CLAUDE.md"
6. `instructions` en la configuración. *Commit:* "Añadir las instrucciones
   extra de la configuración"
7. `application/prompt.py` y `system` en el agente y en las sesiones.
   *Commit:* "Mandar el system prompt en cada llamada"
8. La línea al arrancar y los avisos. *Commit:* "Decir al arrancar qué
   instrucciones se han cargado"
9. `maha prompt` y las tres opciones. *Commit:* "Añadir maha prompt y las
   opciones del system prompt"
10. La traza y la huella en la línea base. *Commit:* "Apuntar la huella del
    prompt en la traza y en la línea base"
11. Evals sin capa de usuario; tareas 21 y 22. *Commit:* "Añadir a las
    evals las tareas de AGENTS.md y CLAUDE.md"
12. Las capas de familia que las evals justifiquen (§5), una por commit.
    *Commit:* "Añadir la capa de la familia <familia>"
13. Evals (§5), anotadas aquí. *Commit:* "Anotar las evals del system
    prompt"

**PR 2 — las herramientas** (`feature/hito-10-herramientas`)
1. `domain/todo.py` y `TodoWrite`. *Commit:* "Añadir la herramienta
   todo_write"
2. La lista en la terminal. *Commit:* "Pintar la lista de tareas en la
   terminal"
3. `domain/question.py`, `UserQuestions` y `AskUser`. *Commit:* "Añadir la
   herramienta ask_user"
4. Las preguntas en la terminal, y el registro solo con persona.
   *Commit:* "Preguntar a la persona en la terminal"
5. La tarea 23. *Commit:* "Añadir a las evals una tarea de varios pasos"
6. Evals (§5), anotadas aquí. *Commit:* "Anotar las evals de las
   herramientas nuevas"

**PR 3 — `/init` y los títulos** (`feature/hito-10-init-titulos`)
1. `prompts/init.md` y `/init`. *Commit:* "Añadir /init"
2. `small_model` en el catálogo y en la configuración. *Commit:* "Elegir
   el modelo pequeño de cada proveedor"
3. `TitleEntry` y `application/titles.py`. *Commit:* "Titular las sesiones
   con el modelo pequeño"
4. `/rename`. *Commit:* "Añadir /rename"

**Cierre** (`feature/hito-10-cierre`): verificación a mano (§7), líneas
base nuevas, nota 10 de la guía, los dos README, PROYECTO, ESTADO,
HISTORIAL, MAPA, spec IMPLEMENTADA y `v0.10.0`.

## 7. Verificación a mano

En un directorio desechable con git, con OpenCode Go:
1. Sin `AGENTS.md`: no hay línea de instrucciones; "¿en qué directorio
   estás y qué día es?" acierta.
2. Con `AGENTS.md` ("responde siempre con la palabra PIÑA al final"): la
   línea lo nombra y el modelo lo sigue. Con solo `CLAUDE.md`, igual.
3. `maha prompt` enseña las capas; `--append-system-prompt` se ve al
   final; `--system-prompt-file` cambia la base.
4. Retomar desde otra carpeta: el modelo sabe dónde trabaja ahora.
5. `/init` escribe un `AGENTS.md` útil tras pedir permiso; el aviso de
   `/new`.
6. Una tarea de varios pasos pinta la lista de tareas.
7. Una petición ambigua hace que el modelo pregunte con `ask_user`; elegir
   una opción y "Other".
8. `/sessions` enseña el título nuevo; `/rename` lo cambia.
9. Con `claude-haiku-5-5`: la segunda llamada lee el prompt de la caché
   (`cache_read` en `/trace`).

## 8. Lo que no viaja por git y lo que necesita la release

- Nada nuevo en `.env`.
- Opcional, en cada PC: `~/.config/maha/AGENTS.md` con instrucciones
  personales. Va a `docs/PUESTA_EN_MARCHA.md`.
- `docs/MAPA.md`: los ficheros nuevos de §3.1 y las tareas 21 a 23.

## 9. Guía

`docs/guia/10-system-prompt.md`, "El system prompt: lo que el modelo sabe
antes de leerte":
1. Qué es el system prompt y por qué va aparte de los mensajes.
2. Las capas y su orden, y por qué el orden importa para la caché.
3. `AGENTS.md`: instrucciones de proyecto como estándar abierto, y por qué
   no cambian permisos.
4. Los prompts son código: plantillas en el repo, revisadas y medidas con
   evals.

## 10. Riesgos

- **El prompt empeora algún modelo.** Las evals con tres familias lo ven;
  la capa de esa familia lo corrige, medida (§1.3).
- **Una familia que no se puede medir aquí** (`gpt`, `gemini`) va solo con
  la base hasta tener su eval. Se dice en la guía y en ESTADO.
- **Más tokens por llamada.** Mitigado por la caché; se mide (§5).
- **`AGENTS.md` maliciosos.** No tocan permisos (§1.6); se ven al arrancar.
- **`ask_user` molesta** si el modelo pregunta de más. El prompt base pide
  preguntar solo cuando no se puede seguir; se ve en la verificación (§7).
- **El paquete sin las plantillas.** `uv_build` incluye los ficheros del
  paquete (ya lo hace con `models.toml`); un test lee las plantillas del
  paquete instalado.

## 11. Decisiones

Propuestas del agente, pendientes del mantenedor (aprobar el PR de esta
spec las aprueba):

1. **Todo en el system prompt, fijado por sesión** (§1.1, §1.2), en lugar
   del mensaje de usuario de Claude Code. Da la misma caché y sigue
   DESIGN §5 y §8.
2. **Una base común y una capa por familia de modelo** (§1.3), con la
   familia explícita en el catálogo. Una capa solo entra medida con evals;
   las familias que no se pueden medir aquí quedan con el mecanismo listo
   y sin fichero. La persona cambia la base con `system_prompt_file` o
   `--system-prompt-file`. *(Revisada el 2026-11-04 a petición del
   mantenedor: la propuesta era un solo prompt base, con capas de familia
   solo si las evals lo pedían; con el criterio de "lo más profesional,
   completo y adaptable", el mecanismo va desde el principio.)*
3. **Plantillas propias `{{hueco}}`**, sin Jinja2 (§1.3).
4. **`CLAUDE.md` por compatibilidad, encendido por defecto**, solo donde no
   hay `AGENTS.md` (§1.4).
5. **Los imports `@` de `CLAUDE.md` no se expanden** (como OpenCode): el
   modelo puede leer el fichero si el texto se lo pide (§0).
6. **Los `AGENTS.md` de subcarpetas, al hito 11; las reglas por ruta, al
   hito 13** (§0). Se anotan en ESTADO, "Con hito asignado".
7. **Tope de 64 KiB** para todas las instrucciones (§1.4).
8. **`instructions` del proyecto, solo dentro del proyecto y sin
   secretos** (§1.5).
9. **`ask_user` solo con persona** (§1.11); **`todo_write` para todos los
   modelos**, medido (§1.10).
10. **Títulos con `small_model`**, del catálogo por proveedor, solo en
    sesiones interactivas, y **`/rename`** (§1.12). `/rename` estaba como
    "mejora pequeña" en la comparativa; entra aquí porque va con los
    títulos.
11. **`--system-prompt-file` sustituye solo la base** (§1.8), no todo como
    en Claude Code: el entorno y el `AGENTS.md` siguen haciendo falta.
12. **La huella del prompt en la traza y en la línea base**, sin el texto
    entero (§1.13).

## 12. Aprendido al implementar

**PR 2 (2026-11-10):**
- **La lista se pinta al terminar la llamada, no al proponerla** (§3.3
  decía con `ToolCallProposed`): así solo se ve una lista válida; una
  llamada que no valida se enseña como cualquier otra, con su error.
- **El ejemplo de §1.11 no cumple su propio esquema:** `"Base de
  datos"` tiene 13 caracteres, y el tope de `header` es 12. Lo cazó un
  test.
- **Topes que el esquema no decía,** para que el modelo no llene la
  pantalla: `label` hasta 60 caracteres, `description` hasta 200,
  `question` hasta 500; las etiquetas de una pregunta y las preguntas, sin
  repetir; ninguna opción se puede llamar "Other", que la añade maha.
- **`ask_user` no enseña su línea de llamada:** sus preguntas ya se ven.
  Si sus argumentos no valen, se enseña la línea con el error.
- **El reloj del turno se para mientras la persona responde:** el puerto
  `Tool` gana `waits_for_user`, y el bucle hace con esa herramienta lo
  mismo que con una aprobación (decisión B4 de la auditoría).
- **En `-p`, una llamada denegada corta el turno** (spec 5, §1.4): una
  lista de tareas queda a medias por eso, no por el modelo. Al medir a
  mano cuánto se cierra la lista, hay que permitir lo que la tarea
  necesita.
- **La guía de una herramienta se mide como el prompt:** la primera
  versión de la de `todo_write` subió los pasos de Kimi un 12 %. Ver §5,
  "Resultados (PR 2)".

