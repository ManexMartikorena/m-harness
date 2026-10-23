Estado: PROPUESTA (2026-10-21) → APROBADA (2026-10-21, sin cambios)

# Spec — Hito 5: Permisos y herramientas con efecto

Referencias: `docs/DESIGN.md` §4, §5 (contrato), §6 (`ApprovalGate`,
`CommandRunner`), §8 (supervisión), §10 (permisos, perímetro, secretos,
terminal) y §14 (hito 5); `docs/ANALISIS.md` §5 (pieza 4); spec del hito 4
(§1.5 a §1.8, pendientes); `AGENTS.md`.

## 0. Alcance

**El problema.** `maha` solo puede mirar. Para ser un agente de código tiene
que escribir y editar ficheros y ejecutar comandos. Eso tiene efecto en tu
máquina, así que **nada con efecto puede pasar sin que tú lo apruebes**
(DESIGN §8 y §10). Además, el hito 4 dejó tres cosas pendientes: leer fuera
del directorio con aprobación, revisar el turno atómico y `refusal`.

**Lo que hace este cambio.** Tres herramientas con efecto (`write_file`,
`edit_file`, `run_command`). Antes de ejecutar una, `maha` te enseña qué va a
hacer (el diff, el comando) y te pregunta:

```
  → edit_file(path="src/app.py", old_string="return 1", new_string="return 2")
  ┌ edit src/app.py
  │ @@ -3 +3 @@
  │ -    return 1
  │ +    return 2
  └ Allow? [y] yes · [a] always this session · [n] no: y
  ✓ 1 replacement
```

Dentro de alcance:
- Contrato de aprobación: `ApprovalRequest`, `Decision`, puerto
  `ApprovalGate` y `Tool.approval()` (§1.2).
- Aprobación "para toda la sesión" por ámbito (§1.3).
- El bucle pregunta antes de ejecutar; una negativa termina el turno (§1.4).
- El turno guarda lo que se ejecutó, aunque falle o se cancele (§1.5).
- Leer fuera del directorio o un secreto: con aprobación, siempre una a una
  (§1.6).
- `write_file` y `edit_file` (§1.7, §1.8).
- `run_command`, el puerto `CommandRunner` y su adaptador local (§1.9).
- La aprobación en la terminal; sin terminal, se deniega (§1.10).
- `refusal` del modelo, como texto (§1.11).
- Nota 05 de la guía y docs al día.

**Fuera de alcance** (y por qué):
- Aislamiento de los comandos (sandbox): hito 14. Aquí el comando corre con
  tus permisos; la defensa es la aprobación (§1.9).
- Reglas de permisos en configuración (allow/deny por patrón, como Claude
  Code): sin hito; DESIGN §8 fija que la única autonomía es "aprobar para
  toda la sesión".
- Recordar aprobaciones entre ejecuciones de `maha`: las sesiones son del
  hito 6; las aprobaciones mueren con el proceso.
- Política automática de aprobación para evals: hito 8.
- Borrar o mover ficheros como herramientas propias: se hace con
  `run_command`, con aprobación.

## 1. Decisiones de fondo

### 1.1 Hechos comprobados

Todos el 2026-10-21 por el agente.

