Estado: PROPUESTA (2026-10-21) → APROBADA (2026-10-21, sin cambios)

# Spec — Hito 4: Tool calling y bucle agéntico

Referencias: `docs/DESIGN.md` §4 (el bucle), §5 (contrato de datos), §6
(puerto `Tool`), §8, §10 (perímetro, ficheros secretos, entrada no confiable)
y §14 (hito 4); `docs/ANALISIS.md` §5 (piezas 2 y 3); spec del hito 3 (§1.2,
§1.6, §1.10, §10); `AGENTS.md`.

## 0. Alcance

**El problema.** Hoy `maha` solo conversa: no puede mirar nada del proyecto.
Un agente necesita pedir acciones (leer un fichero, buscar), recibir el
resultado y seguir hasta terminar. Es el riesgo central del proyecto: que el
núcleo funcione (DESIGN §14).

**Lo que hace este cambio.** El modelo recibe una lista de herramientas de
solo lectura y puede pedir llamarlas. El bucle valida cada petición, la
ejecuta, le devuelve el resultado y repite hasta que el modelo contesta sin
pedir nada o se llega al límite de pasos. La terminal muestra cada llamada.

```
> ¿Qué dice notas.txt?
  → read_file(path="notas.txt")
  ✓ 3 lines
El fichero dice: comprar pan y llamar a Ane.
  [tokens: 474 in · 122 out · 1 call]
```

Dentro de alcance:
- Bloques `ToolCallBlock` y `ToolResultBlock`; `ToolSpec` en la petición
  (§1.2).
- Evento `ToolCallDelta` y su acumulación (§1.3).
- Adaptador de OpenAI: herramientas en la petición, llamadas en la respuesta
  (`stream()` y `complete()`), resultados en el historial (§1.4).
- Puerto `Tool`, permisos y validación con Pydantic (§1.5).
- Cuatro herramientas de solo lectura: `read_file`, `list_dir`, `glob` y
  `grep`, con perímetro y ficheros secretos (§1.6).
- El bucle (`Agent`), con límite de pasos y `AgentEvent` (§1.7).
- Errores de herramientas devueltos al modelo (§1.8).
- La terminal mostrando cada llamada (§1.9).
- Nota 04 de la guía y docs al día.

**Fuera de alcance** (y por qué):
- Herramientas con efecto, `ApprovalGate` y leer fuera del directorio con
  aprobación: hito 5. Aquí, lo que necesitaría aprobación **se deniega**
  (§1.6).
- Límites de tokens y de tiempo por turno: hito 8, cuando haya ejecución sin
  persona delante. Aquí hay límite de pasos y Ctrl+C (§11, duda 3).
- `max_tokens` en la petición: hito 11 (gestión del contexto). La sonda
  muestra que el razonamiento cuenta dentro del límite (§1.1).
- Ejecutar llamadas en paralelo: hito 15 (subagentes). Aquí, en orden
  (§1.7).
- Respetar `.gitignore`: necesitaría una dependencia o un analizador propio.
  Aquí se saltan unas carpetas fijas (§1.6).
- `ReasoningDelta`, coste y trazas: hito 7. `TurnStarted`, `AgentError` y
  `ApprovalRequested` llegan con su hito (§1.7).
- System prompt: hito 10. El modelo solo ve las descripciones de las
  herramientas.

## 1. Decisiones de fondo

### 1.1 Hechos comprobados

Todos el 2026-10-21. "Agente" = comprobado por el agente de la sesión en la
documentación oficial. "Sonda" = medido por el agente contra OpenCode Go, con
permiso del mantenedor (9 llamadas, `glm-5.3-flash`, prompts y herramientas
inventados, sin ids ni claves). Lo no comprobado es **POR VERIFICAR** (§10).

