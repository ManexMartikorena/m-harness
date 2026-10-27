Estado: PROPUESTA (2026-10-27) → APROBADA (2026-10-27, por el humano: "la
opción más profesional y que más valor aporte al producto final" para todas
las dudas; con ese criterio cambian las dudas 3 y 4, y entran `--jobs` y los
errores de infraestructura, §11)

# Spec — Hito 8: Evals y modo no interactivo

Referencias: `docs/DESIGN.md` §4 (límites del bucle), §5 (`AgentEvent`,
`ModelRequest.max_tokens`), §6 (`ApprovalGate` con "política automática
(evals)"), §8, §9 (evals), §10 (permisos) y §14 (hito 8, P1 y P2);
`docs/COMPARATIVA.md` §2, §4, §10, §11 y §15; `docs/ANALISIS.md` §6 (RF 18);
pendientes de las specs 3 (§1.9, reintentos), 4 (§0 y §11.3, límites de
tokens y tiempo; §5, descripciones a la batería), 5 (§1.8, "leer antes de
editar"; §11.3, política sin terminal; §5), 6 (§11.5, `--continue`; §5, la
marca `[interrupted by the user]`) y 7 (§11.4, reintentos; §11.5, `maha
trace`; §12.26, `interrupted` por tiempo límite); `AGENTS.md`.

## 0. Alcance

**El problema.** Hoy cada cambio en el bucle, las herramientas o sus
descripciones se juzga a ojo: no hay forma de saber si `maha` resuelve más o
menos tareas que antes, ni cuánto le cuestan. Además, `maha` solo sirve con
una persona delante: no se puede usar en un script, ni retomar al arrancar,
ni ponerle un tope de gasto, y un 429 del proveedor corta el turno.

**Lo que hace este hito.** Una batería de 10 tareas que `maha eval` ejecuta
con llamadas reales, comprueba solo y compara con una línea base guardada en
el repo. Y el modo no interactivo completo: `maha -p "…"` con salida de
texto o JSON, retomar al arrancar, permisos explícitos sin persona, topes
por turno, reintentos con modelo de respaldo y los comandos `maha models`,
`sessions`, `trace`, `stats`, `export` e `import`.

**Términos.**
- **Eval:** una tarea con una comprobación automática (¿pasan los tests?,
  ¿el fichero dice X?), ejecutada por el agente de verdad.
- **Línea base:** el resultado de la batería en una fecha y con un modelo,
  guardado para comparar los cambios siguientes.
- **Conjunto de validación:** tareas que no se miran al ajustar prompts,
  para detectar si se ajusta "al examen" (sobreajuste).
- **Modo no interactivo (*headless*):** `maha` sin persona delante: recibe
  una instrucción, trabaja y sale con un código de salida.

Dentro de alcance:
- **Núcleo sin persona** (§1.1–§1.4): límites del turno (pasos, coste,
  tokens y tiempo), política de aprobación automática y una ejecución de un
  turno reutilizable por `-p` y por las evals.
- **Evals** (§1.5–§1.9): formato de tarea, 10 tareas con datos inventados,
  `maha eval`, métricas, línea base y comparación.
- **Modo no interactivo** (§1.10–§1.13): `-p`, stdin, `--model`, `-c`, `-r`,
  `--allow`, `--output-format text|json|stream-json`, códigos de salida.
- **Reintentos** ante 429 y 5xx con espera creciente y **modelo de
  respaldo** (§1.14), también en la conversación interactiva.
- **Comandos de línea** (§1.15): `maha models`, `maha sessions`, `maha
  trace`, `maha stats`, `maha export`, `maha import`; y en la conversación,
  `/new` y `/export`.
- Configuración: `fallback_model` y `[limits]` en `config.toml` (§3.2).

**Fuera de alcance** (y por qué):
- `run_command` en las evals: hasta el sandbox (hito 15), duda 2.
- Modos de permiso (`plan`, aceptar ediciones), reglas por patrón y `--allow`
  por prefijo de comando: hito 15 (P9).
- La marca `[interrupted by the user]` en la batería: necesita tareas con
  historial previo; hito 11 (contexto), duda 8.
- Bifurcar una sesión: hito 12 (puntos de control), duda 8.
- `--input-format stream-json`, `--json-schema`, `--append-system-prompt`:
  no están en el plan; el system prompt es el hito 10.
- `max_tokens` por llamada en `ModelRequest`: hito 11 (contexto). El tope de
  tokens de este hito es por turno (§1.1).
- Un selector de sesiones para `-r` sin id: hito 21 (TUI).

## 1. Decisiones de fondo

### 1.0 Hechos comprobados (2026-10-27, documentación oficial)

- **Claude Code** (https://code.claude.com/docs/en/cli-reference.md y
  `/headless.md`): `-p`/`--print`; `-c` ("most recent conversation in the
  current directory", y se salta las sesiones creadas con `-p`); `-r ID`;
  `--model`; `--output-format text|json|stream-json` (`json` trae `result`,
  `session_id`, `total_cost_usd`; la última línea de `stream-json` es un
  `result`); `--max-turns` y `--max-budget-usd` ("print mode only"); el gasto
  "can pass" el tope; `--fallback-model` "when the primary model is
  overloaded or not available"; `--allowedTools`; en `-p`, "a call that
  needs approval is denied unless something approves it"; stdin se une a la
  instrucción (`cat file | claude -p "query"`); "exits with code 0 on
  success and a non-zero code when the run fails"; SIGTERM sale con 143; un
  evento `system/api_retry` con `attempt`, `max_retries`, `retry_delay_ms`.
- **OpenCode** (https://opencode.ai/docs/cli/): `opencode run` con `-c`,
  `-s`, `-m provider/model`, `--format default|json` ("raw JSON events") y
  `--auto` ("Auto-approve permissions that are not explicitly denied");
  `opencode models`; `opencode stats --days --models --project`; `opencode
  export` (JSON) e `import`; `opencode session list`.
- **SDK oficiales** (README de `openai-python`;
  https://platform.claude.com/docs/en/api/sdks/python): reintentan "2 times
  by default, with a short exponential backoff" los errores de conexión,
  408, 409, 429 y ">=500".

### 1.1 Límites del turno, en código

Hoy solo hay `MAX_STEPS = 25`. Pasan a ser cuatro, en `domain/limits.py`:

```python
class TurnLimits(BaseModel, frozen=True):
    max_steps: int = 25  # llamadas al modelo por turno
    max_cost: Usd | None = None  # dólares por turno
    max_tokens: int | None = None  # entrada + salida, sumados en el turno
    timeout: float | None = None  # segundos de reloj por turno
```

- **Pasos, coste y tokens** se comprueban **antes de cada llamada al
  modelo**, con lo gastado hasta ahí. Así las herramientas del paso anterior
  ya tienen su resultado en el historial y el turno queda coherente. El
  gasto puede pasar el tope en una llamada como mucho, igual que en Claude
  Code ("can pass").
- `TurnFinished.reason` gana `max_cost` y `max_tokens` (ya existe
  `max_steps`).
- **Coste desconocido con `max_cost`:** si una llamada no tiene precio ni
  coste del proveedor, el turno se para con `max_cost` y el aviso "cost
  unknown". Es un tope de dinero: falla cerrado (duda 7).
- **Tiempo:** el turno entero va dentro de `asyncio.timeout`. Al vencer se
  cancela como Ctrl+C, por el camino que ya existe y está probado: lo
  ejecutado consta y la traza lo apunta `interrupted` (spec 7, §12.26), con
  la causa `timeout`. *(Corregido al implementarlo, §12.1: el plazo va en
  cada espera del bucle y el turno acaba con `TurnFinished(reason="timeout")`.)*

### 1.2 Política de aprobación sin persona: `AllowList`

Hoy, sin terminal, `DenyAll` deniega todo. Nace `AllowList(tools)` en
`application/approvals.py`, que implementa `ApprovalGate`:

- aprueba (`once`) una petición **con ámbito** (`scope`) de una herramienta
  de la lista;
- deniega **siempre** una petición **sin ámbito**: fuera del directorio de
  trabajo, ficheros secretos y ficheros que ejecutan código (`.git`,
  `.github`…). Son las que con persona preguntan "cada vez" (DESIGN §10);
  sin persona no hay a quién preguntar;
- deniega lo demás.

```
maha -p "arregla el test" --allow edit_file --allow write_file
  edit_file app.py        → aprobado (dentro, con ámbito)
  edit_file .github/ci.yml → denegado (ejecuta código: sin ámbito)
  run_command "pytest"    → denegado (no está en --allow)
```

La lista solo llega por la línea de comandos (`--allow`) o por la tarea de
una eval, **nunca por `config.toml`**: un `.maha/config.toml` de un repo
ajeno no puede darse permisos (duda 1).

### 1.3 Una ejecución de un turno: `application/headless.py`

`run_once(conversation, text, limits) -> RunResult` *(al implementarlo,
§12.3: sin `limits`, que ya lleva el `Agent`)* ejecuta un turno, junta
los eventos y devuelve un resumen. Lo usan `maha -p` y `maha eval`, así que
las evals miden exactamente lo que hace `-p`:

```python
class RunResult(BaseModel, frozen=True):
    session: str
    text: str  # la respuesta final: el texto del último paso
    # end_turn | max_steps | max_cost | max_tokens | denied | timeout | error
    reason: str
    steps: int
    tool_calls: int
    tool_errors: int  # resultados con is_error
    denials: list[str]  # títulos de las peticiones denegadas
    usage: Usage
    cost: Usd | None
    duration: float
    model: str  # el último usado (puede ser el de respaldo)
    error: str | None
```

### 1.4 Códigos de salida

| Código | Cuándo |
|---|---|
| 0 | El turno acabó bien (`end_turn`) |
| 1 | Error: del modelo, de configuración, de lectura |
| 2 | Uso incorrecto de la línea de comandos (argparse, como hoy) |
| 3 | Un límite paró el turno (`max_*`, `timeout`) |
| 4 | Se denegó una llamada (el turno acaba con una negativa, spec 5) |
| 130 / 143 | Ctrl+C / SIGTERM, como hoy |

Claude Code solo documenta "0 o distinto de 0"; distinguir 3 y 4 deja a un
script saber si reintentar con más tope o con más permisos.

### 1.5 Formato de una tarea

Cada tarea es una carpeta en `evals/tasks/` con un `task.toml`; los repos de
prueba, en `evals/fixtures/` (DESIGN §9), compartibles entre tareas.

```toml
# evals/tasks/06-arreglar-bug/task.toml
instruction = "El test de descuentos falla. Arréglalo sin tocar el test."
fixture = "tienda"            # evals/fixtures/tienda/
split = "train"               # o "validation"
allow = ["edit_file", "write_file"]

[limits]                      # opcional; por defecto 25 pasos y 300 s
timeout = 300

[check]                       # una o varias comprobaciones; todas tienen que pasar
command = "python3 -m unittest -q"            # termina con 0
# file = "README.md"; contains = "recibir"; absent = "recivir"
# answer_contains = ["src/iva.py"]           # en la respuesta final
```

La comprobación la ejecuta el arnés de evals, no el modelo: con
`CommandRunner`, en la copia del repo, después del turno. Solo
`python3` de la biblioteca estándar en los fixtures: sin dependencias que
instalar.

### 1.6 Las 10 tareas *(20 desde el PR 2, §12.8)*

Datos inventados; ocho en español y dos en inglés (el producto es
multilingüe). Cubren las siete herramientas salvo `run_command` (duda 2) y
los pendientes de specs anteriores.

| # | Tarea | Herramientas | Comprobación | Conjunto |
|---|---|---|---|---|
| 1 | ¿Qué versión declara `pyproject.toml`? | `read_file` | respuesta contiene `1.4.2` | train |
| 2 | ¿En qué fichero se define `calcular_iva`? | `grep`/`glob` | respuesta contiene la ruta | train |
| 3 | ¿Cuántos ficheros `.py` hay en `src/`? | `glob`/`list_dir` | respuesta contiene el número | train |
| 4 | Crea un `.gitignore` con `__pycache__/` y `.venv/` | `write_file` | fichero con las dos líneas | **validation** |
| 5 | Cambia el puerto por defecto de 8000 a 8080 | `edit_file` | `python3 -c` comprueba `PORT == 8080` | train |
| 6 | El test de descuentos falla: arréglalo sin tocar el test | `read_file`, `edit_file` | `unittest` en verde | train |
| 7 | Renombra `total` a `importe_total` en todo el proyecto | `grep`, `edit_file` | `unittest` en verde y `python3 -c` comprueba que `total` ya no existe en ningún módulo | **validation** |
| 8 | Implementa `slugify` para que pasen sus tests | `write_file`/`edit_file` | `unittest` en verde | train |
| 9 | *Fix the typo "recieve" in README.md* | `edit_file` (exactitud de `old_string`) | fichero sin `recieve` | train |
| 10 | *Add `is_even(n)` to utils.py* | `edit_file` | `python3 -c` la prueba | train |

*(Añadidas al implementar, por decisión del mantenedor, §12.8: diez tareas
más exigentes.)*

| # | Tarea | Qué la hace difícil | Conjunto |
|---|---|---|---|
| 11 | Puerto desde `TIENDA_PORT`, 8000 si falta o no es un número | Casos límite | train |
| 12 | IVA del 10 % para `alimentacion`, con líneas de dos o tres elementos | Cambiar dos funciones sin romper nada | train |
| 13 | ¿Qué funciones de `src/tienda` no aparecen en `tests/`? | Cruzar ficheros; decir de más falla (`answer_absent`) | train |
| 14 | Descuento por volumen en `total()` | Una regla que se nota también en el IVA | **validation** |
| 15 | Los tests de la agenda fallan (años bisiestos) | La causa real: 1900 no es bisiesto | train |
| 16 | `notas lista --ordenar` | Programa de línea de comandos, salida comprobada | train |
| 17 | Notas en JSON, migrando el `notas.txt` antiguo | Cambio de formato con migración | train |
| 18 | *`parse_duration("1h30m")`*, rechazando lo que no vale | Analizar texto | **validation** |
| 19 | *The inventory tests fail* | Un fallo con dos causas | train |
| 20 | *`total_value()` and its test* | Escribir código y su test | train |

- Las tareas 5 a 10 miden de paso lo que la spec 5 (§1.8) dejó para aquí:
  si hace falta "leer antes de editar". La métrica `tool_errors` cuenta las
  ediciones que fallan por un `old_string` que no está.
- Las descripciones de las herramientas (spec 4, §5, y spec 5, §5) quedan
  medidas desde la primera línea base.

### 1.7 Métricas

Por tarea y en total, a partir de `RunResult` (las trazas de cada tarea se
guardan para mirarlas, §1.9):

| Métrica | Qué es |
|---|---|
| Éxito | Tareas cuya comprobación pasa (con repeticiones, la proporción) |
| Errores de infraestructura | Ejecuciones que no llegaron a acabar por el proveedor (429, 5xx, red, credenciales): no cuentan como fallo ni entran en el éxito, se informan aparte y se pueden repetir con `--retry-errors` |
| Pasos | Llamadas al modelo |
| Errores de herramienta | Resultados con `is_error` |
| Tokens y coste | Suma del turno |
| Tiempo | Duración del turno, sin la comprobación |

### 1.8 Repeticiones, línea base y regresión

Un modelo no responde siempre igual: una sola pasada es ruido.

- `maha eval` corre cada tarea **1 vez** por defecto (rápido, para iterar);
  `--repeat N` la corre N veces. La línea base y la comparación antes de
  cada merge, con **5** (duda 3).
- **Dos modelos** de familias distintas (duda 4): `opencode-go/glm-5.3-flash`
  (el de uso diario) y `opencode-go/kimi-k2.7-code` (especializado en
  código). `--model` elige uno; `--models a,b` los dos. Cada uno tiene su
  línea base.
- `maha eval --save` escribe `evals/baselines/AAAA-MM-DD-<proveedor>-<modelo>.json`:
  solo métricas, versión de `maha` y commit; nunca trazas ni respuestas.
- Cada ejecución se compara con la última línea base **del mismo modelo** y
  marca ⚠ una **regresión**:
  - una tarea que pasaba en todas las repeticiones y ahora falla en
    alguna, o baja la tasa de éxito total;
  - o el coste o los pasos medios suben más de un 20 %.

  Una ⚠ no bloquea nada por sí sola: AGENTS.md ya dice que una regresión no
  se mergea salvo decisión del mantenedor, anotada en la spec.
- `--split train|validation|all` (por defecto `all`): al ajustar prompts se
  itera con `train`; la validación se mira solo al final.

### 1.9 Dónde corre una eval

- Cada tarea, en una **copia temporal** de su fixture (`tempfile`), que se
  borra al acabar salvo con `--keep`.
- Sesiones y trazas de una ejecución, en `~/.local/state/maha/evals/<id>/`,
  no entre las del usuario: no ensucian `/sessions` ni `maha stats`.
- Las tareas se buscan en `./evals/tasks` (o `--tasks DIR`): es una
  herramienta del repo de `maha`, no del usuario final; el paquete no las
  lleva.
- **En paralelo:** `--jobs N`, 4 por defecto. Cada tarea tiene su copia y
  su sesión (los ids ya se reservan en exclusiva, spec 7, §12.18). Un 429
  con varias a la vez no falsea el resultado: es un error de
  infraestructura (§1.7).
- Coste estimado de una pasada completa (10 tareas × 5 × 2 modelos, ~5
  llamadas de ~3 000 tokens): unos 0,15 $ con `glm-5.3-flash` (0,15 $/M de
  entrada) y en torno a 1 $ con `kimi-k2.7-code` (0,95 $/M). Se mide en la
  primera y se anota aquí.

### 1.10 `maha -p`: entrada

```
maha -p "resume este proyecto"
git diff | maha -p "revisa este diff"
maha -p < instrucciones.txt
```

- Con texto en `-p` y stdin que no es una terminal, la instrucción es el
  texto y, debajo, el contenido de stdin entre delimitadores (es entrada no
  confiable, AGENTS.md). Sin texto, stdin es la instrucción. Tope de 10 MB,
  con error claro (el mismo que Claude Code).
- `maha < fichero` sin `-p` sigue como hoy (cada línea, un turno), por
  compatibilidad.
- `-p` guarda la sesión como la conversación: `-c` o `-r` la siguen.

### 1.11 `maha -p`: salida

- **`text`** (por defecto): en stdout, **solo la respuesta final** (el
  texto del último paso), para `x=$(maha -p …)`. Las líneas de llamadas,
  los avisos y la línea de tokens van a **stderr**, como en la conversación
  pero sin spinner.
- **`json`**: un objeto al final, el `RunResult` con nombres estables:

  ```json
  {"type": "result", "session_id": "20261027-…", "result": "…",
   "reason": "end_turn", "is_error": false, "steps": 3, "tool_calls": 2,
   "tool_errors": 0, "denials": [], "usage": {"input_tokens": 5236, "…": 0},
   "cost_usd": "0.0004", "duration_s": 4.1, "model": "glm-5.3-flash"}
  ```
- **`stream-json`**: un `AgentEvent` por línea, como su JSON de Pydantic, y
  la última, el `result`. Es el mismo contrato que las trazas.

Lo que sale por stdout no se enmascara, como no se enmascara la terminal:
en `-p` los ficheros secretos se deniegan siempre (§1.2) y los comandos no
reciben las credenciales (DESIGN §10).

### 1.12 Retomar al arrancar: `-c` y `-r`

- `maha -c`: la última sesión **de este directorio**, también las de `-p`
  (Claude Code se las salta; aquí `-p` + `-c` es el uso natural en scripts).
- `maha -r ID`: esa sesión, de cualquier directorio. Sin id, error con la
  sugerencia de `maha sessions` (el selector, en el hito 21).
- Valen con y sin `-p`. Usan `Sessions.resume`, que ya existe (`/resume`).

### 1.13 Opciones

Los nombres de Claude Code donde significan lo mismo; propios donde `maha`
cuenta distinto (duda 6):

| Opción | Qué |
|---|---|
| `-p`, `--print [TEXTO]` | Una instrucción y salir |
| `-c`, `--continue` | Seguir la última sesión de aquí |
| `-r`, `--resume ID` | Seguir una sesión |
| `-m`, `--model ID` | Modelo de esta ejecución |
| `--fallback-model ID` | Modelo de respaldo (§1.14) |
| `--output-format text\|json\|stream-json` | Solo con `-p` |
| `--allow TOOL` | Repetible; solo con `-p` (§1.2) |
| `--max-steps N`, `--max-cost USD`, `--max-tokens N`, `--timeout S` | Límites del turno (§1.1) |

Claude Code llama `--max-turns` a lo que aquí son pasos: en `maha` un turno
es lo que escribe el usuario (spec 4), así que `--max-steps`.

### 1.14 Reintentos y modelo de respaldo

- **Qué se reintenta:** `ModelRateLimitError` (429) y
  `ModelUnavailableError` (5xx, red, tiempo de espera), **solo antes del
  primer evento** de la respuesta. Una respuesta empezada no se repite: su
  texto ya se mostró (spec 3, §1.9).
- **Cuánto:** 3 reintentos, con espera de 1, 2 y 4 s más un azar de hasta
  el 25 % (*jitter*: que varios clientes no reintenten a la vez). Si el
  proveedor manda `Retry-After`, se respeta hasta 60 s. La espera se corta
  con Ctrl+C y cuenta para `timeout`.
- **Dónde:** en el bucle (`application/agent.py`), que puede emitir un
  evento nuevo `ModelRetry(attempt, max_retries, delay, error)`; la terminal
  lo enseña y la traza lo guarda. La política (cuántos, cuánto) es pura, en
  `domain/retry.py`, con el azar inyectado para los tests.
- **Respaldo:** si se agotan los reintentos y hay `fallback_model`, la
  llamada se repite con él y el resto del turno sigue con él; el turno
  siguiente vuelve al principal. Evento `ModelFallback(model, fallback,
  error)`. El coste usa el precio del modelo de respaldo (ya viaja en
  `ModelCallFinished.model`).
- 401/403 y otros 4xx no se reintentan: repetirlos no los arregla.
- Los adaptadores pasan `Retry-After` en `ModelRateLimitError.retry_after`.

### 1.15 Comandos de línea

| Comando | Qué hace |
|---|---|
| `maha models [--all]` | Modelos del catálogo del proveedor actual (todos con `--all`): id, ventana y precios |
| `maha sessions` | Las sesiones recientes, como `/sessions` |
| `maha sessions delete ID` | Borra una sesión y su traza, como `/delete` |
| `maha trace [ID]` | Lo que hizo y costó, como `/trace` (spec 7, §11.5) |
| `maha stats [--days N]` | Coste y tokens acumulados por día y por modelo, de las trazas |
| `maha export ID [--format md\|json]` | La conversación en Markdown (por defecto) o el JSON de la sesión, a stdout |
| `maha import FICHERO` | Una sesión exportada en JSON, como sesión nueva con otro id |
| `maha eval [opciones]` | La batería (§1.5–§1.9) |

En la conversación, dos comandos pequeños de la comparativa (§2):
`/new` (sesión nueva sin salir) y `/export [FICHERO]` (Markdown).

`maha import` valida el JSON con el modelo `Session` y lo guarda con un id
nuevo; nunca sobrescribe. Una sesión importada es entrada no confiable como
cualquier historial: no trae permisos (spec 6, §1.9).

## 2. En la industria

| Pieza | Aquí | Normalmente | Cuándo se elegiría |
|---|---|---|---|
| Batería de evals | Tareas TOML propias y comprobación por comando | Inspect AI (UK AISI), promptfoo, OpenAI Evals; benchmarks como SWE-bench o Terminal-Bench | Muchas tareas, varios modelos, paneles; o comparar con otros agentes |
| Seguimiento de experimentos | JSON de línea base en el repo | LangSmith, Braintrust, Langfuse (datasets y experiments) | Equipos, históricos largos, revisión humana de respuestas |
| Juez | Comprobación determinista | Modelo como juez (*LLM-as-judge*) | Tareas abiertas sin respuesta comprobable (resúmenes, estilo) |
| Modo no interactivo | `-p` propio | `claude -p`, `opencode run`, `codex exec` | — (es la convención) |
| Reintentos | A mano en el bucle | `tenacity`, `backoff`, o el reintento del SDK oficial (§1.0: dos veces, 429 y 5xx) | Sin requisito de enseñarlo ni de cambiar de modelo |
| Modelo de respaldo | En el bucle | Pasarelas: LiteLLM Router, OpenRouter (*fallbacks*) | Muchos proveedores a la vez |

*Solo se citan categorías y herramientas; no se afirma el comportamiento de
ningún producto concreto más allá de su documentación pública.*

## 3. Diseño de detalle

### 3.1 Ficheros

```
src/mharness/
├── domain/limits.py              # nuevo: TurnLimits
├── domain/retry.py               # nuevo: RetryPolicy (esperas, Retry-After, jitter inyectado)
├── domain/evals.py               # nuevo: Task, Check, TaskRun, Summary, compare()
├── domain/agent_events.py        # ModelRetry, ModelFallback; reasons max_cost, max_tokens
├── domain/errors.py              # ModelRateLimitError.retry_after
├── domain/trace.py               # registros de ModelRetry y ModelFallback; causa timeout
├── ports/evals.py                # nuevo: EvalSuite (tareas, copia del fixture, líneas base)
├── application/agent.py          # límites, reintentos y respaldo
├── application/approvals.py      # AllowList
├── application/headless.py       # nuevo: run_once() → RunResult
├── application/evals.py          # nuevo: ejecutar una tarea, comprobar, resumir
├── application/stats.py          # nuevo: coste acumulado desde las trazas
├── application/sessions.py       # /new, importar, exportar (datos)
└── adapters/
    ├── evals/__init__.py         # nuevo
    ├── evals/toml_suite.py       # nuevo: TomlEvalSuite
    ├── models/openai_chat.py     # Retry-After
    └── cli/
        ├── app.py                # subcomandos y opciones
        ├── headless.py           # nuevo: salida text / json / stream-json
        ├── reports.py            # nuevo: models, sessions, stats, eval
        ├── export.py             # nuevo: sesión → Markdown
        └── conversation.py       # ModelRetry/ModelFallback en pantalla; /new, /export
config.py                         # fallback_model, [limits]
bootstrap.py                      # despacho de subcomandos; AllowList; DenyAll sin -p
evals/tasks/01-…/ … 10-…/task.toml
evals/fixtures/<repos inventados>/
evals/baselines/AAAA-MM-DD-opencode-go-glm-5.3-flash.json
tests/fakes/evals.py
docs/guia/08-evals.md
```

### 3.2 Configuración nueva

```toml
# ~/.config/maha/config.toml (y .maha/config.toml del proyecto)
fallback_model = "glm-5.3"

[limits]
max_steps = 25
max_cost = 0.50      # dólares por turno
max_tokens = 400000
timeout = 600        # segundos por turno
```

Las opciones de la línea de comandos mandan sobre la configuración. Un
proyecto puede poner límites (solo restringen: de cada uno vale el más
estricto de los dos ficheros, §12.4) y un modelo de respaldo (como
ya elige el modelo), pero no permisos (§1.2). Ninguna variable de entorno
nueva.

## 4. Plan de tests

Todo con fakes y directorios temporales; ninguna llamada real.

1. **Límites:** con `FakeModelClient`, el turno para en `max_steps`,
   `max_cost` y `max_tokens` antes de la llamada que lo pasaría, con lo
   ejecutado en el historial; coste desconocido con `max_cost` para; el
   `timeout` cancela y la traza dice `interrupted` con causa `timeout`.
2. **`AllowList`:** aprueba con ámbito y herramienta en la lista; deniega
   sin ámbito (fuera, secreto, `.github`) aunque esté en la lista; deniega
   lo que no está.
3. **`RetryPolicy`:** esperas 1-2-4 con el azar fijado; `Retry-After`
   respetado y recortado a 60 s.
4. **Reintentos en el bucle:** 429 y 503 antes del primer evento se
   reintentan y emiten `ModelRetry`; un error a mitad de respuesta no; 401
   no; agotados, el error sale como hoy; con respaldo, `ModelFallback` y el
   resto del turno con el otro modelo; el turno siguiente, con el principal.
   El reloj de espera se inyecta: los tests no duermen.
5. **Adaptador:** `Retry-After` en segundos y como fecha HTTP, con respx.
6. **`run_once`:** `RunResult` con texto final, motivo, contadores y coste;
   un error del modelo da `reason="error"`.
7. **Línea de comandos:** cada opción y su combinación inválida (por
   ejemplo `--allow` sin `-p`) sale con 2; códigos de salida 0, 1, 3 y 4.
8. **Salida:** `text` deja solo la respuesta en stdout; `json` es un objeto
   válido con los campos de §1.11; `stream-json`, una línea JSON por evento
   y el `result` al final.
9. **stdin:** se une a `-p` entre delimitadores; sin texto es la
   instrucción; más de 10 MB, error.
10. **`-c` y `-r`:** la última sesión de este directorio, incluida una de
    `-p`; `-r` de otro directorio; id que no existe, error claro.
11. **Evals, dominio:** `compare()` marca regresión con los umbrales de
    §1.8 y no la marca dentro de ellos.
12. **Evals, suite:** `TomlEvalSuite` lee una tarea, rechaza una mal
    formada con error claro, copia el fixture a un temporal y escribe y lee
    una línea base.
13. **Evals, aplicación:** con modelo falso, una tarea que edita el fichero
    pasa la comprobación y otra no; las repeticiones se agregan; `--split`;
    un `ModelRateLimitError` cuenta como error de infraestructura, no como
    fallo; con `--jobs 4` el resultado es el mismo que en serie, y cada
    tarea, en su copia.
14. **Las 10 tareas son válidas:** se cargan todas, cada fixture existe y la
    comprobación **falla** sobre el fixture sin tocar (si no, la tarea no
    mide nada).
15. **Comandos de línea:** `models`, `sessions`, `sessions delete`, `trace`,
    `stats` (agregado de varias trazas), `export` (Markdown y JSON) e
    `import` (id nuevo, nunca sobrescribe, JSON inválido rechazado); `/new` y
    `/export`.
16. **Arquitectura:** `adapters/evals` no importa otros adaptadores.

## 5. Evals

Este hito crea la batería y su **primera línea base** (§1.8), con
`opencode-go/glm-5.3-flash` y `opencode-go/kimi-k2.7-code`, 5 repeticiones
cada uno (dudas 3 y 4).

- El PR de evals (PR 2, §6) toma la línea base **antes** de los PRs que
  cambian el bucle (reintentos, PR 4), y esos se comparan contra ella, como
  pide AGENTS.md.
- Los PRs anteriores a la batería (PR 1) cambian el bucle sin cambiar su
  comportamiento por defecto (límites que no se alcanzan): quedan dentro de
  la primera línea base.
- El resultado (fecha, modelo, métricas y comparación) se anota aquí al
  implementar.

**Primera línea base** (2026-10-27, `maha` 0.7.1, commit `d214e0a`, OpenCode
Go; 20 tareas, 5 repeticiones, 4 a la vez; 12 minutos y 0,60 $ en total;
ningún error del proveedor). Ficheros: `evals/baselines/2026-10-27-opencode-go-*.json`.

| Modelo | Éxito | train | validation | Pasos/ejecución | Coste de 100 |
|---|---|---|---|---|---|
| `glm-5.3-flash` | 94/100 | 77/80 | 17/20 | 4,5 | 0,08 $ |
| `kimi-k2.7-code` | 99/100 | 79/80 | 20/20 | 5,3 | 0,52 $ |

Fallos: `glm-5.3-flash` en 12 (1/5), 13 (2/5: nombra funciones que sí
tienen test) y 18 (3/5); `kimi-k2.7-code` en 12 (1/5). Las diez básicas
pasan siempre con los dos. No hay comparación: es la primera.

## 6. Orden de piezas para el implementador

Cada punto, un commit en verde. Seis PRs, en el milestone "Hito 8".

**PR 1 — núcleo sin persona** (`feature/hito-8-nucleo`)
1. `TurnLimits` y los límites en el bucle (pasos, coste, tokens).
2. El tiempo límite del turno, con la causa `timeout` en la traza.
3. `AllowList`.
4. `run_once()` y `RunResult`.
5. `[limits]` en la configuración.

**PR 2 — evals** (`feature/hito-8-evals`)
1. Dominio de evals: `Task`, `Check`, `compare()`.
2. Puerto `EvalSuite` y su fake.
3. `TomlEvalSuite`.
4. `application/evals.py`: ejecutar, comprobar, repetir, resumir; los
   errores de infraestructura, aparte.
5. En paralelo (`--jobs`).
6. `maha eval` y su informe, con `--models` y `--retry-errors`.
7. Fixtures y las 10 tareas, una por commit o de dos en dos.
8. Primera línea base de los dos modelos (llamadas reales, en local) y su
   anotación en §5.

**PR 3 — modo no interactivo** (`feature/hito-8-print`)
1. Opciones y subcomandos en `cli/app.py`.
2. `-p` con salida `text`; stdin.
3. `json` y `stream-json`.
4. `-c`, `-r`, `--model`, `--allow`, límites por opción.
5. Códigos de salida.

**PR 4 — reintentos y respaldo** (`feature/hito-8-reintentos`)
1. `RetryPolicy`.
2. `Retry-After` en el adaptador.
3. Reintentos en el bucle y `ModelRetry`.
4. Modelo de respaldo, `ModelFallback` y `fallback_model`.
5. Terminal y traza de los dos eventos.
6. Evals contra la línea base, anotadas en §5.

**PR 5 — comandos de línea** (`feature/hito-8-comandos`)
1. `maha models`.
2. `maha sessions` y `sessions delete`.
3. `maha trace`.
4. `maha stats`.
5. `maha export` y `/export`.
6. `maha import`.
7. `/new`.

**PR 6 — cierre** (`feature/hito-8-cierre`): versión 0.8.0, verificación
a mano, nota de la guía, spec IMPLEMENTADA, los dos README, PROYECTO,
ESTADO, HISTORIAL y MAPA. **Tras el PR 6:** tag `v0.8.0`.

## 7. Verificación a mano

En un directorio desechable, con OpenCode Go:

1. `maha --version` → `maha 0.8.0`; `maha --help` lista opciones y
   subcomandos.
2. `maha -p "¿qué ficheros hay aquí?"` → solo la respuesta en stdout, las
   llamadas en stderr, código 0.
3. `echo "uno dos" | maha -p "cuenta las palabras"` → usa stdin.
4. `maha -p "crea hola.txt"` sin `--allow` → denegado, código 4, sin
   fichero; con `--allow write_file` → fichero creado, código 0.
5. `maha -p "lee .env" --allow read_file` sobre un `.env` inventado →
   denegado (sin ámbito).
6. `--output-format json | jq .cost_usd` y `stream-json | jq -c .type`.
7. `maha -c -p "¿qué te pedí antes?"` → recuerda; `maha -r ID` en otro
   directorio.
8. `--max-steps 1` en una tarea de varios pasos → código 3; `--timeout 2`
   → código 3 y la traza dice `timeout`.
9. Reintento: `base_url` de un proveedor local que responde 503 (un
   servidor de una línea con `python3 -m http.server` adaptado) →
   `ModelRetry` en pantalla; con `--fallback-model`, `ModelFallback`.
10. `maha models`, `maha sessions`, `maha trace`, `maha stats`, `maha export
    ID > s.md`, `maha export ID --format json > s.json && maha import
    s.json`; `/new` y `/export` dentro.
11. `maha eval --split train` y `maha eval --models glm-5.3-flash,kimi-k2.7-code
    --repeat 5 --save` → informe y un fichero por modelo en
    `evals/baselines/`.

## 8. Lo que no viaja por git y lo que necesita la release

- Ninguna variable nueva. `maha eval` usa la clave de siempre (`.env`).
- `docs/PUESTA_EN_MARCHA.md`: cómo lanzar las evals (`uv run --env-file .env
  maha eval`) y qué cuestan.
- `docs/MAPA.md`: `evals/`, los módulos nuevos y la nota 08.
- Sin pasos manuales en la release.

## 9. Guía

`docs/guia/08-evals.md` — **Cómo se evalúa un agente**:
1. Por qué no basta con probarlo a mano: el modelo no es determinista y los
   cambios pequeños tienen efectos grandes.
2. Tarea + comprobación automática; métricas de éxito, pasos, coste y
   tiempo.
3. Ruido y repeticiones; línea base y regresión; el conjunto de validación
   contra el sobreajuste.
4. El modo no interactivo y los permisos sin persona, y en la industria
   (Inspect, promptfoo, SWE-bench, LangSmith).

## 10. Riesgos

- **Ruido:** con 10 tareas y 5 repeticiones, una diferencia de una tarea
  aún puede ser azar. Por eso la regresión es "pasaba siempre y ahora falla" o
  baja el total, y la decide el mantenedor.
- **Tiempo de una pasada completa** (100 ejecuciones): se mide en la
  primera; `--jobs` lo reparte, y al iterar se usa 1 repetición y `train`.
- **Tareas demasiado fáciles:** si `glm-5.3-flash` las pasa todas, la
  batería no distingue cambios. Se mira en la primera línea base; si pasa,
  se endurecen antes de cerrar (sin mirar la validación).
- **`--allow write_file` en un script** escribe sin preguntar dentro del
  directorio. Es la decisión explícita de quien lanza el comando, y lo que
  ejecuta código (`.github`, `.git`…) se sigue denegando.
- **Sin `run_command` en las evals** no se mide su descripción ni las
  tareas de "ejecuta y arregla" hasta el hito 15.
- **`Retry-After` de OpenCode:** no se sabe si lo manda. POR VERIFICAR; el
  código cubre los dos casos.
- **El respaldo oculta un fallo:** si el principal cae a menudo, el usuario
  podría no notarlo. Por eso `ModelFallback` se enseña siempre y queda en la
  traza.
- **`maha stats` con muchas trazas** lee todas: lento con miles. Mejora
  posible (un índice) si llega a pasar.

## 11. Decisiones

Del humano (2026-10-27): **"lo que quiero es la opción más profesional y que
más valor aporte al producto final para todas las dudas"**. El agente repasó
las nueve con ese criterio:

1. `--allow TOOL` con lo que pregunta "cada vez" siempre denegado: es lo
   que hacen Claude Code (`--allowedTools`, y en `-p` se deniega lo no
   aprobado) y OpenCode (`--auto`, salvo lo denegado); aprobarlo todo no es
   profesional sin sandbox. **Se mantiene.**
2. Sin `run_command` en las evals hasta el sandbox: dar comandos sin
   aislar a un modelo sin persona en la máquina de desarrollo no es una
   práctica profesional. **Se mantiene**, y el hito 15 añade a la batería
   tareas de "ejecuta y arregla".
3. **Cambia: 5 repeticiones** (no 3) para la línea base y antes de cada
   merge: 3 dejan demasiado ruido para decidir un merge.
4. **Cambia: dos modelos** de familias distintas, `glm-5.3-flash` y
   `kimi-k2.7-code`: un cambio que ayuda a uno y perjudica a otro solo se
   ve con dos.
   Con 100 ejecuciones por pasada entran **`--jobs`** (paralelo) y los
   **errores de infraestructura** separados de los fallos (§1.7–§1.9).
5. Solo la respuesta final en stdout: es lo que necesita un script, y la
   convención de `claude -p`. **Se mantiene.**
6. Nombres de Claude Code donde significan lo mismo y propios donde `maha`
   cuenta distinto: `--max-turns` diría lo contrario de lo que hace en
   `maha`. **Se mantiene.**
7. `max_cost` falla cerrado: un tope de dinero que no se puede comprobar no
   es un tope. **Se mantiene.**
8. `[interrupted]` en el hito 11 y bifurcar en el 12: encajan con el
   contexto y los puntos de control, y aquí serían a medias. **Se
   mantiene.**
9. Evals antes que `-p` y los reintentos: así el cambio del bucle se mide.
   **Se mantiene.**

Dudas que se plantearon al mantenedor (registro), con la recomendación del
agente:

1. **Permisos sin persona** (§1.2). Propuesta: `--allow TOOL`, repetible,
   que aprueba solo lo que tiene ámbito; lo que con persona pregunta "cada
   vez" se deniega siempre. Solo por línea de comandos. Alternativa: un
   modo que lo aprueba todo, como `--auto` de OpenCode (más cómodo, más
   peligroso: un fichero que ejecuta código pasaría sin mirar).
   *Cambia DESIGN §8 ("no hay modo sin aprobaciones en v1"); va corregido
   en el mismo commit que esta spec.*
2. **`run_command` en las evals** (§0). Propuesta: no hasta el sandbox del
   hito 15; las tareas se comprueban igual, porque la comprobación la
   ejecuta el arnés. Alternativa: permitirlo ya, en la copia temporal y sin
   credenciales, aceptando que un comando del modelo podría tocar fuera de
   ella.
3. **Repeticiones y regresión** (§1.8). Propuesta: 1 al iterar, 3 para la
   línea base; ⚠ si una tarea que pasaba siempre falla, si baja el éxito
   total, o si coste o pasos suben más de un 20 %. Alternativa: 5
   repeticiones (menos ruido, el doble de tiempo).
4. **Modelo de la línea base.** Propuesta: `opencode-go/glm-5.3-flash`, el
   de uso diario. Alternativa: dos modelos (por ejemplo, añadir `glm-5.3`)
   para ver si un cambio ayuda a uno y perjudica a otro.
5. **Salida de `-p` en texto** (§1.11). Propuesta: solo la respuesta final
   en stdout y el resto en stderr. Alternativa: todo el texto del turno en
   stdout, en directo.
6. **Nombres de opciones** (§1.13). Propuesta: los de Claude Code donde
   significan lo mismo, y `--max-steps`, `--max-cost`, `--max-tokens`,
   `--timeout` y `--allow` propios. Alternativa: copiar también
   `--max-turns`, `--max-budget-usd` y `--allowedTools`.
7. **`max_cost` sin precio conocido** (§1.1). Propuesta: el turno se para
   (falla cerrado). Alternativa: avisar y seguir sin tope.
8. **Lo que sale del hito 8** (§0). Propuesta: la marca `[interrupted by the
   user]` en la batería pasa al hito 11, con tareas de historial previo;
   bifurcar una sesión, al 12. Entran `maha import`, `/new` y `/export`.
   Alternativa: tareas con historial ya en este hito.
9. **Orden de los PRs** (§6). Propuesta: la batería (PR 2) antes de `-p` y
   de los reintentos, para que el cambio de bucle del PR 4 se mida contra la
   línea base. Alternativa: el orden de DESIGN (`-p` primero).

## 12. Aprendido al implementar

### PR 2 (`feature/hito-8-evals`, 2026-10-27)

7. **Comprobar las tareas, no solo el agente.** Un test pasa cada
   comprobación sobre el repo sin tocar (tiene que fallar: si no, la tarea
   no mide nada) y sobre una solución de referencia (tiene que pasar: si
   no, es imposible). Las comprobaciones van en el `task.toml`, nunca en
   un script dentro del repo: el agente podría cambiarlo.
8. **La batería era demasiado fácil** (decisión del mantenedor). Con las
   diez tareas de §1.6, `glm-5.3-flash` pasó 50 de 50 y `kimi-k2.7-code`
   49 de 50: se detectaban regresiones, no mejoras. Entran diez tareas
   difíciles (§1.6), dos más de validación, y `answer_absent` para las que
   piden una lista. DESIGN §9 anotado.
9. **Un stream que no avanza.** En esa medición, una llamada de Kimi siguió
   abierta casi cinco minutos sin contenido y la ejecución llegó al tiempo
   límite de la tarea (300 s) con el fichero ya escrito: contó como
   aprobada. El límite de lectura del cliente (120 s entre bytes) no saltó;
   lo más probable es que llegaran comentarios SSE, que lo reinician
   (**POR VERIFICAR**). Arreglo: cada evento con datos se espera 120 s como
   mucho (`STALL_SECONDS`); si no llega, `ModelUnavailableError`, que en
   las evals es un error del proveedor y no un aprobado.
10. **Comandos en paralelo que se mataban.** Con las comprobaciones a la vez
    (`--jobs`), la limpieza de un comando mataba a los que empezaron
    después ("the check exited with None"): `maha` es subreaper y tomaba
    por escapados a todos los hijos que no conocía. Ahora corre un comando
    a la vez en todo el proceso (un cerrojo por bucle de eventos). En la
    conversación ya era así; las herramientas en paralelo del hito 16
    necesitarán otra forma de distinguirlos. Encontrado porque dos fallos
    de la primera línea base eran falsos: se descartó y se tomó otra.
11. **Una ejecución que llega a un límite se juzga por su comprobación**,
    como en SWE-bench: lo que cuenta es cómo queda el repo. Todo
    `ModelError` (también un 4xx) es un error del proveedor y no cuenta.
12. **Detalles de `maha eval`:** un cliente por ejecución (cada una es una
    sesión para el proveedor, como un `maha -p`); sesiones y trazas en
    `~/.local/state/maha/evals/<fecha-hora>-<sufijo>/`, con `runs.json`
    (cada ejecución entera: el informe da una línea de cada fallo); el
    sufijo aleatorio separa dos `maha eval` del mismo segundo; `--save` solo
    de la batería entera; sale con 1 si hay una regresión; el commit de la
    línea base sale de `git describe --dirty`. Los repos de prueba, fuera de
    ruff (`force-exclude`: pre-commit le pasa los ficheros uno a uno).
13. **Un fallo de proceso del agente:** un commit entró con un test
    intermitente en rojo, porque `| tail -1` ocultaba el código de pytest.
    El test (dos carpetas del mismo segundo ordenadas por nombre) se
    arregló, y el agente encadena los comandos con `pipefail`.

### PR 1 (`feature/hito-8-nucleo`, 2026-10-27)

1. **El tiempo límite no puede ir alrededor del generador.** Con un
   `asyncio.timeout` que abarca un `yield`, la cancelación cae en el
   código de quien lee los eventos (la terminal pintando), no en el bucle;
   y el bucle lo tomaría por Ctrl+C ("cancelled by the user"). Solución:
   `_within()` pone el plazo en cada espera del bucle (el siguiente trozo
   del modelo, preparar la llamada, la aprobación, la herramienta) y, al
   vencer, el turno acaba con `TurnFinished(reason="timeout")`, como los
   demás límites. Conserva lo ejecutado como tras Ctrl+C, con "stopped by
   the time limit" en la llamada en curso. Un `TimeoutError` que no causó
   el plazo sigue siendo el de quien lo lanzó (`scope.expired()`).
2. **Una respuesta a medias no se guarda al vencer el plazo:** su marca
   diría "[interrupted by the user]". Si no se ejecutó nada, no queda nada,
   como tras Ctrl+C.
3. **`run_once` no recibe límites:** los lleva el `Agent` desde su fábrica
   (`bootstrap` con los de la configuración; las evals, con los de su
   tarea). `tool_calls` se cuenta en cada `ToolFinished`, para que también
   salga bien si el modelo falla a mitad del turno.
4. **"Un proyecto solo restringe" necesitaba código:** con "el proyecto
   gana", un `.maha/config.toml` con `max_steps = 1000` aflojaría los 25
   del usuario. De cada límite vale el más estricto de los dos ficheros.
5. **`AllowList` se apoya en que lo que pregunta cada vez llega sin
   ámbito:** fijado con un test sobre las herramientas reales (un `.env`,
   una ruta de fuera y `.github/workflows/ci.yml`).
6. **Verificación a mano** (OpenCode Go, `glm-5.3-flash`, configuración
   temporal): `max_steps = 1` para tras la primera llamada ("[step limit
   reached: 1]"); `timeout = 0.5` corta la respuesta ("[time limit
   reached]") y la traza dice `"reason": "timeout"`. Encontró un fallo,
   arreglado con su test: tras un corte sin ninguna llamada terminada, la
   terminal pintaba "[tokens: 0 in · 0 out · $0 …]".
