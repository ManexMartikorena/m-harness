Estado: PROPUESTA (2026-10-26) → APROBADA (2026-10-27, por el humano, sin
cambios; el 2026-10-27, al empezar el PR 2, el mantenedor amplía el catálogo
a todos los modelos de cada proveedor y pide precios por tramos, §11)

# Spec — Hito 7: Trazas y coste

Referencias: `docs/DESIGN.md` §5 (`AgentEvent`, `Usage`), §6 (`ModelCatalog`,
`TraceSink`), §10 (trazas sin credenciales), §11 (observabilidad) y §14
(hito 7); `docs/ANALISIS.md` §5 (pieza 15) y §6 (RF 17); pendientes de las
specs 2 (§12, modelos que entrenan con los datos), 3 (§1.7, tokens de
razonamiento), 4 (§1.7, `TurnStarted` y `AgentError`), 5 (§1.4,
`ToolFinished.decision`), mejora `2026-10-23` (D11) y 6 (§1.8, `/model` sin
catálogo; los tokens de cada turno); `AGENTS.md`.

## 0. Alcance

**El problema.** `maha` dice cuántos tokens gasta, pero no cuánto cuesta, ni
qué parte es razonamiento. Lo que pasa en una sesión (cada llamada al
modelo, cada herramienta, su duración, cada aprobación) se ve en pantalla y
se pierde: no hay forma de revisarlo después (RF 17, auditabilidad).

**Lo que hace este cambio.** Cada sesión deja una traza en disco, un evento
por línea, sin credenciales. Un catálogo de modelos da los precios, y la
terminal enseña el coste de cada turno y de la sesión. `/trace` resume la
traza de una sesión.

```
> Arregla el test de config
  → read_file(path="tests/unit/test_config.py")
  ✓ 210 lines
…
  [tokens: 4111 in · 286 out (190 reasoning) · 2 calls · $0.0008 · session $0.0031]
> /trace
  20261026-091502-3fa2 · glm-5.3-flash · 3 turns · 7 model calls · 4 tools
  1 09:15:04  2 calls  1 tool   4111 in  286 out  $0.0008  6.2 s
  2 09:16:40  1 call   0 tools  4398 in   41 out  $0.0007  1.9 s
  …
  total 12 950 in · 512 out · $0.0031
```

Dentro de alcance:
- `Usage.reasoning_tokens` y el desglose en la terminal (§1.2).
- Catálogo de modelos: puerto `ModelCatalog`, fichero TOML propio en el
  paquete y otro opcional del usuario (§1.3, §1.4).
- Coste por llamada, por turno y por sesión (§1.5).
- Eventos `TurnStarted` y `ModelCallFinished.cost` (§1.6).
- Trazas: puerto `TraceSink`, JSONL por sesión, credenciales enmascaradas
  (§1.7, §1.8).
- `/trace [ID]` (§1.9).
- `/model` y el arranque avisan de un modelo fuera del catálogo o que
  entrena con los datos (§1.10).
- Registro de la aplicación en `~/.local/state/maha/maha.log`; el fallo del
  `fsync` de la carpeta (D11) deja rastro ahí (§1.11).
- Nota 07 de la guía y docs al día.

**Fuera de alcance** (y por qué):
- Reintentos ante 429 o 5xx: hito 8 (duda 4).
- Ver el razonamiento del modelo (`ReasoningDelta`): hito 19, con la
  interfaz. Aquí solo se cuentan sus tokens.
- Barra de estado siempre visible (modelo, contexto, coste): hito 19. Aquí
  el coste va en la línea de tokens de cada turno.
- Límite de coste o de tokens por turno: hito 8 (DESIGN §14).
- Exportar a OpenTelemetry o Langfuse: hito 20.
- Precios que dependen de la hora (DeepSeek V4.1 Flash tiene hora punta en
  OpenCode Go): se usa el precio de hora punta, el mayor (§1.3).

## 1. Decisiones de fondo

### 1.1 Hechos comprobados

Todos el 2026-10-26 por el agente.