- **OpenAI Chat Completions, referencia oficial** (agente;
  https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create,
  leída con `curl`: la herramienta de lectura web devolvía 404, el navegador
  y `curl`, 200):
  - `tools`: `[{"type": "function", "function": {name, description,
    parameters, strict}}]`. `name`: a-z, A-Z, 0-9, `_` y `-`, máximo 64.
    `parameters` es un JSON Schema.
  - `tool_choice`: `none`, `auto` (por defecto si hay `tools`), `required` o
    una función concreta. `parallel_tool_calls`: booleano opcional.
  - La llamada del modelo: `{id, type: "function", function: {name,
    arguments}}`. `arguments` es un string JSON, y "el modelo no siempre
    genera JSON válido y puede inventar parámetros": hay que validarlos.
  - El mensaje del asistente: `content` es obligatorio "salvo que haya
    `tool_calls`". El mensaje de resultado: `{role: "tool", tool_call_id,
    content}`.
  - `finish_reason`: `stop`, `length`, `tool_calls`, `content_filter` y
    `function_call` (obsoleto).
  - `max_tokens` está obsoleto en favor de `max_completion_tokens`.
- **Streaming de llamadas** (agente;
  https://developers.openai.com/api/reference/resources/chat/subresources/completions/streaming-events):
  `delta.tool_calls[]` con `index` (obligatorio) e `id`, `type`, `function.name`
  y `function.arguments` opcionales. No documenta si los argumentos llegan
  partidos; los SDK los concatenan por `index`.
- **Cookbook de OpenAI** (agente, búsqueda en developers.openai.com): un
  mensaje `tool` tiene que responder a un mensaje anterior con `tool_calls`.
- **Pydantic 2.14.1** (agente, probado en local): `model_json_schema()` da un
  JSON Schema con `type`, `properties`, `required`, `title` y `description` de
  cada `Field`. `ValidationError.errors(include_url=False,
  include_input=False)` da mensajes cortos sin copiar la entrada.
- **Sonda, OpenCode Go con `glm-5.3-flash`:**

| Dato | Resultado |
|---|---|
| Forma de una llamada en el stream | **Un solo trozo** con `index`, `id` (`call_` + 24), `type`, `function.name` y los argumentos **enteros**. Nunca partidos en las 4 respuestas con llamadas |
| Varias llamadas | "Lee a.txt y b.txt": **dos llamadas en la misma respuesta** (`index` 0 y 1), con texto delante ("Voy a leer ambos ficheros:") |
| `parallel_tool_calls: false` | Aceptado (200) pero **ignorado**: siguen llegando dos llamadas |
| `finish_reason` | `tool_calls` |
| Devolver resultados | El asistente con `content: null` y con `content: ""`: los dos funcionan |
| `"tool_calls": null` | En los trozos de texto de la respuesta siguiente llega `"tool_calls": null` **explícito** (16 a 22 trozos por respuesta) |
| Usuario justo tras un resultado | Aceptado: el modelo contesta normal |
| Llamada sin resultado | OpenCode la acepta; OpenAI no (cookbook). Se empareja siempre |
| Sin stream | `message.tool_calls` con la misma forma (incluye `index`); `content: ""`; `reasoning_content` (en el hito 3 se llamó `reasoning`: el nombre varía) |
| `max_tokens` / `max_completion_tokens` | Los dos aceptados. Con 64, `finish_reason: length`: el razonamiento gasta el límite |
| Coste de las herramientas | Dos herramientas añaden ~200 tokens de entrada por llamada |
| Primer byte | 0,8 a 2,1 s (en el hito 3, ~5 s) |

### 1.2 Bloques de llamada y de resultado

**Dónde:** `domain/messages.py` y `domain/model.py`.

```python
class ToolCallBlock(BaseModel, frozen=True):
    type: Literal["tool_call"] = "tool_call"
    id: str
    name: str
    arguments: str  # JSON text, exactly as the model wrote it


class ToolResultBlock(BaseModel, frozen=True):
    type: Literal["tool_result"] = "tool_result"
    call_id: str
    content: str
    is_error: bool = False


type Block = Annotated[
    TextBlock | ToolCallBlock | ToolResultBlock, Field(discriminator="type")
]


class Message(BaseModel, frozen=True):
    role: Role
    blocks: list[Block]


class ToolSpec(BaseModel, frozen=True):
    name: str
    description: str
    input_schema: dict[str, Any]  # JSON Schema


class ModelRequest(BaseModel, frozen=True):
    ...
    tools: list[ToolSpec] = []
```

- **`arguments` es el texto JSON, no un `dict`.** Corrige DESIGN §5 (anotado).
  El modelo puede escribir JSON inválido (§1.1). Ese intento tiene que quedar
  en el historial, tal cual, junto a su resultado de error, para que el
  modelo vea qué hizo mal. Un `dict` no lo puede guardar. El bucle lo
  convierte y lo valida (§1.8).
- **`content` del resultado es texto**, no una lista de bloques como dice
  DESIGN §5. Las imágenes llegan en el hito 18; entonces se amplía. Corrige
  DESIGN §5 (anotado).
- **Unión discriminada por `type`** (Pydantic): con tres tipos de bloque,
  validar un `Message` necesita saber cuál es cada uno. Las sesiones del
  hito 6 lo leerán de disco.
- `Message.text` sigue juntando solo los `TextBlock`.
- **Roles:** el asistente lleva `TextBlock` y `ToolCallBlock`; los resultados
  van en un `Message(role="tool")` con un `ToolResultBlock` por llamada.

### 1.3 `ToolCallDelta` y su acumulación

**Dónde:** `domain/events.py` y `application/collect.py`.

```python
class ToolCallDelta(BaseModel, frozen=True):
    type: Literal["tool_call_delta"] = "tool_call_delta"
    index: int
    id: str | None = None
    name: str | None = None
    arguments: str = ""  # a fragment, to append


