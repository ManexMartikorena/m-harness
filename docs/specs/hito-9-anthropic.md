Estado: PROPUESTA (2026-11-03) → APROBADA (2026-11-03, por el humano: "el
camino más profesional y robusto para el producto" en cada duda, §11)

# Spec — Hito 9: Adaptador de Anthropic

Referencias: `docs/DESIGN.md` §5 (contrato de datos: `ReasoningBlock`,
`ModelRequest.max_tokens`), §6 (`ModelClient`, `ModelCatalog`), §7 y §7.1
(httpx a mano; configuración de proveedores) y §14 (hito 9 y P3);
`docs/COMPARATIVA.md` (formato de Anthropic, *effort*, caché del prompt);
specs 2 (§1.8, adaptador de OpenAI), 3 (§1.8 y §1.11, streaming), 4 (§1.3,
llamadas por `index`), 5 (§1.11, `refusal`), 6 (§1.7, marca de
interrupción), 7 (§1.2 a §1.5, uso, catálogo y coste) y 8 (§1.14,
reintentos); `AGENTS.md`.

## 0. Alcance

**El problema.** `maha` solo habla el formato de OpenAI (Chat Completions).
Los modelos Claude, y otros que los proveedores sirven con el formato de
Anthropic (MiniMax M3 o Qwen en OpenCode), no se pueden usar. Tampoco se
puede elegir cuánto razona el modelo (*effort*), ni se aprovecha la caché del
prompt de Anthropic, que abarata mucho un agente: cada paso reenvía toda la
conversación.

**Lo que hace este hito.** Un segundo adaptador, `AnthropicClient`, escrito a
mano como el de OpenAI. El formato pasa a ser **de cada modelo**: el catálogo
dice cuál habla, y `maha` elige el adaptador en cada llamada (también tras
`/model` o con el modelo de respaldo). El razonamiento del modelo se guarda y
se devuelve intacto, como pide Anthropic. Y en los dos formatos: el *effort*
(`effort` en la configuración, `--effort` y `/effort`) y la caché del prompt.

**Términos.**
- **Formato (API):** la forma del JSON que se manda y se recibe. Hoy,
  `openai-chat`; desde este hito, también `anthropic` (la Messages API).
- **Bloque de razonamiento (*thinking*):** lo que el modelo piensa antes de
  responder. Anthropic lo devuelve con una **firma** (*signature*), una
  copia cifrada que hay que reenviar intacta en el turno siguiente.
- **Effort:** cuánto se esfuerza el modelo (`low` a `max`). Más esfuerzo,
  más razonamiento, más tokens y más coste.
- **Caché del prompt:** el proveedor guarda el principio de la petición; si
  la siguiente empieza igual, lo cobra al 10 % (o menos) del precio.

Dentro de alcance:
- **El formato de cada modelo** (§1.1, §1.2): `api` y `max_output` en el
  catálogo; varios formatos por proveedor; un proveedor `anthropic` de serie;
  un error claro con los formatos que `maha` aún no habla.
- **`AnthropicClient`** (§1.3 a §1.6, §1.9): petición, streaming,
  `complete()`, uso de tokens, coste, motivos de parada y errores.
- **Razonamiento** (§1.5): `ReasoningBlock` y `ReasoningDelta` en el
  dominio, el orden de los bloques respetado y guardado en la sesión.
- **`max_tokens` por llamada** (§1.6): Anthropic lo exige.
- **Effort** (§1.7) en los dos formatos.
- **Caché del prompt** (§1.8).
- **Evals comparando proveedores** (§5): la batería con `claude-haiku-5-5`,
  y su primera línea base.
- Nota 09 de la guía: en qué se diferencian los dos formatos.

**Fuera de alcance** (y por qué):
- **Ver el texto del razonamiento:** hito 21 (TUI), ya asignado. Aquí se
  guarda y se devuelve, pero no se enseña (§1.5).
- **Las APIs Responses de OpenAI y de Google:** después de la 1.0
  (DESIGN §14). Aquí solo se reconocen, para dar un error claro (§1.2).
- **Imágenes y PDFs en el formato de Anthropic:** hito 20 (multimodal).
- **Herramientas de servidor** (búsqueda web de Anthropic, ejecución de
  código): hito 19 decide la web; `pause_turn` no puede llegar sin ellas.
- **Compactación en la API** y edición del contexto: hito 11 (contexto).
- **Entrar con la suscripción de Claude (Pro o Max):** Anthropic no lo
  permite a productos de terceros salvo aprobación (§1.0). Se usa con una
  clave de la API, creada en la Claude Console.
- **Respaldo de servidor ante un `refusal`** (`fallbacks` de Anthropic):
  `maha` ya tiene su modelo de respaldo (hito 8) para todos los
  proveedores; el de servidor es solo de la API directa de Anthropic.
- **`apply_patch`:** `docs/COMPARATIVA.md` lo dejaba "h9 o después"; es la
  herramienta de edición de los modelos de OpenAI con la API Responses
  (decisión 7).

## 1. Decisiones de fondo

### 1.0 Hechos comprobados (2026-11-03)

En la documentación oficial (Markdown de cada página) y con cuatro llamadas
reales a OpenCode Go (0,0005 $ en total):

- **Messages API** (https://platform.claude.com/docs/en/api/messages,
  `/build-with-claude/streaming`, `/api/versioning`): `POST /v1/messages`;
  cabeceras de la clave y `anthropic-version` (obligatoria; versiones
  `2023-06-01` y `2026-10-21`, la más reciente; `2026-10-21` quita
  `temperature`, `top_p` y `top_k`, que `maha` no manda). `max_tokens` es
  obligatorio. El system va aparte (`system`), no como mensaje.
- **Clave** (`/manage-claude/authentication`): se crea en la Claude Console
  (`platform.claude.com/settings/keys`) y se manda como `Authorization:
  Bearer <key>`; "the legacy `x-api-key` header is still supported".
- **Suscripción** (https://code.claude.com/docs/en/agent-sdk/overview):
  "Unless previously approved, Anthropic does not allow third party
  developers to offer claude.ai login or rate limits for their products".
  Un producto como `maha` no puede usar la suscripción Pro o Max: solo
  claves de la API.
- **Streaming:** eventos con nombre: `message_start` (con `usage`), por cada
  bloque `content_block_start`, `content_block_delta` y
  `content_block_stop`, uno o más `message_delta` (con `stop_reason` y el
  `usage` **acumulado**) y `message_stop`. También `ping` y `error`
  (`{"type": "error", "error": {"type": "overloaded_error", …}}`). "New
  event types may be added": lo desconocido se ignora. Sin `[DONE]`.
- **Deltas:** `text_delta` (`text`), `input_json_delta` (`partial_json`; el
  `content_block_start` de un `tool_use` trae `input: {}` y la primera
  delta puede ser `""`), `thinking_delta` (`thinking`) y `signature_delta`
  (`signature`, justo antes del `content_block_stop`).
- **Herramientas** (`/agents-and-tools/tool-use/handle-tool-calls`): se
  definen con `name`, `description` e `input_schema`; el modelo responde con
  bloques `tool_use` (`id`, `name`, `input`) y se contesta en un mensaje
  `user` con bloques `tool_result` (`tool_use_id`, `content`, `is_error`).
  Los `tool_result` van **primero** en ese mensaje; el texto, después.
- **Motivos de parada** (`/build-with-claude/handling-stop-reasons`):
  `end_turn`, `max_tokens`, `stop_sequence`, `tool_use`, `pause_turn` (solo
  con herramientas de servidor), `refusal` (HTTP 200, con `stop_details`:
  `category` y `explanation`) y `model_context_window_exceeded`.
- **Uso y caché** (`/build-with-claude/prompt-caching`): `input_tokens`
  cuenta **solo** lo que va después del último punto de caché; el total es
  `cache_read_input_tokens + cache_creation_input_tokens + input_tokens`.
  `cache_control: {"type": "ephemeral"}` arriba de la petición (caché
  automática) pone el punto en el último bloque, y avanza solo con la
  conversación. TTL de 5 minutos por defecto. Mínimo cacheable: 512 tokens
  en los modelos 5.x, 1.024 a 4.096 en otros; por debajo, sin error y sin
  caché. Precios: escribir, 1,25 × la entrada; leer, 0,1 × (0,05 × en Opus
  5.5 y Sonnet 5.5; 0,025 × en Fable 5.1).
- **Razonamiento** (`/build-with-claude/thinking`): bloques `thinking`
  (`thinking`, `signature`) y `redacted_thinking` (`data`). "When you return
  tool results, you must pass the thinking blocks from the assistant message
  back to the API, complete and unmodified." Desde Claude 5.1, un bloque
  solo vale si **todo lo anterior** (system, herramientas y mensajes) llega
  igual: "make your integration append-only". En Opus 5.5 y Fable 5.1 el
  razonamiento no se puede apagar; por defecto se devuelve vacío (`display:
  "omitted"`), con su firma.
- **Effort** (`/build-with-claude/effort`): `output_config.effort` =
  `low`, `medium`, `high`, `xhigh` o `max`; no todos los modelos admiten
  todos; sin valor, el del modelo (`medium` en Opus 5.5 y Haiku 5.5, `high`
  en el resto). En OpenAI (referencia de Chat Completions, en
  developers.openai.com): `reasoning_effort` = `none`, `minimal`, `low`,
  `medium`, `high`, `xhigh` o `max`, "not all reasoning models support every
  value".
- **Errores** (`/api/errors`): cuerpo `{"type": "error", "error": {"type",
  "message"}, "request_id"}`. 400, 401, 402 (`billing_error`), 403, 404,
  413, 429 (con `retry-after`, salvo el tope de gasto, que no lo lleva), 500,
  504 y **529** (`overloaded_error`).
- **Modelos y precios** (`/about-claude/models/overview`, `/pricing`):
  ids como `claude-opus-5-5`, `claude-sonnet-5-5` y `claude-haiku-5-5`;
  salida máxima de 128K en los actuales.
- **OpenCode** (https://opencode.ai/docs/go/ y `/zen/`): **un mismo
  proveedor sirve modelos con formatos distintos.** En Go,
  `claude-haiku-5-5`, `minimax-m3`, `qwen3.7-plus`, `qwen3.8-max` y
  `qwen3.8-flash` van a `https://opencode.ai/inference/go/anthropic/v1/messages`;
  la mayoría, a `…/go/openai/v1/chat/completions`; los GPT, a
  `…/openai/v1/responses`, y Gemini, a `…/google/v1beta/…`. En Zen, igual
  con `https://opencode.ai/inference/anthropic/v1/messages` (todos los
  Claude y varios Qwen).
- **Llamadas reales a OpenCode Go con `claude-haiku-5-5`:**
  - sin `x-opencode-session`, 400 `MissingSessionID`: hace falta la misma
    cabecera que en el formato de OpenAI;
  - con la clave en `x-api-key` o en `Authorization: Bearer`, la cabecera
    de sesión y `anthropic-version` igual a `2023-06-01` o `2026-10-21`:
    200;
  - el stream es el de la documentación; el `tool_use` trae además
    `"caller": {"type": "direct"}`;
  - la caché automática funciona: con un system de unos 2.500 tokens, la
    primera llamada escribe 2.546 (`cache_creation_input_tokens`) y la
    segunda los lee (`cache_read_input_tokens`); el coste baja de 0,00034 $
    a 0,00005 $;
  - el `usage` trae `output_tokens_details.thinking_tokens` y el coste de
    OpenCode (`cost`, `opencode.allowance` y `opencode.list_cost`), como en
    el formato de OpenAI;
  - `output_config.effort` se acepta; `reasoning_effort` también en
    `glm-5.3-flash` (formato OpenAI), pero no está claro que lo respete
    (con `low` gastó 212 tokens de razonamiento, con `max` 0): POR
    VERIFICAR en la verificación a mano.

### 1.1 El formato es de cada modelo

OpenCode sirve en un mismo proveedor modelos con formatos distintos (§1.0).
Así que el formato no puede ser solo del proveedor:

- **El catálogo** gana dos campos por modelo: `api` (`openai-chat`,
  `anthropic` o uno que `maha` aún no habla) y `max_output` (tokens de
  salida máximos). Así lo hace models.dev, del que ya salen las ventanas de
  contexto.
- **Un proveedor** declara un formato por defecto (`api`) y, si sirve
  varios, una URL por formato (`endpoints`). El formato de un modelo es el
  del catálogo; si el catálogo no lo conoce, el del proveedor.

```toml
# ~/.config/maha/config.toml: un servidor propio de un solo formato
[providers.local]
api = "anthropic"
base_url = "http://localhost:4000/v1"
api_key_env = "MY_KEY"
```

```python
# De serie (config.py)
"opencode-go": ProviderSettings(
    api="openai-chat",
    base_url="https://opencode.ai/inference/go/openai/v1",
    endpoints={"anthropic": "https://opencode.ai/inference/go/anthropic/v1"},
    api_key_env="OPENCODE_API_KEY",
    session_header="x-opencode-session",
),
"anthropic": ProviderSettings(
    api="anthropic",
    base_url="https://api.anthropic.com/v1",
    api_key_env="ANTHROPIC_API_KEY",
),
```

- **Proveedor `anthropic` de serie**, la API directa, con sus modelos y
  precios en el catálogo (comprobados el 2026-11-03). Quien paga en la
  Claude Console crea una clave, la pone en `ANTHROPIC_API_KEY` y usa
  `provider = "anthropic"`.
- Un `.maha/config.toml` sigue sin poder declarar proveedores (spec 2,
  §1.10): tampoco `endpoints`.

*Alternativa descartada:* dos proveedores por cada uno de OpenCode
(`opencode-go` y `opencode-go-anthropic`). La persona tendría que saber qué
formato habla cada modelo, y `/model claude-haiku-5-5` fallaría sin
explicación en uno de los dos.

### 1.2 Un cliente por formato, elegido en cada llamada

`/model` y el modelo de respaldo pueden cambiar de formato a mitad de
sesión. Por eso no basta un cliente por sesión:

- **`ModelRouter`** (`application/routing.py`) cumple el puerto
  `ModelClient` y reparte cada `ModelRequest` al cliente del formato de su
  modelo. Vive en `application`: solo conoce el puerto, y ningún adaptador
  importa a otro.
- `bootstrap.py` crea los clientes que el proveedor puede usar (uno por
  formato) y el router con el formato de cada modelo.
- **Un formato que `maha` no habla** (`openai-responses`, `google`…) da un
  error claro antes de llamar, en vez de un 400 del proveedor:

```
error: gpt-6-luna uses the openai-responses API, which maha does not speak yet
```

  Es un `ModelRequestError`: no se reintenta, y el respaldo (si es de otro
  formato) sí puede responder.

### 1.3 La petición

Del `ModelRequest` al JSON de Anthropic (`adapters/models/anthropic.py`):

```json
{
  "model": "claude-haiku-5-5",
  "max_tokens": 128000,
  "system": "…",
  "tools": [{"name": "read_file", "description": "…", "input_schema": {…}}],
  "messages": [
    {"role": "user", "content": [{"type": "text", "text": "Lee notas.txt"}]},
    {"role": "assistant", "content": [
      {"type": "thinking", "thinking": "", "signature": "Eq…"},
      {"type": "tool_use", "id": "toolu_1", "name": "read_file", "input": {"path": "notas.txt"}}
    ]},
    {"role": "user", "content": [
      {"type": "tool_result", "tool_use_id": "toolu_1", "content": "uno\ndos"}
    ]}
  ],
  "cache_control": {"type": "ephemeral"},
  "output_config": {"effort": "medium"},
  "stream": true
}
```

- **Cabeceras:** `Authorization: Bearer <clave>` (la forma actual; funciona
  en la API directa y en OpenCode, §1.0), `anthropic-version: 2026-10-21`
  (la más reciente, que Anthropic recomienda; cada proveedor puede fijar
  otra con `anthropic_version`, para servidores que solo conozcan
  `2023-06-01`; decisión 2),
  `content-type`, el `User-Agent` de `maha` y la cabecera de sesión del
  proveedor si la declara (OpenCode la exige, §1.0).
- **Mensajes `tool`:** pasan a `user` con un `tool_result` por resultado,
  con `is_error`. Si les sigue un mensaje de la persona (tras una
  denegación), se unen en un solo `user`: primero los `tool_result`, luego
  el texto.
- **`ToolCallBlock.arguments`** es texto JSON (spec 4, §1.2); Anthropic pide
  un objeto en `input`. Si el texto no es un objeto JSON (el modelo lo
  escribió mal y su error ya está en el historial), va `{}`: el
  `tool_result` con el error explica lo que pasó.
- **Bloques de razonamiento** (§1.5): van tal cual, en su sitio. Uno sin
  firma (cortado con Ctrl+C antes de llegar) no se manda: Anthropic lo
  rechazaría.
- **Texto vacío:** un bloque de texto vacío no se manda.
- **Mensaje interrumpido** (spec 6, §1.7): se añade la marca
  `[interrupted by the user]` como bloque de texto final, como en OpenAI.
- **Sin** `temperature`, `top_p`, `top_k`, `tool_choice` ni `thinking`: el
  modelo usa los suyos. En Opus 5.5 y Fable 5.1 un `tool_choice` forzado o
  `thinking: disabled` dan 400 (§1.0).

### 1.4 La respuesta en streaming

Cada evento de Anthropic, a los `ModelEvent` del dominio:

| Anthropic | `maha` |
|---|---|
| `message_start` | se guardan `model` y el `usage` inicial |
| `content_block_start` de `text` | nada (el texto llega en las deltas) |
| `text_delta` | `TextDelta(text, block=index)` |
| `content_block_start` de `tool_use` | `ToolCallDelta(index, id, name)` |
| `input_json_delta` | `ToolCallDelta(index, arguments=partial_json)` |
| `thinking_delta`, `signature_delta` | `ReasoningDelta(index, text o signature)` |
| `content_block_start` de `redacted_thinking` | `ReasoningDelta(index, redacted=data)` |
| `message_delta` | se guardan `stop_reason` y el `usage` acumulado |
| `message_stop` | `MessageEnd(stop_reason, usage, model, cost)` |
| `ping` y tipos desconocidos | se ignoran |
| `error` | `ModelUnavailableError` (o `ModelRateLimitError` si es `rate_limit_error`) |

- **Uso:** `input_tokens` del dominio es la suma de los tres de Anthropic,
  porque el dominio cuenta el prompt entero, como OpenAI (spec 7, §1.2), y
  así el coste y los tramos de precio (Haiku 5.5 sube por encima de 100.000
  tokens "including cache reads and cache writes") salen bien.
  `cache_read_tokens` y `cache_write_tokens`, los de Anthropic;
  `reasoning_tokens`, `output_tokens_details.thinking_tokens`.
- **Coste:** el del proveedor si lo da (`opencode.allowance`, `list_cost` o
  `cost`, la misma regla que en OpenAI, spec 7, §1.5); si no, el del
  catálogo.
- **Una llamada sin argumentos:** si no llega ninguna `input_json_delta`,
  los argumentos son `{}`.
- **Fin sin `message_stop`** o sin `stop_reason`: `ModelResponseError`
  ("stream ended before the answer was complete"), como en OpenAI.
- **Silencio:** los mismos 120 s sin datos que en OpenAI (spec 8, §12.9);
  los `ping` no cuentan como progreso.
- La lectura de SSE (`adapters/models/sse.py`) se comparte; el decodificador
  de UTF-8 incremental, también.

**Motivos de parada:**

| Anthropic | `maha` |
|---|---|
| `end_turn` | `end_turn` |
| `tool_use` | `tool_use` |
| `max_tokens`, `model_context_window_exceeded` | `max_tokens` |
| `refusal` | `content_filter` |
| `stop_sequence`, `pause_turn`, otros | `other` |

- **`refusal`:** si la respuesta no trae texto, el `explanation` de
  `stop_details` llega como `TextDelta`: la persona tiene que ver por qué
  (spec 5, §1.11).

### 1.5 El razonamiento, guardado y devuelto intacto

Anthropic exige devolver los bloques de razonamiento **intactos y en su
sitio**, y desde Claude 5.1 comprueba que todo lo anterior llegue igual
(§1.0). Hoy el acumulador junta todo el texto delante y las llamadas
detrás: con razonamiento intercalado, eso es "editar" el turno y el modelo
pierde lo que pensó. Por eso:

- **Dominio** (`domain/messages.py`, `domain/events.py`), como ya preveía
  DESIGN §5:

```python
class ReasoningBlock(BaseModel, frozen=True):
    type: Literal["reasoning"] = "reasoning"
    text: str = ""  # vacío con display "omitted"
    signature: str | None = None
    redacted: str | None = None  # el `data` de un redacted_thinking


class ReasoningDelta(BaseModel, frozen=True):
    type: Literal["reasoning_delta"] = "reasoning_delta"
    index: int
    text: str = ""
    signature: str | None = None
    redacted: str | None = None
```

- **`TextDelta` gana `block: int | None`:** el índice del bloque, en
  Anthropic; `None` en OpenAI, que no tiene bloques. El acumulador
  (`application/collect.py`) crea los bloques **en el orden en que
  aparecen**, uno por índice. Con OpenAI el resultado es el de hoy: un
  texto y después las llamadas.
- **Se guarda en la sesión**, como cualquier bloque. Una sesión de antes se
  lee igual. Una sesión con razonamiento no se lee con una versión de
  `maha` anterior a esta: no se promete compatibilidad hacia atrás.
- **El adaptador de OpenAI** no manda los bloques de razonamiento: su
  formato no los tiene. Tras un `/model` de Claude a GLM y vuelta, Claude
  recibe los suyos; los de otro modelo que no sepa leer los descarta la API
  sin cobrarlos (§1.0).
- **No se enseña:** el texto llega vacío por defecto, y verlo es el hito 21.
  No se traza (como `TextDelta`); `/export` en Markdown no lo incluye.
- **Una regla nueva del bucle, fijada con un test:** lo que se manda al
  modelo solo crece por el final. El system, las herramientas y los
  mensajes anteriores no cambian dentro de una sesión. Hoy ya es así; el
  test lo protege para los hitos 10 (system por capas) y 11 (compactación).

### 1.6 `max_tokens` en cada llamada

Anthropic exige `max_tokens`, y un valor mayor que la salida máxima del
modelo da 400. Hasta ahora `ModelRequest` no lo llevaba (DESIGN §5, lo
aplazaba al hito 11):

- `ModelRequest.max_tokens: int | None`. El bucle pone el `max_output` del
  catálogo; sin él, `None`.
- **Todo modelo de formato `anthropic` del catálogo de serie lleva
  `max_output`**, y un test lo exige (decisión 5).
- `AnthropicClient` manda ese valor. Solo si es `None` (un modelo que añadió
  la persona sin `max_output`) manda **32.000**; si el modelo admite menos,
  el error del proveedor lo dice y se corrige en `models.toml`. Es un techo,
  no un gasto: se paga lo que se genera.
- `OpenAIChatClient` no lo manda, como hoy: los servidores compatibles
  tienen su propio tope, y cambiarlo ahora sería un cambio de
  comportamiento sin necesidad.
- Si el modelo llega al techo, la parada es `max_tokens`, como ya se trata.

### 1.7 Effort

- **Configuración:** `effort = "low" | "medium" | "high" | "xhigh" | "max"`
  en `config.toml`, del usuario o del proyecto (como `model`); `--effort` en
  la línea de comandos; y `/effort [NIVEL]` en la conversación (sin nivel,
  enseña el actual; `/effort default` vuelve al del modelo). Sin valor
  (por defecto), no se manda nada: el modelo usa el suyo, el que su
  proveedor calibra para él (decisión 4). Las evals miden si otro defecto
  mejora (§5).
- **En el dominio:** `ModelRequest.effort`. Anthropic lo manda como
  `output_config.effort`; OpenAI, como `reasoning_effort`.
- Son los cinco niveles que admiten los dos formatos (§1.0). Un modelo que
  no admite un nivel responde 400, y el error del proveedor lo dice.
- Cambiar el effort a mitad de sesión invalida la caché del prompt de
  Anthropic (§1.8): se avisa en la ayuda de `/effort`.

### 1.8 Caché del prompt

- **Anthropic:** `cache_control: {"type": "ephemeral"}` arriba de cada
  petición (caché automática).
- **Duración (`cache_ttl`):** `5m` por defecto, o `1h` en la configuración
  (decisión 9). Con `5m`, escribir cuesta 1,25 × y la caché aguanta entre
  pasos del agente, pero caduca si la persona se para más de 5 minutos; con
  `1h`, escribir cuesta 2 × y aguanta las pausas de una conversación. La
  guía y el README lo explican con números. El punto de caché
  avanza solo con la conversación: cada paso lee lo que escribió el
  anterior. Comprobado por OpenCode (§1.0). Como la petición solo crece por
  el final (§1.5), la caché se aprovecha entera.
- **OpenAI:** la caché es automática en el servidor; `maha` ya lee
  `cached_tokens` y `cache_write_tokens` (spec 7). No cambia nada.
- **El coste** ya distingue lectura y escritura con los precios del
  catálogo (`cache_read`, `cache_write`); faltaba que alguien escribiera.
- La línea de tokens y `/trace` enseñan la caché como hoy.

### 1.9 Errores

Como en el adaptador de OpenAI, con los códigos de Anthropic:

| HTTP | Error de `maha` | ¿Se reintenta? (spec 8) |
|---|---|---|
| 401, 403 | `ModelAuthError` | no |
| 429 | `ModelRateLimitError` con `retry-after` | sí |
| 500, 504, 529 y otros ≥ 500 | `ModelUnavailableError` con `retry-after` | sí |
| 400, 402, 404, 413 y otros 4xx | `ModelRequestError` | no |

- El mensaje es `error.message` del cuerpo, sin la clave y recortado (las
  mismas reglas de seguridad que en OpenAI: el cuerpo es entrada no
  confiable).
- Un 200 que no es `text/event-stream` en streaming: `ModelResponseError`.
- `retry_after()` y la limpieza del mensaje se sacan de `openai_chat.py` a
  un módulo común (`adapters/models/http.py`), para no repetirlos: los
  adaptadores no se importan entre sí.

### 1.10 `complete()`

`complete()` (sin streaming) también existe en este adaptador, como pide el
puerto: el mismo JSON sin `stream`, y la respuesta entera traducida con las
mismas reglas de bloques, uso, coste y parada.

## 2. En la industria

- **SDK oficial `anthropic`** (Python): cliente con tipos, streaming,
  reintentos (2 por defecto, respetando `retry-after`) y ayudas como
  `get_final_message()`. Es lo normal en un producto: aquí el adaptador es
  a mano a propósito (DESIGN §7.1), para ver el JSON que viaja.
- **LiteLLM** y el **AI SDK de Vercel** (`@ai-sdk/anthropic`, el que usa
  OpenCode): una interfaz para muchos proveedores; traducen entre formatos
  como `maha` entre su dominio y cada API.
- **models.dev:** dice el formato de cada modelo (el paquete del AI SDK que
  lo sirve) y sus límites; `maha` copia esa idea en su catálogo.
- **Claude Code** solo habla el formato de Anthropic y tiene `/effort`;
  **OpenCode** habla los dos y llama a sus niveles "variantes".
- **Caché automática** con un solo `cache_control` arriba: la forma más
  simple que documenta Anthropic. Los productos grandes suelen poner además
  puntos fijos (herramientas y system) para conversaciones muy largas.

## 3. Diseño de detalle

### 3.1 Ficheros

| Fichero | Capa | Qué |
|---|---|---|
| `domain/messages.py` | domain | `ReasoningBlock` en `Block` |
| `domain/events.py` | domain | `ReasoningDelta`; `TextDelta.block` |
| `domain/model.py` | domain | `ModelRequest.max_tokens` y `effort`; `Effort` |
| `domain/catalog.py` | domain | `ModelInfo.api` y `max_output`; `Api` |
| `application/collect.py` | application | bloques en orden de aparición, con razonamiento |
| `application/routing.py` | application | `ModelRouter` (nuevo) |
| `application/agent.py` | application | `max_tokens` del catálogo y `effort` en cada petición |
| `application/sessions.py` | application | `effort` de la conversación y su cambio |
| `adapters/models/http.py` | adapters | `retry_after()`, mensaje seguro, texto UTF-8 (sacado de `openai_chat.py`) |
| `adapters/models/anthropic.py` | adapters | `AnthropicClient` (nuevo) |
| `adapters/models/openai_chat.py` | adapters | `reasoning_effort`; sin bloques de razonamiento |
| `adapters/catalog/models.toml` | adapters | `api` y `max_output`; proveedor `anthropic` |
| `adapters/catalog/toml_catalog.py` | adapters | leer `api` y `max_output` |
| `adapters/cli/*` | adapters | `--effort`, `/effort`, ayuda |
| `config.py` | — | `ProviderSettings.api`, `endpoints` y `anthropic_version`; `effort` y `cache_ttl`; proveedor `anthropic` |
| `bootstrap.py` | — | un cliente por formato y el router |

### 3.2 Configuración nueva

```toml
# ~/.config/maha/config.toml o .maha/config.toml
effort = "high"   # low | medium | high | xhigh | max; sin él, el del modelo
cache_ttl = "1h"  # 5m (por defecto) | 1h: caché del prompt de Anthropic

# solo en el del usuario
[providers.mio]
api = "anthropic"            # openai-chat (por defecto) | anthropic
base_url = "https://…/v1"
anthropic_version = "2023-06-01"  # opcional; por defecto, 2026-10-21
[providers.mio.endpoints]    # opcional: otra URL para otro formato
openai-chat = "https://…/openai/v1"
```

Variable nueva, opcional: `ANTHROPIC_API_KEY`, solo para el proveedor
`anthropic` (`.env.example` y `PUESTA_EN_MARCHA`).

### 3.3 Catálogo

```toml
[models."opencode-go/claude-haiku-5-5"]
api = "anthropic"
context = 1_000_000
max_output = 128_000
input = 0.10
# …

[providers.anthropic]
checked = 2026-11-03
source = "https://platform.claude.com/docs/en/about-claude/pricing"
```

- `api` para cada modelo de OpenCode que no sea `openai-chat`, según sus
  páginas (§1.0); `max_output` de models.dev, el mismo día.
- Los modelos del proveedor `anthropic`: los actuales y los antiguos que
  siguen disponibles, con los precios de la página oficial.
- `maha models` enseña el formato de cada modelo.

## 4. Plan de tests

Todo con fakes y respuestas HTTP simuladas (respx); ninguna llamada real.

1. **Catálogo y configuración:** `api` y `max_output` leídos; todo modelo
   `anthropic` del catálogo de serie tiene `max_output`; un modelo sin
   `api` toma el del proveedor; `cache_ttl` y `anthropic_version`; `endpoints` en el usuario sí y en el
   proyecto no; `effort` válido e inválido; el proveedor `anthropic` de
   serie pide `ANTHROPIC_API_KEY`.
2. **`ModelRouter`:** cada petición va al cliente de su formato; un cambio
   de modelo cambia de cliente; un formato sin cliente da el error claro
   (§1.2) y no llama a nadie.
3. **Acumulador:** con OpenAI, el mismo mensaje de hoy (test existente);
   con bloques de Anthropic (razonamiento, texto, llamada, razonamiento,
   llamada), el mismo orden; la firma y `redacted` se juntan en su bloque.
4. **Petición de Anthropic** (el JSON exacto): system aparte; `tool` a
   `user` con `tool_result` e `is_error`; resultados más texto de la
   persona en un solo `user`, resultados primero; argumentos inválidos como
   `{}`; razonamiento en su sitio y sin el que no tiene firma; texto vacío
   fuera; marca de interrupción; `max_tokens` del catálogo o 32.000;
   `effort`; `cache_control` con su TTL; cabeceras (Bearer, versión por
   defecto y la del proveedor, sesión).
5. **Stream de Anthropic** (SSE simulado, con eventos copiados de la
   documentación y de las llamadas reales de §1.0): texto, llamada con
   argumentos en trozos, llamada sin argumentos, razonamiento con firma,
   `redacted_thinking`, `ping`, evento desconocido, `error` a mitad,
   `rate_limit_error` a mitad, fin sin `message_stop`, silencio de 120 s.
6. **Uso y coste:** los tres `input_tokens` sumados; caché y razonamiento;
   el coste de OpenCode gana al del catálogo; sin él, el del catálogo con
   los precios de caché.
7. **Motivos de parada:** cada uno de §1.4; `refusal` sin texto da el
   `explanation`.
8. **Errores HTTP:** cada fila de §1.9, con `retry-after` en segundos y en
   fecha; el mensaje sin la clave; un 200 que no es SSE.
9. **`complete()`:** la misma traducción sin stream.
10. **OpenAI:** `reasoning_effort` con `effort`; sin él, no se manda; los
    bloques de razonamiento no se mandan.
11. **Sesión:** un mensaje con razonamiento se guarda y se retoma igual; una
    sesión de antes se lee.
12. **Solo crece por el final** (§1.5): en un turno con varios pasos, cada
    petición empieza exactamente por la anterior (system, herramientas y
    mensajes).
13. **Effort en la interfaz:** `--effort`, `/effort`, `/effort default` y
    la ayuda; con `-p`.
14. **De punta a punta** (`bootstrap`): con un proveedor de dos formatos,
    un turno con un modelo `anthropic` y otro con uno `openai-chat`, cada
    uno a su URL.

## 5. Evals

Toca el bucle (acumulador, petición) y añade un formato. Antes del merge:

- **Sin regresión** en los modelos de la línea base (`glm-5.3-flash` y
  `kimi-k2.7-code`, 5 repeticiones), contra la del 2026-10-27. Con OpenAI
  la petición no cambia salvo `effort` (que no se manda por defecto), así
  que se espera lo mismo.
- **Comparar proveedores:** la batería con `claude-haiku-5-5` (OpenCode Go,
  formato `anthropic`), 5 repeticiones, y su primera línea base
  (`--save`), decisión 8. Se miran éxito, pasos, coste por ejecución y
  tokens de caché leídos.
- **Effort con datos** (decisión 4): la misma batería con
  `claude-haiku-5-5` y `--effort high`, comparada con su defecto. Si `high`
  mejora el éxito sin disparar el coste, se propone al mantenedor como
  defecto para ese modelo.
- Coste estimado: unos 0,90 $ en total.

El resultado se anota aquí al implementar.

## 6. Orden de piezas para el implementador

Cada punto, un commit en verde. Tres PRs y el de cierre, en el milestone
"Hito 9".

**PR 1 — El formato de cada modelo** (`feature/hito-9-formatos`)
1. `Api` y `ModelInfo.api` y `max_output`; leerlos del TOML. *Commit:*
   "Guardar en el catálogo el formato y la salida máxima de cada modelo"
2. `api` y `max_output` de los modelos de OpenCode en `models.toml`.
3. `ProviderSettings.api` y `endpoints`, de serie para OpenCode.
4. `ModelRouter` y el error de formato no soportado.
5. Cableado en `bootstrap.py`: un cliente por formato (hoy, solo OpenAI).
6. `maha models` enseña el formato.

**PR 2 — Razonamiento, `max_tokens` y effort en el núcleo**
(`feature/hito-9-nucleo`)
7. `ReasoningBlock`, `ReasoningDelta` y `TextDelta.block`.
8. El acumulador por bloques, en orden.
9. `ModelRequest.max_tokens` y `effort`; el bucle los rellena.
10. El test de "solo crece por el final".
11. `adapters/models/http.py` (sacado de `openai_chat.py`, sin cambio).
12. OpenAI: `reasoning_effort` y sin razonamiento.
13. `effort` en la configuración, `--effort` y `/effort`.

**PR 3 — `AnthropicClient`** (`feature/hito-9-anthropic`)
14. La petición (tests 4).
15. El stream (tests 5 a 7).
16. Los errores (tests 8).
17. `complete()`.
18. Proveedor `anthropic` de serie y sus modelos en el catálogo.
19. Cableado: el cliente de Anthropic en el router; prueba de punta a punta.
20. Evals (§5), anotadas aquí.

**Cierre** (`feature/hito-9-cierre`): verificación a mano, nota 09 de la
guía, los dos README, PROYECTO, ESTADO, HISTORIAL, MAPA, versión `0.9.0`.

## 7. Verificación a mano

Con OpenCode Go, en un directorio desechable:

1. `maha -m claude-haiku-5-5`: dos turnos; la línea de tokens enseña la
   caché leída desde el segundo paso.
2. Pedir que lea y edite un fichero: pide permiso, edita, y el modelo sigue
   en el mismo turno con el resultado (razonamiento devuelto bien: sin 400).
3. Ctrl+C a mitad de una respuesta y seguir: sin error.
4. `/model glm-5.3-flash` y vuelta a `claude-haiku-5-5` en la misma sesión;
   `maha -c` retoma con el razonamiento guardado.
5. `/effort low` y `/effort`; `maha -p "…" --effort high --output-format
   json`; comprobar si GLM respeta el effort (POR VERIFICAR de §1.0).
6. `maha -m minimax-m3` (formato `anthropic`, no Claude).
7. `maha -m gpt-6-luna`: el error claro de §1.2.
8. `/trace` y `maha stats`: el coste cuadra con el de OpenCode.
9. Si hay `ANTHROPIC_API_KEY` (decisión 1): un turno con el proveedor
   `anthropic`.

## 8. Lo que no viaja por git y lo que necesita la release

- `ANTHROPIC_API_KEY`, opcional: `.env.example` y `PUESTA_EN_MARCHA` §2.
- Nada para la release: el formato de OpenCode llega de serie.
- `docs/MAPA.md`: `application/routing.py`, `adapters/models/anthropic.py`
  y `adapters/models/http.py`, con sus tests.

## 9. Guía

Nota 09: **"Dos formatos para hablar con un modelo"**.
- En qué se diferencian OpenAI y Anthropic: el system, los mensajes hechos
  de bloques, los resultados de herramientas, el streaming por bloques y el
  uso de tokens (con un ejemplo de JSON de cada uno).
- Por qué el formato es de cada modelo y no del proveedor.
- El razonamiento con firma: por qué se devuelve intacto y qué significa
  "solo crece por el final".
- La caché del prompt y el effort: qué ahorran y qué cuestan, con los
  números de las evals.

## 10. Riesgos

- **Los servidores intermedios** (OpenCode) pueden comportarse distinto de
  la API directa: el error a mitad de stream, la caché o el razonamiento.
  Se mitiga con la verificación a mano y los POR VERIFICAR.
- **Razonamiento invalidado:** si algún hito cambia lo ya enviado (system
  que cambia, compactación), el modelo pierde lo pensado y, en cuentas
  nuevas, la API puede dar 400. El test de §1.5 lo vigila; los hitos 10 y
  11 lo tienen que respetar.
- **`max_output` mal en el catálogo:** un 400 del proveedor que lo dice. Se
  corrige en el catálogo del usuario.
- **Sesiones con razonamiento** no se leen con versiones anteriores de
  `maha` (§1.5).
- **El tope de gasto de Anthropic** da 429 sin `retry-after`: se reintenta
  tres veces y falla igual (unos 7 s de espera). Aceptable; el mensaje del
  proveedor lo explica.

## 11. Decisiones

Del humano (2026-11-03): "lo que estamos construyendo es un producto
robusto, serio y competitivo": en cada duda, el camino más profesional y
robusto para el producto. Con ese criterio, el agente cambió tres de sus
recomendaciones (2, 5 y 9):

1. **Proveedor `anthropic` de serie**, aunque no haya clave para probarlo
   ahora: se prueba con respx, la verificación real va por OpenCode Go
   (`claude-haiku-5-5`) y la de la API directa queda POR VERIFICAR hasta
   que haya clave.
2. **Versión `2026-10-21`** por defecto (la recomendada), con
   `anthropic_version` por proveedor para servidores que solo conozcan
   `2023-06-01`. *(Antes se proponía `2023-06-01` por compatibilidad: era
   lo cómodo, no lo robusto.)*
3. **`/effort` en la conversación**, además de `effort` y `--effort`.
4. **Effort por defecto: el de cada modelo**, calibrado por su proveedor;
   forzar uno global rompe los modelos que no lo admiten. Las evals miden
   `high` frente al defecto en `claude-haiku-5-5` (§5).
5. **`max_output` obligatorio** en los modelos `anthropic` del catálogo de
   serie, con su test; 32.000 solo para modelos añadidos por la persona.
   *(Antes: 32.000 para cualquier modelo sin dato.)*
6. **Ver el razonamiento, en el hito 21.** Pedir su resumen ahora
   (`display`) enciende el razonamiento en Opus 4.7 y 4.8 y da error en
   Haiku 4.5; se decide con la pantalla que lo enseña.
7. **`apply_patch` fuera de este hito:** va con la API Responses de OpenAI,
   después de la 1.0 (`docs/COMPARATIVA.md`, corregido en este PR).
8. **Línea base de `claude-haiku-5-5`**, para comparar proveedores.
9. **`cache_ttl` configurable**, `5m` por defecto y `1h` para
   conversaciones con pausas largas. *(Antes: 5 minutos fijos.)*

## 12. Aprendido al implementar

(Se añade al implementar.)