- **Python 3.14, documentación oficial:**
  - `asyncio.create_subprocess_shell(cmd, stdin, stdout, stderr, limit, **kwds)`
    lanza un comando de shell; los demás parámetros son los de
    `loop.subprocess_exec()`
    (https://docs.python.org/3.14/library/asyncio-subprocess.html).
  - `Process.wait()` "puede bloquearse" con `stdout=PIPE` si el hijo escribe
    más de lo que cabe en la tubería: hay que leer la salida mientras corre.
    `communicate()` y `wait()` no tienen `timeout`: se usa `wait_for()`.
    `kill()` manda SIGKILL al hijo.
  - `process_group=0` (desde 3.11) hace `setpgid(0, 0)` en el hijo: un grupo
    de procesos propio
    (https://docs.python.org/3.14/library/subprocess.html).
  - `os.killpg(pgid, sig)` manda una señal a un grupo de procesos (Unix)
    (https://docs.python.org/3.14/library/os.html).
  - `difflib.unified_diff(a, b, fromfile, tofile, n=3)` da el diff en formato
    unificado (https://docs.python.org/3.14/library/difflib.html).
- **Prueba local** (agente, Python 3.14.8, WSL): con `process_group=0`, un
  `sh -c "sleep 30 & …"` cancelado y luego `os.killpg(pid, SIGKILL)` no deja
  ningún proceso del grupo vivo, nieto incluido. Con `wait_for(communicate(),
  timeout)`, al vencer se pierde la salida parcial: hay que leerla poco a
  poco (§1.9).
- **Terminal (POSIX):** Ctrl+C manda SIGINT a todo el grupo de procesos en
  primer plano. Un hijo en su propio grupo no lo recibe: `maha` decide
  cuándo matarlo, y lo mata entero.

### 1.2 Contrato de aprobación

**Dónde:** `domain/approval.py`, `ports/approval.py` y `ports/tools.py`.

```python
type Decision = Literal["once", "session", "deny"]


class ApprovalRequest(BaseModel, frozen=True):
    tool: str
    title: str  # "edit src/app.py", "run: uv run pytest"
    detail: str  # the diff, the command and its directory…
    scope: str | None  # what "always this session" covers; None: not offered
    warning: str | None = None  # "outside the working directory", "secret file"


class ApprovalGate(Protocol):
    async def decide(self, request: ApprovalRequest) -> Decision: ...


class Tool[P: BaseModel](Protocol):
    ...

    def approval(self, params: P) -> ApprovalRequest | None:
        """What to ask before running, or None. May raise ToolError."""
```

- **La herramienta sabe qué preguntar:** solo ella puede calcular el diff de
  una edición o saber si una ruta sale del directorio. El bucle solo pregunta
  y decide (§1.4).
- **`approval()` va antes de `run()` y puede fallar:** un `old_string` que no
  está, o una ruta que no existe, dan `ToolError` sin molestarte con una
  pregunta inútil.
- **Una herramienta `effect` siempre pregunta.** Si su `approval()` devuelve
  `None`, el bucle lo trata como un fallo nuestro y **no la ejecuta**. Un test
  lo fija.
- **El permiso sigue siendo código** (AGENTS.md): el modelo no puede saltarse
  la pregunta; solo propone.

### 1.3 "Aprobar para toda la sesión", por ámbito

**Dónde:** `application/approvals.py` (`SessionApprovals`).

Responder `a` guarda el `scope` de la petición; las siguientes con el mismo
`scope` se aprueban solas hasta que `maha` termina.

| Herramienta | `scope` |
|---|---|
| `write_file`, `edit_file` dentro del directorio | `"write_file"`, `"edit_file"`: todas las escrituras o ediciones |
| `run_command` | `"run_command:<comando exacto>"`: solo ese comando |
| Leer o escribir **fuera** del directorio, o un **secreto** | `None`: siempre se pregunta, sin opción `a` |

- **Por qué el comando exacto:** aprobar "todos los comandos" sería dar la
  terminal entera; aprobar `uv run pytest` para la sesión es lo útil.
  Prefijos o patrones (como Claude Code) quedan fuera (§0).
- **Mejora futura, anotada al aprobar:** aprobar por prefijo
  (`uv run pytest *`) es más cómodo para el producto final: con el comando
  exacto, cada variante vuelve a preguntar. Se valora cuando `maha` trabaje
  en su propio repo y resulte pesado, con su propia spec de mejora.
- **Por qué nunca para la sesión fuera del perímetro o con secretos:** son las
  dos cosas que DESIGN §10 pide "explícitamente" una a una.
- *(Añadido 2026-10-21, decisión del mantenedor; ver §12.12.)* Escribir o
  editar en `.git` también pregunta siempre (`scope=None`): sus hooks y su
  config ejecutan código. Leer en `.git` no cambia.
- Ver duda 2 de §11.

### 1.4 El bucle pregunta; una negativa termina el turno

**Dónde:** `application/agent.py`.

Para cada llamada, tras validar los argumentos (hito 4, §1.8):
1. `request = tool.approval(params)`; un `ToolError` aquí es un resultado de
   error, como en el hito 4.
2. Si hay `request`:
   - si su `scope` ya está aprobado para la sesión → se ejecuta;
   - si no → evento `ApprovalRequested(call, request)` y
     `await gate.decide(request)`.
3. `once` o `session` → se ejecuta (`session` guarda el `scope`).
4. **`deny` → resultado `error: the user denied this call`, las llamadas
   siguientes de la misma respuesta no se ejecutan (`error: not run: a
   previous call was denied`) y el turno termina** con
   `TurnFinished(reason="denied")`, sin volver a llamar al modelo.

- **Por qué terminar el turno:** si dices que no, quieres decir algo. Si el
  bucle siguiera, el modelo probaría otra cosa y te volvería a preguntar. Al
  terminar, escribes tú. Ver duda 1 de §11.
- `ToolFinished` lleva `decision` (`once`, `session`, `deny`, o `None` si no
  hizo falta preguntar): para las trazas del hito 7.

### 1.5 El turno guarda lo que se ejecutó

**Dónde:** `application/agent.py`. Revisa el "turno atómico" del hito 4
(§1.7), como pedía su spec.

**Regla: lo que se ejecutó, consta.**
- Si falla una llamada al modelo o pulsas Ctrl+C **antes de que se ejecute
  ninguna herramienta**, no se guarda nada (como en los hitos 3 y 4: puedes
  repetir la pregunta).
- Si ya se ejecutó alguna, **se guarda el turno hasta el último resultado
  completo**. La respuesta del modelo a medias se descarta.
- **Ctrl+C durante una herramienta:** el mensaje del asistente con sus
  llamadas ya está completo, así que se guarda con un resultado para cada
  llamada: las acabadas, con el suyo; la que corría, `error: cancelled by the
  user`; las siguientes, `error: not run`. Cada llamada queda emparejada con
  su resultado (OpenAI lo exige, spec 4 §1.1).
- **Por qué:** si `maha` editó un fichero y luego falló la red, el modelo
  tiene que saber que el fichero ya está editado. Si no, lo editaría otra vez.

### 1.6 Leer fuera del directorio o un secreto: con aprobación

**Dónde:** `adapters/tools/files.py` (las herramientas de lectura ganan
`approval()`).

| Caso | Hito 4 | Hito 5 |
|---|---|---|
| `read_file` / `list_dir` / `glob` / `grep` con una ruta **fuera** del directorio | Denegado | Pregunta (`scope=None`, aviso "outside the working directory") |
| `read_file` de un **secreto** | Denegado | Pregunta (`scope=None`, aviso "secret file: its content goes to the model provider") |
| `list_dir` de una carpeta secreta | Denegado | Pregunta, como un secreto |
| `glob` / `grep` encuentran un secreto al recorrer | Se salta | Se sigue saltando, sin preguntar |
| Enlaces que salen fuera al recorrer | Se saltan | Se siguen saltando |

- Leer **dentro** y no secreto sigue sin preguntar (`READ`, DESIGN §10).
- La pregunta enseña la ruta resuelta, no la que escribió el modelo: un
  enlace no puede disfrazar a dónde va.
- *(Añadido 2026-10-21, decisión del mantenedor; ver §12.12.)* Con aviso
  (fuera, secreto o `.git`), la pregunta va antes de los errores que dependen
  del contenido (binario, no UTF-8, `old_string` que no está…): si no, el
  modelo podría sondear un secreto sin pregunta. Antes solo salen los de
  metadatos y parámetros.

### 1.7 `write_file`

**Dónde:** `adapters/tools/files.py`.

`write_file(path, content)`: crea el fichero (y sus carpetas) o lo
sobrescribe entero. `effect`.

- **Pregunta**, con:
  - fichero nuevo → `create notas.txt (3 lines)` y sus primeras 20 líneas;
  - existente → `overwrite notas.txt` y el diff unificado.
- `scope`: `"write_file"` dentro; `None` fuera o si es un secreto.
- Escribe en UTF-8 tal cual (sin cambiar los saltos de línea). Devuelve
  `wrote notas.txt (3 lines)`.
  *(Añadido 2026-10-21, decisión del mantenedor; ver §12.)* La escritura es
  **atómica** (temporal en la misma carpeta y `os.replace`); `edit_file`
  usa la misma.
- Una carpeta en `path` → `ToolError`.

### 1.8 `edit_file`

**Dónde:** `adapters/tools/files.py`.

`edit_file(path, old_string, new_string, replace_all=False)`: cambia un texto
exacto por otro. `effect`.

- `old_string` tiene que aparecer **exactamente una vez** (o
  `replace_all=True`). Si no aparece o aparece varias veces → `ToolError` en
  `approval()`, antes de preguntarte. El modelo puede corregirse leyendo el
  fichero.
  *(Corregido 2026-10-21, decisión del mantenedor; ver §12.)* **Adaptación a
  CRLF:** si hay 0 coincidencias exactas, `old_string` contiene `\n` sueltos
  y el fichero contiene `\r\n`, se busca con esos `\n` pasados a `\r\n`, y
  `new_string` se escribe adaptado igual. La coincidencia exacta tiene
  prioridad. Por qué: `read_file` no muestra los `\r`; sin esto, toda edición
  de varias líneas en un fichero CRLF fallaría.
- **Pregunta** con el diff unificado (3 líneas de contexto, a lo sumo 60
  líneas de diff; más, con un aviso de cuántas faltan).
- `scope`: `"edit_file"` dentro; `None` fuera o en un secreto.
- Lee y escribe con `newline=""`: un fichero con CRLF sigue con CRLF. Solo
  UTF-8 válido: si no lo es, `ToolError` (editar con `errors="replace"`
  estropearía el fichero).
- `old_string` igual a `new_string` → `ToolError` ("nothing to change").
- Devuelve `edited app.py (1 replacement)`.
- **Sin "leer antes de editar"** obligatorio (Claude Code lo exige): el
  `old_string` exacto ya obliga a conocer el texto. Se valora en el hito 8
  con evals.

### 1.9 `run_command` y el puerto `CommandRunner`

**Dónde:** `ports/commands.py`, `adapters/commands/local.py` y
`adapters/tools/shell.py`.

```python
class CommandResult(BaseModel, frozen=True):
    exit_code: int | None  # None if it was killed
    output: str  # stdout and stderr, interleaved, maybe cut
    truncated: bool
    timed_out: bool


class CommandRunner(Protocol):
    async def run(
        self, command: str, *, cwd: Path, timeout: float
    ) -> CommandResult: ...
```

`run_command(command, timeout=120)`: ejecuta un comando de shell en el
directorio de trabajo. `effect`; `timeout` de 1 a 600 s.

- **Pregunta** con `run: <comando>` y el directorio. `scope`:
  `"run_command:<comando>"`.
- **Adaptador local:**
  - `create_subprocess_shell` con `process_group=0`, `stdin` cerrado
    (`DEVNULL`: un comando que pide datos no se queda esperando) y
    `stderr` a `stdout`;
  - lee la salida **mientras corre**, en trozos, hasta 30 000 caracteres; lo
    que sobra se lee y se tira, para que el hijo no se bloquee (§1.1);
  - al pasar el tiempo, o si cancelan la tarea (Ctrl+C), **mata el grupo
    entero** con `os.killpg(…, SIGKILL)` en un `finally`; la salida leída
    hasta entonces se conserva.
- **Entorno sin credenciales:** el comando hereda el entorno de `maha`
  **menos** las variables con credenciales: la de la clave del proveedor
  configurado y cualquier nombre que acabe en `_API_KEY`, `_TOKEN`,
  `_SECRET` o `_PASSWORD` (sin mirar mayúsculas). Si no, un `env` o un
  `echo $OPENCODE_API_KEY` mandaría tu clave al modelo (AGENTS.md: las
  credenciales nunca salen).
- **Resultado** para el modelo:

  ```
  exit code: 1
  …salida…
  … [output cut at 30000 characters]
  ```

  y `[timed out after 120 s]` si pasó el tiempo. Un código distinto de 0 no
  es un error de la herramienta: es información para el modelo.
- **Sin perímetro:** un comando puede hacer `cd ..` o tocar cualquier cosa
  que puedas tocar tú. Hasta el sandbox (hito 14), **la única defensa es que
  lees el comando antes de aprobarlo**. La pregunta lo deja claro.
- Sin hilos (`asyncio` puro), como el resto (spec 4, §1.6).

### 1.10 La aprobación en la terminal

**Dónde:** `adapters/cli/approval.py` (`TerminalApproval`), cableado en
`bootstrap`.

```
  ┌ run: uv run pytest -q
  │ in /home/ane/proyecto
  └ Allow? [y] yes · [a] always this session · [n] no:
```

- Lee la respuesta con el mismo lector de la conversación (`StdinLines`, sin
  hilos). `y`/`yes`/`s`/`sí` → `once`; `a` → `session` (solo si hay
  `scope`); `n`/`no` → `deny`; otra cosa → se repite la pregunta; Ctrl+D →
  `deny`.
- Con aviso, una línea más en amarillo: `│ ! outside the working directory`.
- `detail` se corta a 60 líneas y cada línea a 200 caracteres.
- *(Añadido 2026-10-21, decisión del mantenedor tras la revisión del PR 2;
  ver §12.12.)* **Requisito para la pieza 14:** antes de pintar `title`,
  `detail` y `warning`, se sanean sus caracteres de control (ESC, `\r`…).
  Por qué: un fichero o un argumento del modelo con secuencias de terminal
  podría falsear lo que ves en la pregunta.
- **Sin terminal, se deniega sin preguntar.** Con `maha < notas.txt`, la
  "respuesta" sería la siguiente línea del fichero: una línea que empiece por
  "y" aprobaría un comando. `bootstrap` usa entonces `DenyAll`, que escribe
  `(denied: input is not a terminal)`. Un test lo fija.
- Ctrl+C durante la pregunta: corta el turno, como en cualquier otro momento
  (§1.5).

### 1.11 `refusal`, como texto

**Dónde:** `adapters/models/openai_chat.py`. Pendiente desde la spec 3 (§10).

Si el modelo se niega, OpenAI lo manda en `delta.refusal` (stream) o
`message.refusal` (sin stream), no en `content`. Hoy se pierde en silencio.
Se emite como `TextDelta` / `TextBlock`: lo ves y queda en el historial. Ver
duda 4 de §11.

## 2. En la industria

| Pieza | M-Harness | Alternativas | Cuándo se elegirían |
|---|---|---|---|
| Aprobaciones | Una vez / sesión por ámbito / no, en código | Reglas allow/ask/deny por patrón (Claude Code); modos de aprobación (Codex: `suggest`, `auto-edit`, `full-auto`); *human-in-the-loop* de LangGraph (`interrupt`) | Muchos comandos repetidos; flujos sin persona |
| Editar ficheros | `old_string` → `new_string` exacto | Diffs o parches (aider, Codex `apply_patch`); reescribir el fichero entero | Cambios grandes o muchos ficheros a la vez |
| Ejecutar comandos | Subproceso local con grupo propio, tiempo límite y sin credenciales | Contenedor o sandbox (Codex con seatbelt/landlock, E2B, Docker) | Código no confiable: hito 14 |
| Credenciales | Fuera del entorno del comando | Gestores de secretos; contenedores sin red | Equipos y producción |
| Sin terminal | Denegar todo | Política automática configurable | Evals y CI (hito 8) |

*Solo se citan categorías y herramientas; no se afirma el comportamiento de
ningún producto concreto más allá de su documentación pública.*

## 3. Diseño de detalle

### 3.1 Ficheros

```
src/mharness/
├── domain/approval.py            # nuevo: Decision, ApprovalRequest
├── domain/agent_events.py        # ApprovalRequested; ToolFinished.decision; reason "denied"
├── ports/approval.py             # nuevo: ApprovalGate
├── ports/tools.py                # Tool.approval()
├── ports/commands.py             # nuevo: CommandRunner, CommandResult
├── application/approvals.py      # nuevo: SessionApprovals
├── application/tools.py          # el registro ya acepta herramientas effect
├── application/agent.py          # pregunta; negativa; lo ejecutado consta
└── adapters/
    ├── tools/files.py            # approval() en las de lectura; write_file, edit_file
    ├── tools/shell.py            # nuevo: run_command
    ├── commands/local.py         # nuevo: LocalCommandRunner
    ├── cli/approval.py           # nuevo: TerminalApproval, DenyAll
    ├── cli/conversation.py       # muestra decisiones; reason "denied"
    └── models/openai_chat.py     # refusal
bootstrap.py                      # cablea gate, runner y las 7 herramientas
tests/fakes/approval.py           # nuevo: FakeApproval
tests/fakes/commands.py           # nuevo: FakeRunner
docs/guia/05-permisos.md
```

`adapters/tools/shell.py` usa el puerto `CommandRunner`, no el adaptador
local: no importa otro adaptador (AGENTS.md). `bootstrap` los une.

### 3.2 Descripciones nuevas

```
write_file: Create or overwrite a text file in the working directory. The
  user approves it first. Example: {"path": "notes.txt", "content": "…"}
edit_file: Replace an exact text in a file. old_string must appear exactly
  once (or use replace_all). Read the file first. The user approves it.
  Example: {"path": "app.py", "old_string": "return 1", "new_string": "return 2"}
run_command: Run a shell command in the working directory, with a timeout.
  The user approves it first. Example: {"command": "uv run pytest -q"}
```

### 3.3 Configuración nueva

Ninguna. La variable de la clave que se quita del entorno sale de la
configuración del proveedor que ya existe (`api_key_env`).

## 4. Plan de tests

Sin llamadas reales ni red. Disco: solo en `tmp_path`. Comandos reales solo
en los tests del adaptador local, inocuos (`echo`, `sleep`, `printf`).

**4.1 Dominio y sesión** (`tests/unit/test_approvals.py`)
1. `SessionApprovals`: `session` guarda el `scope`; `None` nunca se guarda.

**4.2 Bucle** (`tests/unit/test_agent.py`, con `FakeApproval`)
1. Una herramienta de lectura sin petición no pregunta.
2. `once` ejecuta; `ApprovalRequested` antes y `decision="once"` en
   `ToolFinished`.
3. `session`: la segunda llamada con el mismo `scope` no pregunta; con otro,
   sí; con `scope=None`, siempre.
4. `deny`: resultado de error, las siguientes de la respuesta "not run",
   `TurnFinished("denied")` y ninguna llamada más al modelo.
5. Herramienta `effect` cuyo `approval()` devuelve `None` → no se ejecuta,
   error interno.
6. `approval()` con `ToolError` → resultado de error sin preguntar.
7. Lo ejecutado consta: fallo del modelo en el paso 2 tras una herramienta →
   el turno se guarda hasta el resultado; Ctrl+C durante la 2.ª de 3
   llamadas → resultados "cancelled" y "not run", emparejados; sin
   herramientas ejecutadas → nada.

**4.3 Lectura con aprobación** (`tests/adapters/test_file_tools.py`)
1. Ruta fuera → petición con aviso y `scope=None`; aprobada, se lee.
2. Secreto → petición con aviso; dentro y normal → `None`.

**4.4 `write_file` y `edit_file`** (`tests/adapters/test_file_tools.py`)
1. `write_file`: petición de crear (preview) y de sobrescribir (diff); crea
   carpetas; `scope` dentro y `None` fuera o secreto; carpeta → error.
2. `edit_file`: diff; 0 o 2+ apariciones → `ToolError` en `approval()`;
   `replace_all`; CRLF se conserva; no UTF-8 → error; sin cambios → error.

**4.5 Comandos** (`tests/adapters/test_local_runner.py` y
`tests/adapters/test_shell_tool.py`)
1. Salida y código de salida; stderr mezclado.
2. Corte a 30 000 caracteres con un comando que escribe más; no se bloquea.
3. Tiempo límite: se mata y se conserva la salida parcial.
4. Cancelar mata el grupo entero (un nieto `sleep` no sobrevive).
5. Entorno: `OPENCODE_API_KEY`, `X_TOKEN`… no llegan; `PATH` sí.
6. `run_command`: petición con el comando y su `scope`; texto del resultado
   (con `FakeRunner`).

**4.6 Terminal** (`tests/adapters/test_approval.py` y `test_conversation.py`)
1. `TerminalApproval`: `y`, `a`, `n`, respuesta inválida y repetir, EOF →
   `deny`; sin `scope` no se ofrece `a`; aviso y corte del detalle.
2. `DenyAll` sin preguntar.
3. La conversación muestra la pregunta y el resultado; `TurnFinished
   ("denied")` → `  [denied: tell maha how to continue]`.

**4.7 `refusal`** (`tests/adapters/test_openai_chat*.py`): stream y
respuesta entera → texto.

**4.8 De punta a punta** (`tests/test_bootstrap.py`): con stdin que no es
terminal, una llamada a `write_file` se deniega sin preguntar y el fichero
no existe.

**4.9 Arquitectura:** `adapters/tools` no importa `adapters/commands`.

## 5. Evals

No aplica todavía (hito 8). Las tres descripciones nuevas se suman a las
candidatas de la batería.

## 6. Orden de piezas para el implementador

Cada punto es un commit, en verde.

**PR 1** (`feature/hito-5-aprobacion`): contrato y bucle, con fakes.
1. **Contrato.** `domain/approval.py`, `ports/approval.py`,
   `Tool.approval()` (las cuatro de lectura devuelven `None` de momento),
   `FakeApproval`. *Commit:* "Añadir el contrato de aprobación"
2. **Sesión.** `SessionApprovals`; tests 4.1. *Commit:* "Recordar las
   aprobaciones para toda la sesión"
3. **El bucle pregunta.** Eventos; el registro acepta `effect`; tests
   4.2.1–6. *Commit:* "Preguntar antes de ejecutar una herramienta"
4. **Lo ejecutado consta.** Tests 4.2.7. *Commit:* "Guardar en el turno lo
   que ya se ejecutó"
5. **Mapa.**

**PR 2** (`feature/hito-5-ficheros`): ficheros con aprobación.
6. **Leer fuera y secretos.** Tests 4.3. *Commit:* "Pedir aprobación para
   leer fuera del directorio o un secreto"
7. **`write_file`.** 4.4.1. 8. **`edit_file`.** 4.4.2. 9. **Mapa.**

**PR 3** (`feature/hito-5-comandos`): comandos.
10. **Puerto `CommandRunner` y `FakeRunner`.**
11. **`LocalCommandRunner`.** Tests 4.5.1–5. *Commit:* "Ejecutar comandos en
    un grupo de procesos propio y sin credenciales"
12. **`run_command`.** 4.5.6. 13. **Mapa.**

**PR 4** (`feature/hito-5-terminal`): terminal, `refusal` y cableado.
14. **`TerminalApproval` y `DenyAll`.** 4.6.1–2. *(Añadido 2026-10-21:
    con el saneado de caracteres de control de §1.10.)*
15. **La conversación con aprobaciones.** 4.6.3.
16. **`refusal`.** 4.7.
17. **Cableado** de las siete herramientas, el gate y el runner. 4.8.
18. **Mapa.**

**PR 5** (`feature/hito-5-cierre`): versión 0.5.0, verificación, nota de la
guía, spec IMPLEMENTADA y docs. **Tras el PR 5:** tag `v0.5.0`.

## 7. Verificación a mano

Con `opencode-go` y `glm-5.3-flash`, **en un directorio desechable** (AGENTS:
las herramientas con efecto se prueban así), creado para la prueba.

1. `maha --version` → `maha 0.5.0`.
2. "Crea notas.txt con dos líneas" → pregunta con la vista previa; `y` → el
   fichero existe.
3. "Cambia la segunda línea" → `edit_file` con el diff; `n` → no cambia, el
   turno termina con `[denied…]`; el modelo, en el turno siguiente, sabe que
   se denegó.
4. Dos ediciones seguidas con `a` en la primera: la segunda no pregunta.
5. "Ejecuta ls -la" → pregunta con el comando; `y` → salida; el mismo
   comando con `a` no vuelve a preguntar, otro sí.
6. "Ejecuta env" → la salida **no** contiene `OPENCODE_API_KEY`.
7. "Ejecuta sleep 30" y Ctrl+C → `[interrupted]`; `pgrep sleep` no lo
   encuentra; el turno siguiente sabe que se canceló.
8. Un comando que tarda más que su `timeout` → `[timed out…]`.
9. "Lee /etc/hostname" → pregunta con aviso, sin opción `a`; `y` → se lee.
10. "Lee .env" (uno inventado en el desechable) → pregunta con aviso; `n`.
11. `maha < notas.txt` pidiendo escribir un fichero → `(denied: input is not a
    terminal)` y el fichero no existe.

## 8. Lo que no viaja por git y lo que necesita la release

- Nada nuevo: ni variables ni configuración. `PUESTA_EN_MARCHA` sin cambios.
- `docs/MAPA.md`: los ficheros de §3.1.
- `docs/DESIGN.md` §5 y §10: `Tool.approval()`, ámbitos de sesión, entorno
  sin credenciales y "sin terminal se deniega". Corregido en el mismo commit
  que esta spec, con fecha.

## 9. Guía

`docs/guia/05-permisos.md`, "Permisos: el modelo propone, el código decide":
1. Leer frente a efecto; por qué el permiso es código y no prompt.
2. La pregunta: qué enseña (diff, comando), una vez / sesión / no, y los
   ámbitos.
3. Lo que nunca es "para la sesión": fuera del directorio y secretos.
4. Ejecutar comandos: grupo de procesos, tiempo límite, salida acotada y
   entorno sin credenciales; y lo que **no** protege (hasta el sandbox).
5. Lo ejecutado consta: el historial ante fallos y Ctrl+C.
6. "En la industria": la tabla de §2.

## 10. Riesgos

**POR VERIFICAR:**
- **`refusal` en OpenCode:** no se ha visto nunca; se implementa por la
  documentación de OpenAI.

**Riesgos y contingencias:**
- **Aprobar sin leer:** la pregunta es la única defensa de los comandos
  hasta el hito 14. Se enseña entera (cortada a 60 líneas) y el aviso de
  fuera/secreto va resaltado.
- **Una credencial con otro nombre** (`MI_CLAVE=…`) sí llega al comando. La
  lista es por patrón; mejora posible si aparece.
- **Un comando que lanza un demonio fuera de su grupo** (`setsid`) sobrevive
  al Ctrl+C. Es raro; el sandbox lo resolverá.
- **Comandos interactivos** (un editor, `git commit` sin `-m`): sin stdin
  terminan o se quedan hasta el `timeout`. La descripción pide comandos no
  interactivos.
- **Ediciones concurrentes** (tú editas el mismo fichero a la vez): el diff
  se calcula al preguntar y se aplica al aprobar; si el texto cambió entre
  medias, `edit_file` lo vuelve a comprobar y falla con `ToolError`.

## 11. Decisiones

Del humano (2026-10-21): **acepta las cinco recomendaciones del agente**:
1. Una negativa termina el turno.
2. "Toda la sesión" cubre todas las escrituras, todas las ediciones o cada
   comando exacto. La aprobación por prefijo queda como mejora futura
   (§1.3).
3. Sin terminal, se deniega todo; la política para el modo no interactivo se
   decide en el hito 8.
4. `refusal` entra en este hito, como texto.
5. Lo ejecutado consta en el historial aunque el turno falle o se cancele.

Propuestas del agente (2026-10-21), aprobadas por el humano con la spec:
**todas las de §1.2 a §1.11 y los cinco PRs de §6**.

**Dudas que se plantearon al mantenedor** (registro):
1. **Una negativa termina el turno** (propuesta, §1.4). Alternativa: el
   modelo recibe el error y sigue (puede volver a preguntarte con otra cosa).
2. **Ámbitos de "toda la sesión"** (propuesta, §1.3): todas las escrituras,
   todas las ediciones, y cada comando exacto. Alternativas: por fichero
   (más preguntas), o "todos los comandos" (más peligroso).
3. **Sin terminal, se deniega todo** (propuesta, §1.10). Alternativa: no
   ofrecer las herramientas con efecto cuando no hay terminal.
4. **`refusal` entra en este hito** (propuesta, §1.11), como texto. Es
   pequeño y cierra una pérdida silenciosa. Alternativa: dejarlo para el
   hito 9 (formatos de API).
5. **Lo ejecutado consta** (propuesta, §1.5). Alternativa: mantener el turno
   atómico del hito 4 (más simple, pero el modelo olvidaría ediciones
   hechas).

## 12. Aprendido al implementar (2026-10-21)

PR 1 (`feature/hito-5-aprobacion`, piezas 1 a 5). Lo que la spec no fijaba,
decidido al implementar; en las piezas 3 y 4, por el mantenedor.

1. **Pieza 1, contrato:**
   - `FakeTool` gana `approval()`, que devuelve `None`; sin él, `FakeTool`
     ya no cumplía el puerto `Tool` y mypy no cerraba;
   - `FakeApproval` sigue la forma de `FakeModelClient`: un guion de
     decisiones en orden, guarda las peticiones y falla si se agota;
   - §4 no asignaba tests a la pieza 1: se añaden unos mínimos propios
     (`tests/unit/test_fake_approval.py`).
2. **Pieza 2, sesión:** `SessionApprovals` tiene `covers(request)` y
   `record(request, decision)`. La regla de `scope=None` (nunca se guarda ni
   se cubre) vive dentro de `SessionApprovals`, no en el bucle.
3. **Pieza 3, el bucle pregunta** (decisiones del mantenedor):
   - `gate` es obligatorio: `Agent(..., gate=...)`;
   - en `bootstrap`, `_DenyEverything` provisional hasta la pieza 17 (opción
     A, frente a adelantar `DenyAll` o hacer el `gate` opcional). Hoy ninguna
     herramienta pregunta, así que no se llama;
   - `SessionApprovals` se crea dentro de `Agent`;
   - `FakeTool` gana el guion `requests` para `approval()` (petición, `None`
     o error), para los tests de §4.2;
   - `ToolFinished.decision` es `None` si el `scope` ya estaba aprobado para
     la sesión (no se preguntó);
   - tras una negativa, las llamadas "not run" emiten `ToolCallProposed` y
     `ToolFinished`, y no cuentan en `TurnFinished.tool_calls`; la denegada
     sí cuenta;
   - herramienta `effect` cuyo `approval()` devuelve `None` → `error:
     internal error in tool "<name>"`, con `internal_error="effect tool
     without an approval request"`;
   - una excepción que no es `ToolError` en `approval()` es un error
     interno, como en `run()`;
   - `test_an_effect_tool_is_refused` pasa a `test_an_effect_tool_is_accepted`;
   - el tiempo de decidir no cuenta en `ToolFinished.duration`; las "not run"
     llevan `duration=0.0`.
4. **Pieza 4, lo ejecutado consta** (decisiones del mantenedor; concreta
   §1.5):
   - D1: una llamada cuenta como ejecutada si se llegó a llamar a `run()`,
     también si Ctrl+C la cortó;
   - D2: Ctrl+C durante la única llamada guarda el turno con `error:
     cancelled by the user`. Cambian dos tests del hito 4 (`test_agent.py` y
     `test_conversation.py::test_ctrl_c_during_a_tool_goes_back_to_the_prompt`);
   - D3: Ctrl+C durante la pregunta, tras una llamada ya ejecutada → la
     llamada en aprobación queda `cancelled by the user` y las siguientes,
     `not run`. Sin nada ejecutado, no se guarda nada;
   - D4: solo `ModelError` y `CancelledError` guardan el turno, y además
     `GeneratorExit`: Ctrl+C que llega a la terminal mientras ella espera
     (p. ej., al parar el spinner) cierra el generador con `aclosing`, y el
     bucle recibe `GeneratorExit`. Aceptado por el mantenedor;
   - tras una negativa, si el turno se corta, las llamadas restantes llevan
     `not run: a previous call was denied`.
5. **Revisión del PR 1** (arreglos aprobados por el mantenedor):
   - **Solo una decisión válida ejecuta** (`d3953b0`). Antes, cualquier valor
     del `gate` distinto de `deny` ejecutaba la herramienta: fallaba en
     abierto. Ahora se ejecuta solo sin pregunta, con el `scope` ya cubierto,
     o con `once` o `session` (constante `DECISIONS` de
     `application/agent.py`). Otro valor → `internal error`, con
     `internal_error="invalid approval decision: <repr>"`; no se ejecuta, no
     se guarda nada en la sesión y el turno sigue;
   - **un fallo de `summary()` no oculta el resultado** (`56d7909`): el
     modelo recibe el contenido real, la terminal ve `(no summary)` y
     `internal_error="summary: <Tipo>: <msg>"`. Por qué: el efecto ya
     ocurrió; si llegara como error, el modelo lo repetiría;
   - **JSON demasiado anidado** (`56d7909`): el `RecursionError` de
     `json.loads` da `arguments are not a valid JSON object`, como un JSON
     inválido;
   - **más tests del bucle** (`bf643a6`): `once` y luego `deny` en la misma
     respuesta, Ctrl+C a mitad del stream del paso 2 tras una herramienta y
     `gate.requests == []` cuando no se pregunta. `HangingApproval` pasa a
     `tests/fakes/approval.py`;
   - **queda para el hito 6** (por D4): si, tras una ejecución, salta una
     excepción no prevista (p. ej., el `gate` falla con `OSError`), el turno
     no se guarda. Hoy eso tumba `maha` y el historial en memoria se pierde
     igual. Se revisa cuando las sesiones se guarden en disco.

PR 2 (`feature/hito-5-ficheros`, piezas 6 a 9). Lo que la spec no fijaba,
decidido por el mantenedor al implementar. Todo en
`adapters/tools/files.py`.

6. **Pieza 6, lectura con aprobación** (`7e39cfb`):
   - el permiso pasa de `run()` a `approval()`. Cambian 7 tests del hito 4:
     de "denegado" a "pregunta";
   - D1: `run()` vuelve a resolver la ruta; si no es la que se preguntó →
     `<ruta> changed after the question; ask again`. Una sola pareja
     `(escrita, resuelta)` por herramienta (`_Asked`), porque las llamadas
     van una a una; en el hito 15, una por llamada. Ese texto sale también si
     un enlace pasa a apuntar fuera o a un secreto sin que hubiera pregunta:
     aceptado así. *(Revisión, `06e285e`: ahora se guarda la llamada entera,
     no solo la ruta; ver §12.12.)*;
   - D2: en un recorrido (`glob`, `grep`) de fuera, el límite es la carpeta
     aprobada: los enlaces que salen de ella se saltan;
   - D3: fuera, todas las rutas salen absolutas, también las de dentro al
     buscar en `..`;
   - D4: fuera del directorio, `is_secret` mira la ruta absoluta resuelta
     (dentro, la relativa, como en el hito 4): un `~/.ssh` aprobado sigue
     siendo secreto;
   - D5: con los dos avisos, van juntos con `"; "`, el de fuera primero;
   - D6: `list_dir` de una carpeta secreta avisa con `secret directory: its
     file names go to the model provider`. §1.6 decía "como un secreto"
     (contenido), pero lo que sale son nombres; texto exacto elegido por el
     mantenedor;
   - D7: `grep` sobre un fichero secreto pregunta; sobre una carpeta secreta
     no pregunta, y el recorrido salta sus secretos;
   - D8: los fallos baratos (no existe, carpeta, binario, patrón o regex
     inválidos) van antes de preguntar. *(Revisión, `39162ca`: "binario" ya
     no; sale en `run()`, tras aprobar. Ver §12.12.)*;
   - textos: title `read <ruta>`, `list <ruta>`, `glob <patrón> in <ruta>`,
     `grep "<patrón>" in <ruta>` (más ` (glob: …)` si lo hay); detail, la ruta
     resuelta, con ` (asked: <escrita>)` si difiere.
7. **Pieza 7, `write_file`** (`fad129c`):
   - W1: diff con 3 líneas de contexto y como mucho 60; si hay más,
     `… [N more diff lines]`;
   - W2: fichero existente binario o no UTF-8 → error antes de preguntar.
     *(Revisión, `39162ca`: con aviso, sale en `run()`, tras aprobar.)*;
   - W3: líneas contadas como las numera `read_file` (`\n`, `\r` o `\r\n`);
   - W4: diff sin cabeceras `---`/`+++`, como el ejemplo de §0: la ruta va en
     el title;
   - W5: mismo contenido → `nothing to change`; solo cambian los saltos de
     línea → el detail dice `(only line endings change)`. *(Revisión,
     `39162ca`: con aviso, `nothing to change` sale en `run()`, tras
     aprobar.)*;
   - W6: `run()` vuelve a leer el fichero; si no es el texto que mostró la
     pregunta (o ahora existe y antes no) → `changed after the question`;
   - W7: `(asked: <escrita>)` como primera línea del detail, si difiere;
   - W8/A3: carpeta, algo que no es un fichero normal, un padre que no es
     carpeta o `content` no UTF-8 → error antes de preguntar;
   - A2: un `OSError` al escribir → `cannot write <ruta>: <motivo>`;
   - A4: las carpetas creadas antes de un fallo se quedan;
   - textos: vista previa de 20 líneas, con `… [N more lines]` y
     `(empty file)`; resultado `wrote <ruta> (N lines)`; summary `N lines`;
   - **escritura atómica** (fuera de la spec, decisión del mantenedor):
     temporal oculto `.<nombre>.<8 hex>.tmp` en la misma carpeta, creado con
     `os.open(…, O_EXCL|O_NOFOLLOW|O_CLOEXEC, 0o666)` para que la umask se
     aplique como con `open("w")` (A1; `mkstemp` crea con 0600); `fsync`;
     `os.replace`. Si el fichero existía, se copia su modo. Ante cualquier
     fallo o cancelación antes del `os.replace`, se borra el temporal y el
     original queda intacto.
8. **`fsync` de la carpeta** (`c22eb08`, decisión del mantenedor): completa
   el patrón atómico; el `fsync` del fichero no cubre su entrada en la
   carpeta. Si falla, se ignora: el fichero ya está reemplazado, y decir
   `cannot write` haría que el modelo lo repitiera.
9. **Pieza 8, `edit_file`** (`b8e98b6`):
   - errores con pista: `old_string not found in <ruta>; read the file and
     copy the text exactly` y `old_string appears N times in <ruta>; add
     context to make it unique or use replace_all`;
   - plural: `1 replacement`, `N replacements`;
   - `old_string` vacío → error; `replace_all` sin apariciones → error (el de
     "not found");
   - fichero que no existe → `file not found: <ruta>`;
   - binario o no UTF-8 → los errores de `write_file`. *(Revisión,
     `39162ca`: con aviso, estos, "not found" y "appears N times" salen en
     `run()`, tras aprobar.)*;
   - `new_string` no UTF-8 → error antes de preguntar;
   - apariciones contadas sin solapar (`str.count`);
   - orden: parámetros, fichero, pregunta;
   - cada campo de `EditFileParams` lleva descripción;
   - 9b, adaptación a CRLF: ver §1.8;
   - C: si tras la adaptación el texto queda igual (`"a\n"` por `"a\r\n"`)
     → `nothing to change`. *(Revisión, `39162ca`: con aviso, sale en
     `run()`, tras aprobar.)*
10. **Límites conocidos** (aceptados):
    - un enlace duro se separa: `os.replace` deja un fichero nuevo;
    - no se conservan el propietario, el grupo, los atributos extendidos ni
      las ACL: solo el modo;
    - las carpetas creadas antes de un fallo se quedan (A4);
    - el `fsync` llega solo a la carpeta del fichero, no a las carpetas padre
      recién creadas;
    - solo POSIX (`O_DIRECTORY`, `O_NOFOLLOW`);
    - un nombre de más de unos 240 caracteres falla al crear el temporal (el
      temporal suma 14);
    - queda un hueco de microsegundos entre la última comprobación y
      `os.replace` / `open`;
    - las apariciones solapadas cuentan sin solapar;
    - en un fichero mezclado, un `old_string` que cruza las zonas LF y CRLF
      no coincide;
    - los `\r` solos no se adaptan;
    - ~~`_Shown` comprueba la ruta y el texto del fichero, no los demás
      parámetros.~~ **Resuelto** en la revisión (`06e285e`, §12.12);
    - el fallo del `fsync` de la carpeta no deja rastro (el hito 7 lo podrá
      registrar);
    - *(segunda revisión)* `difflib` sobre un fichero de hasta 2 MiB con
      muchas líneas casi iguales puede tardar: es trabajo síncrono;
    - *(segunda revisión)* `GIT_DIR` solo cubre `.git`: `.github/workflows`,
      `.husky`, `.pre-commit-config.yaml` o la configuración de `maha`
      siguen admitiendo "siempre en esta sesión";
    - *(segunda revisión)* con aviso, un `old_string` incorrecto o un
      binario pregunta primero y falla después de aprobar: coste aceptado
      del arreglo de la fuga (`39162ca`, §12.12).
11. **Pendiente fuera del hito:** una FIFO bloquea la lectura (viene del
    hito 4). Afecta a `read_file`, a `grep` al recorrer y a `is_binary`, que
    las dos usan para mirar los primeros bytes. Irá en un PR `fix/` justo
    después del PR 2, con su test primero. `write_file` y `edit_file` no se
    ven afectadas: una FIFO no es un fichero normal y falla antes de leer.
    **Resuelto** en `85c9e26` (PR `fix/fifo-bloquea-lectura`, 2026-10-23):
    `read_file` y `grep` sobre un solo fichero dan `not a regular file`
    antes de abrir (y antes de preguntar, como error de metadatos); `grep`
    al recorrer salta lo que no es un fichero normal. El test usa una FIFO
    real con un escritor en un hilo, para que el fallo se vea sin colgar la
    batería. Quedaba un hueco (TOCTOU, *time of check to time of use*): si
    alguien cambiaba el fichero por una FIFO entre la comprobación y la
    apertura, se bloqueaba igual. El agente lo anotó como "límite aceptado"
    sin preguntar; el mantenedor pidió arreglarlo y fijó la regla en
    `AGENTS.md` (ningún fallo conocido se deja sin arreglar por decisión del
    agente). **Resuelto** en `7f329ee` (PR `fix/fifo-sin-carrera`,
    2026-10-23): se abre una sola vez con `O_NONBLOCK`, se mira el tipo con
    `fstat` sobre el fichero abierto y se lee de ese mismo descriptor. El
    test simula la carrera: la comprobación previa ve un fichero normal y en
    disco hay una FIFO.
12. **Revisión del PR 2** (2026-10-21). Arreglos decididos por el
    mantenedor, un commit cada uno; el código los cita como "review of PR 2,
    fix N":
    - **`39162ca`, con aviso, la pregunta va antes que el contenido** (fix
      1). Con aviso (fuera, secreto o `.git`), antes de preguntar solo salen
      errores de metadatos (no existe, carpeta, no es un fichero normal,
      padre que no es carpeta, tamaño, `cannot read`) y de parámetros que no
      miran el disco (`old_string` vacío, `old_string` igual a `new_string`,
      `content` o `new_string` no UTF-8). Los que dependen del contenido
      (`not found`, `appears N times`, `nothing to change`, binario, no
      UTF-8) salen en `run()`, tras aprobar. `read_file` con aviso tampoco
      dice "binary" antes. Por qué: sin esto, un modelo podía sondear un
      secreto carácter a carácter sin pregunta. Si el contenido no es
      válido, el detail es de reserva: en `edit_file`, `old_string:` y
      `new_string:` con sus líneas (y `replace_all: true`), cortado a 60
      líneas; en `write_file`, la vista previa del contenido nuevo. El diff
      de un secreto válido sí se enseña: va a la terminal, no al modelo.
      Ajusta D8, W2, W5 y C (§12.6, §12.7 y §12.9).
    - **`40e7e1a`, tamaño máximo para cambiar** (fix 2):
      `CHANGE_MAX_FILE_BYTES` = 2 MiB, comprobado con `stat` antes de leer.
      Más grande → `file too large to edit|overwrite (N.N MiB, max 2 MiB);
      use run_command`. Por qué: leerlo y calcular su diff bloquearía el
      bucle. Es metadato: sale antes de preguntar, también con aviso.
    - **`b66b354`, `cannot read`** (fix 3): un `OSError` al leer → `cannot
      read <ruta>: <motivo>`, con `_reading`, en vez de un error interno.
      Lo usan `read_file`, `list_dir`, `grep` sobre un fichero, `write_file`
      y `edit_file`; `glob` no lo usa.
    - **`8458304`, aviso de saltos de línea** (fix 4): si cambia el estilo,
      `(line endings change: X → Y)` como primera línea del diff (tras
      `(asked: …)`). Estilos `CRLF`, `LF` o `mixed`; un `\r` suelto cuenta
      como `mixed`. Sin aviso si un lado no tiene saltos, si solo cambian los
      saltos (ya sale `(only line endings change)`) o con el detail de
      reserva. Por qué: el diff compara líneas sin su salto y no lo
      enseñaría.
    - **`06e285e`, la llamada entera** (fix 5): `_Shown` y `_Asked` guardan
      los parámetros completos, y `run()` los compara; si difieren, el error
      de D1. Cierra el hueco antes del hito 15 (llamadas en paralelo).
    - **`ad2341d`, `.git` siempre pregunta** (fix 6): escribir o editar en
      una ruta resuelta con un componente `.git` → `scope=None` y el aviso
      `git directory: hooks and config here can run code`. Orden de los
      avisos: fuera, secreto, git. Por qué: hooks y config de git ejecutan
      código, y "siempre en esta sesión" lo permitiría sin pregunta. Leer en
      `.git` no cambia. Límite: si el directorio de trabajo está dentro de
      una carpeta `.git`, toda escritura avisa.
    - **`9015a45`, refactor**: `_as_shown` (el inicio común de `run()` en
      `write_file` y `edit_file`) y `_write` (escritura atómica con el error
      de A2). Sin cambio de comportamiento.
    - **`105904d`, `grep` y los ficheros ilegibles** (fix 8): al recorrer,
      los salta, como los secretos, binarios y grandes; sobre un fichero
      suelto da `cannot read`.
    - **Requisito para la pieza 14:** `TerminalApproval` sanea los
      caracteres de control de `title`, `detail` y `warning` antes de
      pintarlos (§1.10).

    Segunda revisión del PR 2: sin bloqueantes. Un arreglo más:
    - **`30ffc45`, "Dar un error limpio si falla el stat del fichero que se
      cambia"**: `path.stat()` en `_current_bytes` también da `cannot read`
      en vez de error interno.

    En verde: 487 tests.