- **OpenCode Go** (https://opencode.ai/docs/go/): suscripción mensual
  (Go 10 $, Go Plus 40 $). "Usage limits are defined as monthly dollar
  amounts": cada modelo tiene un límite mensual en dólares, y el uso se
  cuenta a precio por token. Precios por 1M de tokens (entrada · salida ·
  caché leída · caché escrita), iguales en Go y Go Plus:

  | Modelo | Entrada | Salida | Caché leída | Caché escrita | Límite Go |
  |---|---|---|---|---|---|
  | `glm-5.3-flash` | 0,15 | 0,50 | 0,03 | — | 60 $ |
  | `glm-5.3` | 1,40 | 4,40 | 0,26 | — | 15 $ |
  | `kimi-k3` | 3,00 | 15,00 | 0,30 | 3,00 | 15 $ |
  | `deepseek-v4.1-flash` (punta) | 0,30 | 1,20 | 0,006 | — | 80 $ |
  | `deepseek-v4.1-flash` (valle) | 0,15 | 0,60 | 0,003 | — | 80 $ |

- **OpenCode Zen** (https://opencode.ai/docs/zen/): pago por uso, con la
  misma tabla por 1M de tokens. Algunos modelos gratis avisan de que usan
  los datos: "During its free period, collected data may be used to improve
  the model" (Big Pickle, Flint 40B Free, MiMo-V2.6-Flash Free…).
- **models.dev** (https://models.dev/api.json, repositorio `sst/models.dev`):
  un TOML por modelo con `[limit]` (`context`, `output`) y `[cost]` en USD
  por millón (`input`, `output`, `cache_read`, `cache_write`). Para
  `opencode-go` coincide con los precios de arriba y da la ventana:
  `glm-5.3-flash` y `glm-5.3` 1 000 000, `kimi-k3` 1 048 576,
  `deepseek-v4.1-flash` 1 000 000. La documentación de OpenCode no publica
  la ventana: se toma de models.dev, con su fecha.
- **El uso que manda OpenCode** (medido en la spec 3, §1.7):
  `prompt_tokens` **incluye** `prompt_tokens_details.cached_tokens`, y
  `completion_tokens` **incluye**
  `completion_tokens_details.reasoning_tokens`. El adaptador ya lee
  `cached_tokens` en `cache_read_tokens`.

### 1.2 Los tokens de razonamiento

- **`Usage.reasoning_tokens`** (dominio): los de razonamiento, **dentro** de
  `output_tokens` (no se suman aparte). El adaptador de OpenAI los lee de
  `completion_tokens_details.reasoning_tokens`.
- **En la terminal:** `286 out (190 reasoning)`, solo si son más de 0.
- Corrige DESIGN §5 (`Usage`).

### 1.3 El catálogo: un TOML en el paquete, y otro del usuario

**Dónde:** `src/mharness/adapters/catalog/models.toml` (datos) y
`adapters/catalog/toml_catalog.py` (lee).

```toml
checked = 2026-10-26   # when prices were checked against the docs
source = "https://opencode.ai/docs/go/"

[models."opencode-go/glm-5.3-flash"]
context = 1_000_000          # models.dev, 2026-10-26
input = 0.15                 # USD per 1M tokens
output = 0.50
cache_read = 0.03

[models."opencode-zen/big-pickle"]
input = 0
output = 0
trains_on_data = true        # "collected data may be used to improve the model"
```

- **Clave `proveedor/modelo`:** el mismo id cuesta distinto en Go y en Zen.
  El proveedor es el nombre de la configuración (`opencode-go`,
  `opencode-zen` o uno del usuario).
- **Precios con fecha** (`checked`): cambian. La guía y `/trace` dicen de
  qué día son. Actualizarlos es un PR con su comprobación (AGENTS.md, hechos
  externos).
- **El del usuario manda:** `~/.config/maha/models.toml`, mismo formato,
  para sus proveedores (un Ollama local cuesta 0) o para corregir un precio
  sin esperar a una versión. Solo en la configuración del usuario, nunca en
  la del proyecto: un repositorio ajeno no cambia lo que `maha` te dice que
  cuesta (como los proveedores, spec 2, §1.10).
- **Lo que entra al principio:** ~~los cuatro modelos de Go de §1.1 y los
  mismos en Zen si están en su tabla, más los gratis de Zen que entrenan con
  los datos~~. *(Cambiado por el mantenedor el 2026-10-27, §11:)* **todos
  los modelos de cada proveedor**, tal como los publica su tabla de precios:
  los 30 de Go y los 83 de Zen (comprobados el 2026-10-27). Cada proveedor
  nuevo (Anthropic, hito 9) trae los suyos. Lo que no está, no tiene coste
  (§1.5).
- **Precios por tramos** *(añadido el 2026-10-27, §11)*: varios modelos
  cobran más cuando el prompt pasa de un tamaño (GPT 6 Luna: 0,10 $ hasta
  272 000 tokens de entrada, 0,20 $ por encima). Cada modelo puede llevar
  tramos; el coste de una llamada usa el tramo que corresponde a sus
  `input_tokens` (§1.4 y §1.5).
- **Descuentos temporales** (Gemini 4 Argon hasta el 2026-11-30, Mistral
  Large 4): el precio con descuento, que es lo que se cobra hoy, con la
  fecha de fin en un comentario.
- **La ventana de contexto**, de models.dev, por proveedor; los precios,
  siempre de la documentación del proveedor (models.dev no siempre coincide:
  da a DeepSeek en Go el precio de valle).
- **Precio por hora:** DeepSeek V4.1 Flash, el de hora punta (el mayor): el
  coste nunca se queda corto.
- Descartado: descargar models.dev al arrancar (red en cada arranque, un
  fichero de 6 MB y una fuente que no controla el proyecto) y ponerlo en
  `config.toml` (los precios no son configuración del usuario).

### 1.4 Puerto `ModelCatalog`

**Dónde:** `domain/catalog.py` (tipos) y `ports/catalog.py`.

```python
class ModelInfo(BaseModel, frozen=True):
    provider: str
    model: str
    context: int | None = None
    prices: Prices | None = None  # None: unknown, no cost shown
    trains_on_data: bool = False


class Prices(BaseModel, frozen=True):
    input: Decimal  # USD per 1M tokens
    output: Decimal
    cache_read: Decimal | None = None  # None: billed as input
    cache_write: Decimal | None = None
    checked: date
    tiers: tuple[Tier, ...] = ()  # added 2026-10-27: prices above a size


class Tier(BaseModel, frozen=True):
    above: int  # input tokens of the call; from above + 1 on
    input: Decimal
    output: Decimal
    cache_read: Decimal | None = None
    cache_write: Decimal | None = None


class ModelCatalog(Protocol):
    def get(self, provider: str, model: str) -> ModelInfo | None: ...
```

- **Síncrono:** se lee una vez al arrancar (en `bootstrap`); `get` no toca
  el disco. Fake: `MemoryCatalog`.
- **Tramos en el TOML** *(añadido el 2026-10-27)*: cada tramo es una tabla
  del modelo.

  ```toml
  [models."opencode-go/gpt-6-luna"]
  context = 1_050_000
  input = 0.10
  output = 0.50
  cache_read = 0.01
  cache_write = 0.125

  [[models."opencode-go/gpt-6-luna".tiers]]
  above = 272_000              # "> 272K tokens"
  input = 0.20
  output = 0.75
  cache_read = 0.02
  cache_write = 0.25
  ```
- **`Decimal`, no `float`:** 0,003 $ por millón por 41 tokens no debe
  redondearse por el camino.

### 1.5 El coste

**Dónde:** `domain/catalog.py`, `cost(usage, prices) -> Decimal`.

*(Añadido el 2026-10-27 por decisión del mantenedor, §11:)* **Primero, el
coste que da el proveedor.** OpenCode manda en cada respuesta lo que la
llamada cuenta contra el límite (`usage.opencode.allowance`; medido en Go,
y coincide al dígito con el del catálogo, §12.35). Cuando el proveedor lo
da, se usa ese: es exacto también con precios por hora (DeepSeek en Go) y
por tramos. El catálogo queda para cuando no lo da. El adaptador lo lee en
este orden: `usage.opencode.allowance`, `usage.opencode.list_cost` y
`usage.cost` (OpenRouter); va en `MessageEnd.cost` y `ModelResponse.cost`.

```
coste = (input − cache_read) × input  +  cache_read × cache_read
      + cache_write × cache_write  +  output × output        (cada uno / 1M)
```

*(Corregido al implementar, §12.1: `input` incluye también `cache_write`, y
se resta igual que `cache_read`.)*

- La caché leída, a su precio (o al de entrada si no tiene); el
  razonamiento ya va dentro de `output`.
- **Con tramos** *(añadido el 2026-10-27)*: si `input_tokens` pasa del
  `above` de un tramo, toda la llamada va a los precios de ese tramo (el de
  `above` mayor que se pase), como lo publica el proveedor.
- **Sin precio, sin coste:** `None`, y la terminal no enseña `$`. Nunca un
  `$0.0000` que parezca gratis.
- **Por turno:** la suma de sus llamadas. **Por sesión:** la suma de los
  turnos guardados (`UsageEntry.cost`, nuevo y opcional: las sesiones del
  hito 6 se leen igual) más el actual.
- **En la terminal:** `· $0.0008 · session $0.0031`, con 4 decimales (o
  `<$0.0001`).
- **OpenCode Go:** el coste es lo que el turno cuenta contra el límite
  mensual en dólares de ese modelo (§1.1). La nota de la guía lo explica.

### 1.6 Eventos: `TurnStarted` y el coste

- **`TurnStarted(text)`**, el primero de cada turno: marca su hora en la
  traza.
- **`ModelCallFinished(usage, model, cost)`**: el `Agent` calcula `cost` con
  el catálogo que recibe (puerto `ModelCatalog`), por el modelo que contestó.
- **`TurnFinished` lleva `cost`**, la suma del turno (o `None` si alguna
  llamada no tiene precio).
- **`AgentError` no se crea** (duda 3): los errores siguen siendo
  excepciones, como hasta ahora, y la traza los apunta desde fuera del bucle
  (§1.7). Corrige DESIGN §5, que la preveía.

### 1.7 La traza: un JSONL por sesión

**Dónde:** `domain/trace.py` (tipos y `mask()`), `ports/tracing.py`,
`adapters/tracing/jsonl_traces.py` y `application/sessions.py` (quien
traza).

`~/.local/share/maha/traces/<id de la sesión>.jsonl`, un registro por línea:

```json
{"at": "2026-10-26T09:15:04.120Z", "session": "20261026-091502-3fa2", "event": {"type": "turn_started", "text": "Arregla el test de config"}}
{"at": "2026-10-26T09:15:09.802Z", "session": "20261026-091502-3fa2", "event": {"type": "model_call_finished", "model": "glm-5.3-flash", "usage": {"input_tokens": 2051, "output_tokens": 120, "reasoning_tokens": 80, …}, "cost": "0.00009"}}
{"at": "2026-10-26T09:15:09.950Z", "session": "20261026-091502-3fa2", "event": {"type": "tool_finished", "call": {…}, "duration": 0.12, "decision": null, …}}
{"at": "2026-10-26T09:15:20.000Z", "session": "20261026-091502-3fa2", "event": {"type": "error", "kind": "ModelUnavailableError", "message": "HTTP 503: …"}}
```

- **`Conversation.run()` traza:** cada `AgentEvent` que pasa, con su hora; y
  si el turno acaba con una excepción, un registro `error` (tipo y mensaje),
  y otro `interrupted` si fue Ctrl+C. El `Agent` sigue sin saber nada.
- **Todo, menos los trozos de texto:** los `TextDelta` no se trazan uno a
  uno (serían miles de líneas); el texto entero ya está en la sesión, y la
  traza lleva los eventos con hora, tokens, coste, duración y decisión.
- **El id de la sesión, desde el principio:** `Conversation` genera su id al
  empezar (antes, con el primer guardado), para que la traza y la sesión se
  llamen igual. El fichero de la sesión sigue naciendo con el primer turno.
- **Mismos cuidados que las sesiones:** carpeta `0700`, ficheros `0600`,
  solo se añade, y un fallo al escribir no corta la conversación (se avisa
  una vez). Sin `fsync` por registro: la traza no es lo que se retoma; se
  hace `fsync` al terminar cada turno.
- **Se borra con su sesión:** `/delete` borra las dos.

### 1.8 Sin credenciales en la traza

**Dónde:** `domain/trace.py`, `mask(text, known) -> str`.

- **Valores conocidos:** la clave del proveedor (la de `api_key_env`) y
  cualquier valor de más de 8 caracteres de una variable de entorno cuyo
  nombre parezca de credencial (`*KEY*`, `*TOKEN*`, `*SECRET*`,
  `*PASSWORD*`), sustituidos por `[redacted]`. La lista la da `bootstrap`.
- **Patrones de claves:** `sk-…`, `ghp_…`/`github_pat_…`, `AKIA…`,
  `xox[bp]-…`, `-----BEGIN … PRIVATE KEY-----`… (lista en el dominio, con
  tests).
- **Se aplica a todos los textos del registro** antes de escribirlo: los
  argumentos, los resultados de las herramientas, los mensajes de error.
- **La sesión no se enmascara:** es la conversación tal cual, y retomarla
  necesita el texto real (spec 6, §1.3). La traza es para auditar, y puede
  acabar compartida.
- Riesgo: un secreto con otra forma pasa (§10).

### 1.9 `/trace [ID]`

Sin ID, la sesión actual; con ID, otra (de cualquier directorio). Lee la
traza y la resume por turno: hora, llamadas al modelo, herramientas, tokens,
coste y duración, y el total. Las herramientas que fallaron o se denegaron,
marcadas. No necesita bloquear la sesión: solo lee.

```
  1 09:15:04  2 calls  1 tool   4111 in  286 out  $0.0008  6.2 s
  2 09:16:40  1 call   1 tool ✗ (denied)  …
```

- **Para el detalle, el fichero:** `/trace` dice dónde está. Leer el JSONL
  entero es cosa de `jq` o del hito 20 (Langfuse).
- Todo lo que viene del disco pasa por `clean()`.

### 1.10 Avisos del catálogo

- **Al arrancar y con `/model`:** si el modelo no está en el catálogo,
  `[model not in the catalog: no cost shown]`; si entrena con los datos,
  `[warning: this model may use your data for training]`, en amarillo
  (ANALISIS §9: se evitan los que entrenan).
- **`/model` no se niega:** un modelo nuevo del proveedor puede no estar aún
  en el catálogo.

### 1.11 El registro de la aplicación

**Dónde:** `bootstrap` configura `logging` de la biblioteca estándar:
`$XDG_STATE_HOME/maha/maha.log` (por defecto `~/.local/state/maha/`), nivel
`WARNING`, rotado a 1 MiB con una copia (`RotatingFileHandler`).

- **Solo diagnóstico, nunca contenido** (DESIGN §11): fallos del disco al
  guardar una sesión o una traza, el `fsync` de la carpeta que falla (D11,
  ahora sí deja rastro), errores internos de una herramienta.
- **Lo usan los adaptadores**, con `logging.getLogger(__name__)`; ni el
  dominio ni la aplicación lo importan (para ellos, el exterior va por
  puertos).
- En los tests, `conftest.py` da también un `XDG_STATE_HOME` propio.

## 2. En la industria

| Pieza | M-Harness | Alternativas | Cuándo se elegirían |
|---|---|---|---|
| Trazas | JSONL propio por sesión | OpenTelemetry con las convenciones GenAI; Langfuse, LangSmith, Arize Phoenix, Helicone; OpenLLMetry, OpenLIT | Equipos, varios servicios, paneles: hito 20 |
| Catálogo y precios | TOML propio en el paquete | models.dev (datos abiertos, del equipo de OpenCode); `model_prices_and_context_window.json` de LiteLLM; las APIs de facturación de cada proveedor | Muchos proveedores; precios siempre al día |
| Coste | Tokens × precio, en `Decimal` | Lo que devuelve el proveedor (OpenRouter da el coste por llamada); la factura | Cuando el proveedor lo da |
| Secretos en logs | Valores conocidos + patrones | Filtros de logging (structlog), detect-secrets, el enmascarado de Langfuse | Volúmenes grandes |
| Registro | `logging` de la biblioteca estándar | structlog, loguru | Logs estructurados para un servicio |

## 3. Diseño de detalle

### 3.1 Ficheros

```
src/mharness/
├── domain/model.py               # Usage.reasoning_tokens
├── domain/catalog.py             # nuevo: ModelInfo, Prices, cost()
├── domain/trace.py               # nuevo: TraceRecord, mask(), patrones
├── domain/agent_events.py        # TurnStarted; ModelCallFinished.cost; TurnFinished.cost
├── domain/session.py             # UsageEntry.cost
├── ports/catalog.py              # nuevo: ModelCatalog
├── ports/tracing.py              # nuevo: TraceSink, TraceLog
├── application/agent.py          # TurnStarted y el coste, con el catálogo
├── application/sessions.py       # traza cada turno; id desde el principio; /delete borra la traza
├── application/traces.py         # nuevo: el resumen de /trace a partir de los registros
└── adapters/
    ├── catalog/__init__.py       # nuevo
    ├── catalog/models.toml       # nuevo: los datos
    ├── catalog/toml_catalog.py   # nuevo: TomlCatalog (paquete + usuario)
    ├── tracing/__init__.py       # nuevo
    ├── tracing/jsonl_traces.py   # nuevo: JsonlTraceSink
    ├── models/openai_chat.py     # reasoning_tokens
    ├── storage/sessions.py       # logging del fsync de la carpeta
    ├── tools/files.py            # logging del fsync de la carpeta (D11)
    └── cli/                      # línea de tokens con coste, /trace, avisos
config.py                         # state_dir()
bootstrap.py                      # catálogo, trazas, logging, secretos conocidos
tests/fakes/catalog.py, tests/fakes/tracing.py
docs/guia/07-observabilidad.md
```

### 3.2 Configuración nueva

- `~/.config/maha/models.toml`, opcional (§1.3).
- Ninguna variable nueva.

## 4. Plan de tests

Sin llamadas reales ni red. Disco: solo en `tmp_path`; `conftest.py` aísla
también `XDG_STATE_HOME` y `XDG_CONFIG_HOME` del catálogo del usuario.

**4.1 Dominio** (`tests/unit/test_catalog.py`, `test_trace.py`)
1. `cost()`: entrada, salida, caché leída a su precio y sin él, caché
   escrita, razonamiento ya dentro; `Decimal` exacto.
2. `mask()`: un valor conocido, cada patrón, varios en un texto, nada que
   enmascarar; un valor corto no se enmascara (falsos positivos).
3. `UsageEntry` sin `cost` (sesión del hito 6) se lee.

**4.2 Catálogo** (`tests/adapters/test_toml_catalog.py`)
1. El `models.toml` del paquete se lee y tiene los modelos de §1.3, con
   `checked`; sus tramos, ordenados y por encima del precio base.
2. El del usuario gana y añade; uno roto da un error claro al arrancar.
3. Un modelo que no está → `None`.

**4.3 Adaptador de OpenAI:** `reasoning_tokens` con stream y sin él; sin
`completion_tokens_details` → 0.

**4.4 Bucle** (`tests/unit/test_agent.py`, con `MemoryCatalog`)
1. `TurnStarted` primero; `ModelCallFinished.cost` con precio y sin él.
2. `TurnFinished.cost`: suma, o `None` si una llamada no tiene precio.

**4.5 Trazas** (`tests/adapters/test_jsonl_traces.py`,
`tests/unit/test_sessions.py`)
1. Un registro por evento (sin `TextDelta`), con hora y sesión; `0600`.
2. Un fallo del modelo → registro `error`; Ctrl+C → `interrupted`.
3. Los secretos conocidos y los patrones no llegan al fichero.
4. Un fallo al escribir la traza no corta el turno y se avisa una vez.
5. La sesión y la traza se llaman igual; `/delete` borra las dos.
6. `UsageEntry.cost` se guarda y la sesión retomada suma su coste.

**4.6 `/trace`** (`tests/unit/test_traces.py`, `tests/adapters/test_commands.py`)
1. El resumen por turno y el total, con herramientas denegadas y fallidas.
2. Sin traza, otra sesión, un fichero con líneas rotas (se saltan).

**4.7 Terminal y arranque**
1. Línea de tokens con razonamiento, coste y sesión; sin precio, sin `$`.
2. Avisos de modelo fuera del catálogo y que entrena con los datos.
3. `maha.log` recibe el fallo del `fsync` de la carpeta (D11) y nunca el
   contenido de la conversación.

**4.8 De punta a punta** (`tests/test_bootstrap.py`): un turno con respx
deja una traza con su `model_call_finished` y su coste, sin la clave.

## 5. Evals

No aplica todavía (hito 8). Las trazas serán la fuente de las métricas de
pasos, tokens y coste de la batería.

## 6. Orden de piezas para el implementador

Cada punto es un commit, en verde, con su test primero.

**PR 1** (`feature/hito-7-coste`): tokens, catálogo y coste en el dominio.
1. `Usage.reasoning_tokens` y el adaptador de OpenAI. 4.3.
2. `Prices`, `ModelInfo` y `cost()`. 4.1.1.
3. Puerto `ModelCatalog` y `MemoryCatalog`.
4. Mapa.

**PR 2** (`feature/hito-7-catalogo`): el catálogo en TOML.
5. `models.toml` con los precios de §1.1 y `TomlCatalog`. 4.2.
6. Mapa.

**PR 3** (`feature/hito-7-eventos`): eventos y coste en el bucle y la sesión.
7. `TurnStarted`, `ModelCallFinished.cost` y `TurnFinished.cost`. 4.4.
8. `UsageEntry.cost` y el coste de la sesión. 4.1.3, 4.5.6.
9. Mapa.

**PR 4** (`feature/hito-7-trazas`): las trazas.
10. `TraceRecord` y `mask()`. 4.1.2.
11. Puerto `TraceSink` y `JsonlTraceSink`. 4.5.1, 4.5.3.
12. `Conversation` traza (id desde el principio, `error`, `interrupted`,
    `/delete`). 4.5.2, 4.5.4, 4.5.5.
13. Resumen de `/trace`. 4.6.1.
14. Mapa.

**PR 5** (`feature/hito-7-terminal`): terminal, registro y cableado.
15. Línea de tokens con coste; avisos del catálogo. 4.7.1, 4.7.2.
16. `/trace`. 4.6.2.
17. `state_dir()`, `maha.log` y D11. 4.7.3.
18. Cableado en `bootstrap`. 4.8.
19. Mapa y `PUESTA_EN_MARCHA`.

**PR 6** (`feature/hito-7-cierre`): versión 0.7.0, verificación, nota de la
guía, spec IMPLEMENTADA y docs. **Tras el PR 6:** tag `v0.7.0`.

## 7. Verificación a mano

Con `opencode-go`, en un directorio desechable y con `XDG_DATA_HOME` y
`XDG_STATE_HOME` desechables.

1. `maha --version` → `maha 0.7.0`.
2. Un turno con `glm-5.3-flash`: la línea de tokens tiene `(N reasoning)`,
   `$…` y `session $…`; el coste cuadra a mano con los precios de §1.1.
3. Una herramienta y otro turno: `/trace` enseña los dos turnos, con la
   herramienta y su duración.
4. La traza en disco (`0600`) no contiene la clave de `.env`; un `run_command`
   con `echo sk-inventada-1234567890` sale `[redacted]` en la traza y entero
   en la sesión.
5. `/model kimi-k3` y un turno: el coste usa los precios de Kimi.
6. `/model modelo-que-no-existe`: aviso de fuera del catálogo; el turno da
   el error del proveedor, y la traza apunta el `error`.
7. Ctrl+C a mitad: la traza apunta `interrupted`.
8. `/resume` de la sesión: `session $…` sigue sumando desde lo guardado.
9. `/delete` de otra sesión: desaparecen su sesión y su traza.
10. Con la carpeta de sesiones sin permiso de escritura: aviso en la
    terminal y una línea en `maha.log`, sin el texto de la conversación.

## 8. Lo que no viaja por git y lo que necesita la release

- Ninguna variable nueva. `PUESTA_EN_MARCHA` §3: las trazas en
  `~/.local/share/maha/traces/`, el registro en `~/.local/state/maha/` y el
  `models.toml` opcional del usuario.
- `docs/MAPA.md`: los ficheros de §3.1.
- `docs/DESIGN.md` §5, §6 y §11: corregidos en el mismo commit que esta spec,
  con fecha.

## 9. Guía

`docs/guia/07-observabilidad.md`, "Trazas y coste: lo que pasó y lo que
costó":
1. Qué es una traza y por qué no basta la sesión.
2. Tokens: entrada, caché, salida y razonamiento (lo que se factura).
3. El catálogo y sus fechas; el coste en Go (límite en dólares) y en Zen.
4. Sin credenciales: valores conocidos y patrones, y lo que no se cubre.
5. El registro de la aplicación: diagnóstico, nunca contenido.
6. "En la industria": la tabla de §2 y cómo encaja OpenTelemetry (hito 20).

## 10. Riesgos

**POR VERIFICAR:**
- ~~Si OpenCode manda `reasoning_tokens` también sin stream~~ Resuelto
  (§12.35): ya no los manda ni con stream.
- Qué campos de coste manda OpenCode Zen (pago por uso): no se pudo medir
  (la cuenta es de Go). Se leen en el orden de §1.5.

**Riesgos y contingencias:**
- **Precios desfasados:** cambian sin aviso. Van con fecha; el usuario los
  corrige en su `models.toml` sin esperar a una versión.
- **Un secreto con otra forma** llega a la traza: la traza es `0600` y
  local; el enmascarado reduce, no garantiza. La guía lo dice.
- **Trazas que crecen:** un registro por evento, sin el texto en trozos; una
  sesión larga son cientos de líneas. Sin rotación en este hito.
- **El coste de Go no es dinero que se paga** turno a turno: es lo que cuenta
  contra el límite. La guía y la nota de la terminal lo explican.

## 11. Decisiones

Del humano (2026-10-27, tras la auditoría): **el coste, primero el que da
el proveedor, y el del catálogo cuando no lo da** (opción A, recomendada por
el agente; la B era solo el catálogo). §1.5.

Del humano (2026-10-27, al empezar el PR 2), tras ver que la documentación
lista muchos más modelos que los cuatro de §1.3 y que varios tienen precios
por tramos: **el catálogo lleva todos los modelos de cada proveedor** ("si
eliges opencode go pues todas de ahí, si eliges zen pues todas de ahí, si
eliges anthropic pues todas de ahí") **y soporta tramos** (recomendación del
agente; las alternativas eran el precio del tramo alto o dejar fuera esos
modelos).

Del humano (2026-10-27): **acepta las cinco recomendaciones**, "si son las
decisiones más pro para el producto final". El agente las repasó con ese
criterio antes de aprobar:

1. Catálogo propio con fecha y otro del usuario que manda: el producto no
   depende de la red ni de una fuente ajena para decir lo que cuesta.
   Refrescar desde models.dev a una caché, a petición, queda como mejora
   posible si mantener los precios a mano pesa.
2. Coste en dólares: en OpenCode Go es la unidad del límite mensual, así
   que es lo que la persona necesita saber.
3. Sin `AgentError`: las excepciones son lo idiomático en Python; la traza
   las apunta igual, y el exportador del hito 20 las lleva al span.
4. Reintentos en el hito 8: imprescindibles en el producto final, pero son
   del adaptador y de los límites por turno, no de trazas y coste.
5. `/trace` dentro de `maha`, y `maha trace ID` con las opciones del hito 8.

Dudas que se plantearon al mantenedor (registro):

1. **El catálogo** (§1.3). Propuesta: un TOML propio en el paquete, con
   fecha, y otro opcional del usuario que manda. Alternativa: descargar
   models.dev al arrancar.
2. **El coste en OpenCode Go** (§1.5). Propuesta: enseñarlo en dólares, como
   lo que cuenta contra el límite mensual. Alternativa: no enseñar coste con
   una suscripción, solo tokens.
3. **Sin `AgentError`** (§1.6). Propuesta: los errores siguen siendo
   excepciones y la traza los apunta desde `Conversation`. Alternativa: un
   evento `AgentError` antes de la excepción.
4. **Reintentos ante 429 y 5xx** (§0). Propuesta: hito 8, con los límites
   por turno y el modo no interactivo. Alternativa: aquí.
5. **`/trace` dentro de `maha`** (§1.9). Propuesta: sí; `maha trace ID` desde
   la línea de comandos llega con las opciones del hito 8. Alternativa: solo
   el fichero y `jq`.

## 12. Aprendido al implementar

### PR 1 (`feature/hito-7-coste`, 2026-10-27)

1. **Qué cuenta `input_tokens`.** No estaba fijado para la caché escrita, y
   la fórmula de §1.5 la sumaba aparte sin restarla de la entrada. Se fija
   en el dominio: `input_tokens` cuenta todos los tokens del prompt, la
   caché leída y la escrita incluidas (como los cuenta OpenAI), y `cost()`
   resta las dos. El adaptador de Anthropic (hito 9), que las da aparte, las
   sumará al traducir. Hoy no cambia nada: el de OpenAI no lee la escrita.
2. **Sin precio de caché escrita**, se cobra como entrada, igual que la
   leída.
3. **El coste nunca es negativo:** si un proveedor manda más caché que
   entrada, la parte sin caché cuenta 0.
4. **Los tokens de razonamiento** se leen de `completion_tokens_details`,
   con stream y sin él (los trozos medidos en los hitos 3 y 4 ya los
   traían: 25 y 40). Sigue POR VERIFICAR que OpenCode los mande sin stream
   (§10).

### PR 2 (`feature/hito-7-catalogo`, 2026-10-27)

5. **Alcance ampliado por el mantenedor** al empezar el PR (§11): todos los
   modelos de cada proveedor y precios por tramos. Spec y DESIGN corregidos
   en su propio commit (`2f53ed7`).
6. **Las tablas, del HTML de la documentación**, no de un resumen: un
   resumen automático contó 37 modelos en Go porque tomaba cada tramo como
   un modelo. Son 30 en Go y 83 en Zen.
7. **models.dev, segunda fuente.** Cruzado modelo a modelo, solo difiere en
   dos sitios: DeepSeek V4.1 Flash y V4 Pro en Go (models.dev da el precio
   de valle; aquí va el de punta, §1.3) y MiniMax M3 en Go (models.dev le
   pone un tramo por encima de 512 000 tokens que la documentación no
   publica; manda la documentación). Jev 1.13 y Jev 1.13 Free no están en
   models.dev: van sin ventana de contexto.
8. **Los que entrenan con los datos**, de las secciones de privacidad: en
   Go, Muse Spark 1.3 y 1.2 Contributor e Iceman Contributor Free ("Model
   training: Yes"); en Zen, Big Pickle, Flint 40B Free y MiMo-V2.6-Flash
   Free ("collected data may be used to improve the model") y los tres
   Nemotron gratis ("logged … to improve NVIDIA products and services"),
   que se marcan por prudencia.
9. **Muchos modelos usan otra API** (Anthropic Messages, OpenAI Responses,
   Google): `maha` aún solo habla Chat Completions. Están en el catálogo
   igual; poder usarlos es otra pieza (el adaptador de Anthropic, hito 9).
10. **La fecha, por proveedor:** `[providers.<nombre>].checked`, y un modelo
    la puede cambiar con su propio `checked`. Un precio sin fecha es un
    error.
11. **El usuario sustituye modelos enteros**, no campos sueltos: su entrada
    es la que vale, sin heredar la ventana ni la caché del paquete.
12. **`models.toml` entra en el paquete** (`uv build`, comprobado a mano):
    `uv_build` incluye los ficheros que no son Python de la carpeta del
    módulo.

### PR 3 (`feature/hito-7-eventos`, 2026-10-27)

13. **El catálogo se carga ya en este PR**, no en el 5: el `Agent` lo
    necesita para calcular el coste. `config.user_catalog_path()`,
    `bootstrap` lo carga al arrancar y un `models.toml` del usuario roto no
    deja arrancar (como un `config.toml` roto). `conftest.py` aísla también
    `XDG_CONFIG_HOME`. Enseñarlo en la terminal sigue en el PR 5.
14. **El precio, por el modelo que contestó, y si el catálogo no conoce
    ese nombre, por el pedido.** Un proveedor puede devolver el modelo con
    otro nombre (una fecha, una versión); sin la vuelta atrás, ese turno se
    quedaría sin coste.
15. **Fallo encontrado y arreglado:** `Conversation` solo guardaba los
    tokens de un turno si acababa con `TurnFinished`. Un turno que llamaba
    al modelo y después fallaba (o se cortaba con Ctrl+C) no dejaba
    constancia de lo que ya se había pagado. Ahora el uso y el coste del
    turno salen de sus `ModelCallFinished`, y se guardan acabe como acabe.
16. **El coste de la sesión cuenta aparte los turnos sin precio**
    (`uncosted_turns`): una sesión del hito 6, o con un modelo fuera del
    catálogo, no hace que todo el coste desaparezca, pero tampoco lo deja
    pasar por completo. La terminal (PR 5) decide cómo decirlo.
17. **`Usd`:** el coste va en JSON como texto en notación normal
    (`"0.000000123"`), no como `float` (se redondea) ni como lo escribe
    `Decimal` por defecto (`"1.23E-7"`, difícil de leer con `jq`).

### PR 4 (`feature/hito-7-trazas`, 2026-10-27)

18. **El id fijo desde el principio necesitaba reservarse.** Antes, un
    choque al crear el fichero de sesión se arreglaba solo: el siguiente
    guardado probaba otro id. Con el id fijo, el reintento chocaría siempre.
    Es raro con una persona, pero no con los evals en paralelo del hito 8.
    Solución: la traza de una sesión nueva se crea en exclusiva
    (`open(new=True)`, `TraceExists`) y, si el id está tomado, se toma otro
    antes de escribir nada; si al guardar choca con una sesión sin traza
    (del hito 6), `SessionExists`, otro id, y la traza, que es solo suya, se
    mueve. `Conversation.exists` dice si el id ya es suyo; las
    comparaciones con "la sesión actual" (`/resume`, `/delete`, retomar sin
    id, `/trace` sin id) solo valen entonces. `Conversation.stored` dice si
    su fichero existe.
19. **La traza se cablea ya** en `bootstrap` (como el catálogo en el PR 3):
    `Sessions` la necesita. Enseñar su aviso y `/trace` en la terminal es
    del PR 5.
20. **Un secreto igual a un valor fijo** (`PASSWORD=tool_call`, que es el
    `type` de un bloque) deja un registro enmascarado inválido. Se pierde
    ese registro, con aviso; nunca el turno.
21. **gitleaks y los datos de prueba:** la clave PEM inventada de los tests
    se construye en tiempo de ejecución (`pem()`), en vez de marcar la
    línea para que gitleaks la ignore.
22. **`/trace` no cuenta como herramientas** las llamadas saltadas tras
    una denegación (`not run: a previous call was denied`): nunca se
    trataron. Las denegadas y las fallidas van aparte.
23. **Un turno sin `TurnFinished`** sale como `error`, `interrupted` o
    `unfinished` (maha murió o la traza falló al final).

### Auditoría antes del PR 5 (`fix/deuda-hito-7`, 2026-10-27)

Pedida por el mantenedor: dejar el hito sin deuda antes del hito 8. Dos
revisiones independientes del código del hito (sesiones y trazas; catálogo,
coste y bucle) y el repaso de los pendientes. Cada fallo, con su test
primero:

24. **Una traza con una línea cortada** (maha murió escribiendo) pegaba el
    siguiente registro a la media línea: se perdían los dos y `/trace`
    mezclaba dos turnos. Ahora, al abrir o tras un fallo que no se pudo
    recortar, se termina la línea antes de escribir.
25. **Reservar el id comprueba también las sesiones** (`SessionStore.exists`):
    un id que tiene una sesión sin traza (del hito 6) no se toma. Si aun así
    choca al guardar y la traza no se puede mover, se borra: nunca queda con
    el id de otra sesión. Con la comprobación, otro `maha` tampoco puede
    retomar esa sesión y escribir en nuestra traza.
26. **Nada se traza después de `TurnFinished`**: un fallo de la terminal al
    pintar el final ya no deja el turno como `interrupted`. `interrupted`
    pasa a decir "cortado antes de acabar": Ctrl+C, quien lo leía lo cerró
    o un tiempo límite (el hito 8 los tendrá).
27. **Enmascarado:** una clave PEM sin su `END` se tapa hasta el final del
    texto; los secretos conocidos se buscan también escapados como en JSON
    (`\"`, `\\`, `\/`, `\uXXXX`), y se preparan una vez (`Secrets`).
28. **Tokens negativos** de un proveedor cuentan como 0 (antes, coste
    negativo); `Usage` no admite negativos. El coste cero se escribe `"0"`,
    nunca `"-0"`.
29. **El catálogo del paquete ilegible** da `CatalogError`, no una traza.
    Los errores del catálogo dicen el tramo y citan la clave siempre entre
    comillas; se rechazan claves con espacios y precios escritos como texto.
    Un precio del usuario lleva su propia fecha (documentado y con test).
30. **`close()` nunca falla** en sesiones ni trazas: todo estaba ya
    sincronizado, y un `OSError` ahí cortaba el turno.
31. **`/delete` borra una traza que quedó sin su sesión** (guarda el primer
    mensaje), y **`/trace` de un id sin sesión ni traza** dice que no existe.
32. **Una traza que se abre a mitad de turno** (falló al abrir en
    `TurnStarted`) empieza igual con ese `TurnStarted`: `/trace` no esconde
    el turno.
33. **Limpiezas:** `add_cost()` en un solo sitio; `cost` sin valor por
    defecto en los eventos (olvidarlo ya no pasa en silencio); el precio
    recurre al modelo pedido también si el que contestó está sin precio;
    `ToolFinished.skipped` en vez de reconocer las llamadas saltadas por su
    texto; el fake de trazas falla y lee como el adaptador real.
34. **Pendiente de decisión del mantenedor:** si cinco ids seguidos chocan
    (mismo segundo y mismo token aleatorio de 16 bits cinco veces), los
    registros de ese turno anteriores a encontrar un id libre no se
    escriben y se avisa; la conversación sigue con un id nuevo y lo
    siguiente sí se traza. La alternativa es no poner tope a los intentos.
35. **POR VERIFICAR de §10, resuelto (2026-10-27):** OpenCode ya no manda
    `completion_tokens_details`, ni con stream ni sin él (en los hitos 3 y 4
    sí llegaba). Su propio `usage.opencode.tokens.reasoning` vale 0 aunque
    "OK" cueste 102 tokens de salida: el desglose "(N reasoning)" casi nunca
    saldrá con OpenCode. A cambio manda su coste: `usage.opencode.list_cost`
    coincide al dígito con el que calcula el catálogo (15 de entrada y 120 de
    salida con `glm-5.3-flash`: 0,00006225 $).