type ModelEvent = TextDelta | ToolCallDelta | MessageEnd
```

- **El adaptador pasa los trozos tal cual; el `Accumulator` los junta por
  `index`** (concatena `name` y `arguments`, guarda el primer `id`). Así el
  mismo código sirve si un servidor parte los argumentos (OpenAI) o no
  (OpenCode, §1.1), y el adaptador de Anthropic (hito 9) emitirá lo mismo.
- `Accumulator.response()` da el mensaje del asistente con el `TextBlock` (si
  hay texto) y un `ToolCallBlock` por `index`, en orden. Una llamada sin `id`
  o sin `name` al final → `ModelResponseError`.
- **Descartado:** que el adaptador junte y emita la llamada entera (un
  `ToolCall` completo). Más simple aquí, pero cada adaptador repetiría la
  acumulación, y DESIGN §5 ya prevé `ToolCallDelta`.

### 1.4 Adaptador de OpenAI

**Dónde:** `adapters/models/openai_chat.py`.

**Petición.** Si hay herramientas, se añade `tools` (no se envían
`tool_choice` ni `parallel_tool_calls`: el valor por defecto es el que se
quiere, y OpenCode ignora el segundo, §1.1):

```json
{"tools": [{"type": "function",
            "function": {"name": "read_file",
                         "description": "Read a text file…",
                         "parameters": {"type": "object", "properties": {…}}}}]}
```

**Historial.** Cada `Message` del dominio se aplana así:

| Dominio | OpenAI |
|---|---|
| `user` con texto | `{"role": "user", "content": texto}` |
| `assistant` con texto y llamadas | `{"role": "assistant", "content": texto o null, "tool_calls": [{"id", "type": "function", "function": {"name", "arguments"}}]}` |
| `tool` con N resultados | N mensajes `{"role": "tool", "tool_call_id", "content"}` |

Un resultado de error se envía con su texto, que ya empieza por `error:`
(§1.8): OpenAI no tiene un campo `is_error`.

**Respuesta.**

| Trozo | El adaptador |
|---|---|
| `delta.tool_calls` con elementos | un `ToolCallDelta` por elemento, en orden |
| `delta.tool_calls: null` o `[]` | ignora (llega explícito, §1.1) |
| `finish_reason: tool_calls` | `stop_reason="tool_use"` (mapa del hito 2) |

`complete()` traduce igual `message.tool_calls` a `ToolCallBlock` (el puerto
mantiene `complete()`, spec 3 §1.2).

### 1.5 Puerto `Tool`, permisos y registro

**Dónde:** `domain/tools.py` (permiso y errores), `ports/tools.py` (el
puerto) y `application/tools.py` (el registro).

```python
type Permission = Literal["read", "effect"]


class ToolError(Exception):
    """An expected failure, explained to the model (file not found…)."""


class Tool[P: BaseModel](Protocol):
    name: str
    description: str
    params: type[P]
    permission: Permission

    async def run(self, params: P) -> str: ...

    def summary(self, result: str) -> str:
        """A few words for the terminal: "3 lines", "12 entries"."""
        ...
```

- **`summary` resume un resultado correcto para la terminal** (§1.9), sin
  enseñar su contenido.
- **`run` devuelve texto o lanza `ToolError`.** El bucle construye el
  `ToolResultBlock` (sabe el `call_id`; la herramienta no lo necesita).
- **`ToolSpec` se genera del modelo Pydantic:** `params.model_json_schema()`.
  Lo que ve el modelo y lo que se valida salen de la misma clase.
- **Registro (`ToolRegistry`):** guarda las herramientas por nombre, da la
  lista de `ToolSpec` y busca por nombre. **En el hito 4 rechaza una
  herramienta `effect`** al registrarla: no hay `ApprovalGate` que la pueda
  autorizar. Un test lo fija. Lo que no está registrado no existe para el
  modelo (DESIGN §10).
- **Por qué el permiso es código:** AGENTS.md ("límites y permisos son
  código") y DESIGN §10.

### 1.6 Las cuatro herramientas de solo lectura

**Dónde:** `adapters/tools/files.py` (las herramientas) y
`domain/paths.py` (las reglas puras de rutas).

| Herramienta | Parámetros | Devuelve | Tope |
|---|---|---|---|
| `read_file` | `path`, `offset=1`, `limit=None` | Las líneas, numeradas (`   12\t…`) | 2000 líneas o 100 000 caracteres |
| `list_dir` | `path="."` | Entradas, carpetas con `/` al final, ordenadas | 500 entradas |
| `glob` | `pattern`, `path="."` | Rutas relativas que encajan (`**/*.py`), ordenadas | 200 rutas |
| `grep` | `pattern` (regex de Python), `path="."`, `glob=None` | `ruta:línea: texto` | 100 coincidencias; líneas a 300 caracteres |

Al pasar un tope, se corta y se avisa al final, para que el modelo sepa que
falta algo:

```
… [truncated: 2000 of 5321 lines shown; use offset to read more]
```

- **Perímetro:** toda ruta se resuelve (`Path.resolve()`, que sigue enlaces
  simbólicos) y tiene que quedar **dentro del directorio de trabajo**. Fuera
  → `ToolError("outside the working directory")`. DESIGN §10 pide
  aprobación para leer fuera; sin `ApprovalGate` (hito 5), **se deniega**.
  Se resuelve antes de comprobar: `../`, rutas absolutas y enlaces a fuera no
  escapan.
- **Ficheros secretos, denegados** (DESIGN §10): `.env` y `.env.*`, `*.pem`,
  `*.key`, `id_rsa*`, `id_ed25519*`, `.netrc`, `.pgpass`, y todo lo que haya
  dentro de `.ssh/`, `.aws/`, `.gnupg/`, `.docker/`, `.kube/`. Se deja
  `.env.example` (es una plantilla, y está en el repo). `read_file` da
  `ToolError("secret file")`; `list_dir` los muestra con la marca
  `[secret]`, para que el modelo sepa que existen y no los pida; `glob` y
  `grep` los saltan.
  - La regla es una función pura en `domain/paths.py`
    (`is_secret(relative_path) -> bool`), probada sin disco.
- **Carpetas que se saltan** en `glob` y `grep` (no en `list_dir`): `.git`,
  `.venv`, `venv`, `node_modules`, `__pycache__`, `.mypy_cache`,
  `.ruff_cache`, `.pytest_cache`. Sin leer `.gitignore` (§0).
- **Binarios:** un fichero con un byte nulo en sus primeros 8 KiB es binario.
  `read_file` da `ToolError("binary file")`; `grep` lo salta.
- **Texto:** UTF-8 con `errors="replace"`.
- **Sin hilos.** Leer del disco bloquea, pero `asyncio.to_thread` deja un
  hilo vivo que `asyncio.run` espera al salir: el mismo cuelgue con Ctrl+C
  que el hito 2 (spec 2, §12). En su lugar, `glob` y `grep` ceden el control
  (`await asyncio.sleep(0)`) cada 100 ficheros: Ctrl+C los corta. Un
  `read_file` acotado a 100 000 caracteres es corto.
  - Tope de recorrido: `glob` y `grep` miran como mucho 20 000 ficheros, y
    avisan si paran antes.
- **Directorio de trabajo:** el de arranque de `maha`, fijado al crear las
  herramientas en `bootstrap`. No cambia en la sesión.
- **Descripciones**, en inglés, cortas y con un ejemplo, porque son lo único
  que el modelo sabe de cada herramienta (no hay system prompt hasta el
  hito 10). Ver §3.2.

### 1.7 El bucle (`Agent`)

**Dónde:** `application/agent.py` y `domain/agent_events.py`.

```python
class Agent:
    def __init__(
        self,
        client: ModelClient,
        tools: ToolRegistry,
        *,
        model: str,
        max_steps: int = MAX_STEPS,
    ) -> None: ...

    def run(self, text: str) -> AsyncGenerator[AgentEvent]: ...
```

Un turno, desde el mensaje del usuario:
1. **Paso:** llama al modelo con el historial, el turno hasta ahora y las
   herramientas (`stream()`). Reenvía cada `TextDelta` y acumula.
2. Al llegar `MessageEnd`: `ModelCallFinished(usage, model)`. El mensaje del
   asistente se añade al turno.
3. **Sin llamadas** → `TurnFinished(reason="end_turn", usage=…)` y el turno
   se guarda en el historial. Fin.
4. **Con llamadas:** por cada una, **en orden**: `ToolCallProposed(call)` →
   validar y ejecutar (§1.8) → `ToolFinished(call, result, duration)`. Los
   resultados van en un `Message(role="tool")` que se añade al turno. Vuelve
   a 1.
5. **Límite de pasos** (`MAX_STEPS = 25` llamadas al modelo por turno):
   `TurnFinished(reason="max_steps")`. El turno **se guarda** como esté (acaba
   en los resultados; la sonda confirma que el usuario puede seguir, §1.1).

```python
type AgentEvent = (
    TextDelta | ToolCallProposed | ToolFinished | ModelCallFinished | TurnFinished
)
```

- **El turno es atómico ante un fallo** (como en el hito 3): un `ModelError`
  sube como excepción y el turno no se guarda; Ctrl+C cancela el turno entero
  y tampoco se guarda. Se puede porque en el hito 4 nada tiene efecto: no hay
  nada hecho que el historial deba recordar. **El hito 5 lo revisa**, porque
  una edición ya hecha sí debe constar.
- **En orden, no en paralelo:** el modelo puede pedir varias llamadas a la vez
  (§1.1). Son lecturas cortas; en orden, la terminal y los tests son
  deterministas. El paralelo llega con los subagentes (hito 15).
- **`usage` de `TurnFinished`** suma el de todas las llamadas del turno.
- **`Chat` desaparece:** `Agent` hace lo mismo y más (spec 3, §1.6, pasa a
  `Agent`: el turno se guarda antes de ceder `TurnFinished`). Duda 1 de §11.
- **Fuera de este hito:** `TurnStarted` (no aporta nada sin trazas),
  `AgentError` (los errores siguen siendo excepciones hasta el hito 7),
  `ApprovalRequested` (hito 5). Corrige DESIGN §5 solo en el calendario:
  anotado.
- **El límite es código**, no una frase en el prompt (AGENTS.md).

### 1.8 Errores de las herramientas, de vuelta al modelo

**Dónde:** `application/agent.py`.

Cada fallo de una llamada se convierte en un `ToolResultBlock(is_error=True)`
con un texto que empieza por `error:`, y **el bucle sigue**: el modelo puede
corregirse.

| Situación | Texto del resultado |
|---|---|
| Herramienta desconocida | `error: unknown tool "x". Available: read_file, list_dir, glob, grep` |
| `arguments` no es JSON, o no es un objeto | `error: arguments are not a valid JSON object` |
| No valida con el modelo Pydantic | `error: invalid arguments: path: Input should be a valid string` (de `errors(include_url=False, include_input=False)`) |
| `ToolError` | `error: ` + su mensaje |
| Cualquier otra excepción (un fallo nuestro) | `error: internal error in tool "x"`. Además, la terminal lo avisa por stderr con el tipo de excepción, para arreglarlo |

- **Validar antes de ejecutar:** AGENTS.md lo exige ("los argumentos se
  validan con el modelo Pydantic de la herramienta antes de ejecutar").
- **Resultados no confiables:** van en mensajes `tool`, que es la
  delimitación del propio formato de la API. Nunca cambian herramientas ni
  permisos: el registro es fijo en el turno. El aviso en el system prompt
  llega con el hito 10.

### 1.9 La terminal

**Dónde:** `adapters/cli/conversation.py`.

```
> Busca dónde se define parse_sse
⠋ maha
  → grep(pattern="def parse_sse")
  ✓ 1 match
⠋ maha
Está en src/mharness/adapters/models/sse.py, línea 23.
  [tokens: 1240 in · 96 out · 1 call]
```

- `ToolCallProposed` → `  → nombre(arg=valor, …)`: los argumentos tal como
  los mandó el modelo, en una línea, cortada a 100 caracteres.
- `ToolFinished` → `  ✓ <resumen>` o `  ✗ <error>`. El resumen lo da la
  herramienta con `Tool.summary()` (`3 lines`, `12 entries`, `1 match`). El
  contenido no se enseña: puede ser largo, y el usuario no lo ha pedido.
  Duda 4 de §11.
- Los textos de la terminal siguen en inglés, como los del hito 3
  (`[interrupted]`).
- El spinner vuelve a girar en cada paso, mientras se espera al modelo.
- La línea de tokens suma el turno y cuenta las llamadas. Sin llamadas, como
  en el hito 3.
- `TurnFinished(reason="max_steps")` → `  [step limit reached: 25]`.
- Ctrl+C a mitad del turno (también durante una herramienta): `[interrupted]`
  y el turno no se guarda, como en el hito 3.

## 2. En la industria

| Pieza | M-Harness | Alternativas | Cuándo se elegirían |
|---|---|---|---|
| Bucle agéntico | A mano en `application/agent.py` | OpenAI Agents SDK (`Runner`), Pydantic AI, LangGraph, smolagents | Prisa por tener un agente; patrones ya hechos (handoffs, grafos) |
| Definir herramientas | Clase con modelo Pydantic | Decoradores de función (`@tool` de LangChain, `function_tool` del Agents SDK) | Herramientas simples sin estado |
| Esquema de parámetros | `model_json_schema()` | Escribir el JSON Schema a mano; `inspect` de la firma | Sin Pydantic |
| Llamadas en paralelo | En orden | `asyncio.gather` (Agents SDK, Claude Code) | Herramientas lentas o de red |
| Errores al modelo | Resultado con `error:` y seguir | Excepción que corta el turno | Cuando un fallo debe parar al agente |
| Búsqueda en ficheros | Python puro (`pathlib`, `re`) | ripgrep (Claude Code, OpenCode) | Repos grandes: mucho más rápido y respeta `.gitignore` |
| Límites | Pasos en código | `max_turns` (Agents SDK), `recursion_limit` (LangGraph) | — |

*Solo se citan categorías y herramientas; no se afirma el comportamiento de
ningún producto concreto más allá de su documentación pública.*

## 3. Diseño de detalle

### 3.1 Ficheros

```
src/mharness/
├── domain/messages.py            # ToolCallBlock, ToolResultBlock, Block
├── domain/model.py               # ToolSpec; ModelRequest.tools
├── domain/events.py              # ToolCallDelta
├── domain/tools.py               # nuevo: Permission, ToolError
├── domain/paths.py               # nuevo: is_secret(), SKIPPED_DIRS
├── domain/agent_events.py        # nuevo: ToolCallProposed, ToolFinished, ModelCallFinished, TurnFinished
├── ports/tools.py                # nuevo: Tool
├── application/collect.py        # Accumulator junta ToolCallDelta
├── application/tools.py          # nuevo: ToolRegistry
├── application/agent.py          # nuevo: Agent (sustituye a Chat)
├── application/chat.py           # se borra
└── adapters/
    ├── models/openai_chat.py     # tools, tool_calls, mensajes tool
    ├── tools/files.py            # nuevo: read_file, list_dir, glob, grep
    └── cli/conversation.py       # muestra llamadas; usa Agent
bootstrap.py                      # crea el registro con las cuatro herramientas
tests/
├── fakes/tools.py                # nuevo: FakeTool
├── fixtures/openai_chat/         # streams con tool_calls (forma medida)
└── …                             # ver §4
docs/guia/04-tool-calling.md
```

`import-linter`: `adapters/tools` es un adaptador más; no importa
`adapters/models` ni `adapters/cli`.

### 3.2 Descripciones de las herramientas

```
read_file: Read a text file of the working directory. Lines come numbered.
  Use offset and limit for long files. Example: {"path": "src/app.py"}
list_dir: List a directory of the working directory. Directories end in "/".
  Example: {"path": "src"}
glob: Find files by name pattern, relative to the working directory.
  Example: {"pattern": "**/*.py"}
grep: Search file contents with a Python regular expression.
  Example: {"pattern": "def main", "glob": "*.py"}
```

Son prompts: viven en el código, pasan por esta spec y, desde el hito 8, por
evals (AGENTS.md).

### 3.3 Configuración nueva

Ninguna. `MAX_STEPS` y los topes son constantes del código (§1.6, §1.7).

## 4. Plan de tests

Sin llamadas reales ni red. Disco: solo en `tmp_path`.

**4.1 Dominio** (`tests/unit/test_messages.py`, `test_events.py`,
`test_paths.py`)
1. Bloques inmutables; `Message` valida cada bloque por `type` desde JSON.
2. `Message.text` ignora `ToolCallBlock` y `ToolResultBlock`.
3. `is_secret`: `.env`, `.env.local`, `a/.env`, `x.pem`, `id_rsa`,
   `.ssh/config`, `.aws/credentials` → sí; `.env.example`, `env.py`,
   `docs/key.md` → no.

**4.2 Acumulador** (`tests/unit/test_collect.py`)
1. Junta argumentos partidos del mismo `index`; dos `index` dan dos
   `ToolCallBlock` en orden.
2. Texto y llamadas en el mismo mensaje.
3. Llamada sin `id` o sin `name` → `ModelResponseError`.

**4.3 Registro** (`tests/unit/test_tools_registry.py`)
1. `specs()` da nombre, descripción y el esquema de `model_json_schema()`.
2. Nombre repetido → error. **Herramienta `effect` → error** (fija §1.5).

**4.4 Bucle** (`tests/unit/test_agent.py`, con `FakeModelClient` y `FakeTool`)
1. Sin llamadas: `TextDelta`…, `ModelCallFinished`, `TurnFinished("end_turn")`.
2. Una llamada: el modelo recibe en el paso 2 el mensaje del asistente con la
   llamada y el `tool` con el resultado; eventos en orden.
3. Dos llamadas en una respuesta: se ejecutan en orden; un solo mensaje
   `tool` con dos resultados.
4. Cada fila de §1.8: herramienta desconocida, JSON inválido, no valida,
   `ToolError`, excepción → resultado de error y el bucle sigue.
5. La herramienta recibe los parámetros ya validados (el modelo Pydantic).
6. Límite de pasos: con un modelo que siempre pide herramientas,
   `TurnFinished("max_steps")` tras `max_steps` llamadas; el turno se guarda.
7. El siguiente turno lleva el historial completo, con llamadas y resultados.
8. `ModelError` a mitad (paso 2) → sube; el historial queda como estaba.
9. Cancelar durante una herramienta → el historial queda como estaba.
10. `usage` de `TurnFinished` suma los pasos.
11. La petición lleva los `ToolSpec` del registro.

**4.5 Adaptador** (`tests/adapters/test_openai_chat.py` y
`test_openai_chat_stream.py`, con respx y fixtures de la forma medida)
1. La petición lleva `tools`; sin herramientas, no lleva la clave.
2. Historial: asistente con llamadas (`content` null si no hay texto) y un
   mensaje `tool` por resultado, con `tool_call_id`.
3. Stream: `delta.tool_calls` → `ToolCallDelta`; dos llamadas; texto delante;
   `tool_calls: null` ignorado; `finish_reason: tool_calls` → `tool_use`.
4. Argumentos partidos en varios trozos (forma de OpenAI) → varios
   `ToolCallDelta` del mismo `index`.
5. `complete()`: `message.tool_calls` → `ToolCallBlock`.

**4.6 Herramientas** (`tests/adapters/test_file_tools.py`, en `tmp_path`)
1. `read_file`: líneas numeradas; `offset` y `limit`; tope con aviso;
   no existe; es una carpeta; binario.
2. Perímetro: `../x`, ruta absoluta fuera, enlace simbólico a fuera →
   "outside the working directory". Un enlace dentro → se lee.
3. Secretos: `read_file(".env")` → "secret file"; `list_dir` lo marca;
   `glob` y `grep` no lo devuelven.
4. `list_dir`: ordenado, `/` en carpetas, tope.
5. `glob`: `**/*.py`, salta `.git` y `.venv`, tope con aviso.
6. `grep`: coincidencias `ruta:línea: texto`; `glob` filtra; regex inválida
   → `ToolError`; salta binarios; tope.
7. Cada herramienta cumple el puerto (`Tool[...]` para mypy).

**4.7 Terminal** (`tests/adapters/test_conversation.py`)
1. Muestra `→ llamada` y `✓ resumen` / `✗ error`, y la respuesta final.
2. Línea de tokens con la suma y el número de llamadas.
3. `[step limit reached: 25]`.
4. Ctrl+C durante una herramienta: `[interrupted]`, sigue.
5. Un error interno de una herramienta sale por stderr.

**4.8 De punta a punta** (`tests/test_bootstrap.py`): respx sirve una
llamada a `read_file` y después la respuesta; un fichero real en `tmp_path`.
El segundo POST lleva el resultado con el contenido del fichero.

**4.9 Arquitectura:** `adapters/tools` no importa otros adaptadores; el
núcleo sigue sin httpx ni disco.

## 5. Evals

No aplica todavía: nacen en el hito 8. Este hito cambia el bucle y crea
herramientas y sus descripciones (prompts): **son los primeros candidatos a
la batería del hito 8**, y su línea base se medirá entonces.

## 6. Orden de piezas para el implementador

Cada punto es un commit, en verde.

**PR 1** (`feature/hito-4-contrato`): dominio y acumulador, sin red ni disco.
1. **Bloques.** `ToolCallBlock`, `ToolResultBlock`, `Block`; tests 4.1.1–2.
   *Commit:* "Añadir los bloques de llamada y de resultado"
2. **`ToolSpec` en la petición.** *Commit:* "Añadir las herramientas a la
   petición al modelo"
3. **`ToolCallDelta` y acumulador.** Tests 4.2. *Commit:* "Juntar las llamadas
   a herramientas del stream"
4. **Mapa.** *Commit:* "Actualizar el mapa con el contrato de herramientas"

**PR 2** (`feature/hito-4-adaptador`): el adaptador habla de herramientas.
5. **Petición e historial.** Tests 4.5.1–2. *Commit:* "Enviar herramientas y
   resultados en formato OpenAI"
6. **Llamadas en el stream.** Fixtures con la forma medida; tests 4.5.3–4.
   *Commit:* "Traducir las llamadas a herramientas del stream"
7. **Llamadas en `complete()`.** Test 4.5.5. *Commit:* "Traducir las llamadas
   a herramientas de una respuesta entera"
8. **Mapa.**

**PR 3** (`feature/hito-4-bucle`): puerto, registro y bucle, con fakes.
9. **Puerto y permiso.** `domain/tools.py`, `ports/tools.py`, `FakeTool`.
   *Commit:* "Añadir el puerto Tool"
10. **Registro.** Tests 4.3. *Commit:* "Añadir el registro de herramientas"
11. **Eventos del agente.** *Commit:* "Añadir los eventos del agente"
12. **Bucle.** Tests 4.4.1–3, 4.4.5–7, 4.4.10–11. *Commit:* "Añadir el bucle
    agéntico"
13. **Errores al modelo.** Tests 4.4.4. *Commit:* "Devolver al modelo los
    errores de las herramientas"
14. **Fallos y cancelación.** Tests 4.4.8–9. *Commit:* "Deshacer el turno si
    falla o se cancela"
15. **Mapa.**

**PR 4** (`feature/hito-4-herramientas`): las herramientas de ficheros.
16. **Rutas.** `domain/paths.py`; test 4.1.3. *Commit:* "Añadir las reglas de
    ficheros secretos"
17. **`read_file`** con perímetro y secretos; tests 4.6.1–3 (su parte) y
    4.6.7. *Commit:* "Añadir la herramienta read_file"
18. **`list_dir`**; 4.6.4. *Commit:* "Añadir la herramienta list_dir"
19. **`glob`**; 4.6.5. *Commit:* "Añadir la herramienta glob"
20. **`grep`**; 4.6.6. *Commit:* "Añadir la herramienta grep"
21. **Mapa.**

**PR 5** (`feature/hito-4-terminal`): terminal y cableado.
22. **Terminal con llamadas.** `converse()` usa `Agent`; se borra `Chat`;
    tests 4.7. *Commit:* "Mostrar las llamadas a herramientas en la terminal"
23. **Cableado.** `bootstrap` crea el registro. *Commit:* "Dar las
    herramientas de solo lectura a maha"
24. **Punta a punta.** Tests 4.8.
25. **Mapa.**

**PR 6** (`feature/hito-4-cierre`): versión 0.4.0, nota de la guía, spec en
IMPLEMENTADA y docs. **Tras el PR 6:** tag `v0.4.0`.

## 7. Verificación a mano

Con `opencode-go` y `glm-5.3-flash`, en una copia desechable de un proyecto
(o en el propio repo: solo hay lecturas).

1. `maha --version` → `maha 0.4.0`.
2. "¿Qué hay en este directorio?" → `list_dir`, y una respuesta con lo que
   hay.
3. "¿Dónde se define `parse_sse`?" → `grep` o `glob` + `read_file`, y la
   ruta correcta.
4. "Lee el fichero .env" → `✗ error: secret file`; el modelo lo explica.
5. "Lee /etc/hostname" → `✗ error: outside the working directory`.
6. Una pregunta que necesite varios pasos: se ven varias llamadas seguidas y
   una respuesta final; la línea de tokens cuenta las llamadas.
7. Ctrl+C a mitad de un turno con herramientas: `[interrupted]`; el turno
   siguiente funciona.
8. Dos turnos: el segundo puede referirse a lo leído en el primero.
9. `maha < notas.txt > salida.txt`: sin códigos de escape.

## 8. Lo que no viaja por git y lo que necesita la release

- Nada nuevo: ni variables ni configuración. `PUESTA_EN_MARCHA` sin cambios.
- `docs/MAPA.md`: los ficheros de §3.1.
- `docs/DESIGN.md` §5: `ToolCallBlock.arguments` como texto, el resultado
  como texto y el calendario de `AgentEvent`. Corregido en el mismo commit
  que esta spec, con fecha.

## 9. Guía

`docs/guia/04-tool-calling.md`, "Tool calling y el bucle agéntico":
1. Qué es una herramienta para el modelo: nombre, descripción y JSON Schema;
   el modelo solo **propone**.
2. El viaje de una llamada: `tool_calls` → validar → ejecutar → mensaje
   `tool` → otra llamada al modelo (con el JSON real, abreviado).
3. El bucle y su límite; por qué es código.
4. Los errores vuelven al modelo, que se corrige.
5. Perímetro y secretos: lo que el modelo no puede ver, y por qué en código.
6. "En la industria": la tabla de §2.

## 10. Riesgos

**POR VERIFICAR:**
- **Argumentos partidos en OpenCode:** en la sonda llegaron siempre enteros.
  El acumulador sirve para los dos casos (§1.3).
- **JSON inválido de `glm-5.3-flash`:** no se provocó. Cubierto por §1.8.
- **Formato de error a mitad de stream** (heredado del hito 3).

**Riesgos y contingencias:**
- **El modelo no usa bien las herramientas** sin system prompt: las
  descripciones con ejemplo (§3.2) ayudan; el ajuste fino es del hito 10 y se
  mide en el 8.
- **Bucle que no acaba** (el modelo pide lo mismo una y otra vez): el límite
  de 25 pasos lo corta.
- **Contexto que crece rápido:** cada resultado entra entero en el historial.
  Los topes de §1.6 lo acotan; la compactación es del hito 11.
- **Ficheros grandes o repos enormes:** topes de tamaño y de recorrido (§1.6).
- **Un secreto con otro nombre** (`credenciales.txt`) no se detecta: la lista
  es por nombre. Mejora posible en el hito 5, con aprobación.
- **Fuga por `grep`:** `grep` no lee los secretos de la lista (§1.6), pero sí
  un fichero de código con una clave pegada. Es el mismo riesgo que leerlo;
  el repo tiene gitleaks.

## 11. Decisiones

Del humano (2026-10-21): **acepta las cinco recomendaciones del agente**:
1. `Agent` sustituye a `Chat`; `complete()` sigue en el puerto.
2. Leer fuera del directorio de trabajo, denegado hasta el hito 5.
3. Solo límite de pasos (25) en el hito 4; tokens y tiempo en el hito 8.
4. Resumen de cada resultado en la terminal (`✓ 3 lines`).
5. Llamadas en orden hasta el hito 15.

Propuestas del agente (2026-10-21), aprobadas por el humano con la spec:
**todas las de §1.2 a §1.9 y los seis PRs de §6**.

**Dudas que se plantearon al mantenedor** (registro):
1. **`Chat` desaparece y lo sustituye `Agent`** (propuesta, §1.7). `complete()`
   sigue en el puerto y en el adaptador (spec 3, §1.2), aunque nada de
   `maha` lo use hasta el hito 8. ¿O se mantiene `Chat` para la conversación
   sin herramientas?
2. **Leer fuera del directorio de trabajo: denegado** hasta el hito 5
   (propuesta, §1.6). Alternativa: permitirlo sin preguntar hasta entonces
   (contradice DESIGN §10).
3. **Límites del turno:** solo pasos (25) en el hito 4 (propuesta); tokens y
   tiempo en el hito 8, cuando no haya persona delante. ¿O también un tope
   de tiempo por turno ya?
4. **Resumen de cada resultado en la terminal** (propuesta, §1.9: `✓ 3
   lines`). Alternativa: mostrar las primeras líneas del resultado.
5. **Llamadas en orden** (propuesta, §1.7), no en paralelo, hasta el hito 15.

## 12. Aprendido al implementar (fecha)

*(Se rellena al implementar.)*
