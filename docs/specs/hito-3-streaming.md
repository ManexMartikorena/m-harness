Estado: PROPUESTA (2026-10-20)

# Spec — Hito 3: Streaming

Referencias: `docs/DESIGN.md` §3, §5 (`ModelEvent`), §6 (puerto `ModelClient`),
§7 y §14 (hito 3); spec del hito 2 (§1.3, §1.7, §1.8, §1.9, §10, §12); `AGENTS.md`.

## 0. Alcance

**El problema.** Hoy `maha` espera la respuesta entera y la imprime de golpe:
con una respuesta larga, la terminal queda en blanco hasta 120 s, y Ctrl+C
mata el programa.

**Lo que hace este cambio.** `maha` imprime la respuesta token a token según
llega. Ctrl+C a mitad de respuesta corta esa respuesta y vuelve al prompt. El
puerto `ModelClient` pasa a ser `stream()`, que devuelve eventos.

Dentro de alcance:
- Tipos del dominio `TextDelta`, `MessageEnd` y `ModelEvent` (§1.4).
- Puerto `ModelClient.stream()`; `complete()` sale del puerto (§1.2).
- Analizador de SSE propio (*Server-Sent Events*: el formato de streaming
  sobre HTTP), en el adaptador (§1.3).
- `OpenAIChatClient.stream()` con errores a mitad de stream y tiempos (§1.8).
- `FakeModelClient` que emite eventos; `Chat` que los reenvía (§1.6).
- Terminal en directo y Ctrl+C por respuesta (§1.10).
- Una sonda manual contra el proveedor real (§1.7).
- Nota 03 de la guía y docs al día.

**Fuera de alcance** (y por qué):
- Herramientas (`ToolCallDelta`): hito 4. Aquí no se envían `tools`.
- `ReasoningDelta`/`ReasoningBlock`: no se sabe qué campo usa
  `glm-5.3-flash` (§1.7). Se ignoran; decide el mantenedor tras la sonda.
- Desglose de tokens (razonamiento, caché, coste): hito 7.
- Reintentos (§1.9), límite de tokens de salida y de tiempo total del turno
  (hitos 4 y 11), guardar el texto parcial de una respuesta cancelada
  (hito 6) y Rich/prompt_toolkit (hito 19).

## 1. Decisiones de fondo

### 1.1 Hechos comprobados

Todos el 2026-10-20. Los marca "agente" quien los comprobó: el agente de la
sesión en la documentación oficial (salvo Context7, indicado). Lo no
comprobado es **POR VERIFICAR** y está en §10.

- **OpenAI, streaming** (Context7; https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create
  y https://developers.openai.com/api/reference/resources/chat/subresources/completions/streaming-events):
  - `stream: true` da SSE y acaba con `data: [DONE]`. Cada trozo es un
    `chat.completion.chunk` con `model`, `choices[]` y `usage` (null salvo en
    el último). `choices[0].delta` lleva `role` y `content` (que puede venir
    vacío); `finish_reason` es null hasta el final.
  - `stream_options.include_usage`: añade un trozo **antes de `[DONE]`**, con
    `choices` vacío y el `usage` de toda la petición. Si el stream se
    interrumpe, puede no llegar.
  - `usage.completion_tokens_details.reasoning_tokens` existe. El `delta`
    oficial **no** documenta `reasoning_content`. Cada trozo trae un campo
    `obfuscation` (relleno), que se ignora.
- **httpx 0.28.1** (Context7): `client.stream()` cierra la respuesta en un
  `finally`, también ante `CancelledError`; `aiter_bytes()` existe; el timeout
  `read` mide el silencio entre trozos y no hay timeout total;
  `DecodingError` cuelga de `RequestError`, como `TransportError` (agente,
  `httpx/_exceptions.py` instalado). `httpx.MockTransport` admite un
  manejador `async`.
- **respx 0.23.1** (Context7): `return_value` y `side_effect`.
- **SSE, WHATWG** (https://html.spec.whatwg.org/multipage/server-sent-events.html,
  agente): reglas en §1.3.
- **`aiter_lines()` de httpx 0.28.1**
  (https://github.com/encode/httpx/blob/0.28.1/httpx/_decoders.py, agente):
  parte con `str.splitlines()`. Detalle y consecuencia en §1.3.
- **OpenCode Go** (https://opencode.ai/docs/go/, agente):
  `https://opencode.ai/inference/go/openai/v1/chat/completions`, con
  `glm-5.3-flash` y la cabecera `x-opencode-session`. **Zen**
  (https://opencode.ai/docs/zen/, agente):
  `https://opencode.ai/inference/openai/v1/chat/completions`. Los dos coinciden
  con `config.py`. (Context7 dio una URL `/zen/go/v1/...`: desfasada.) Las dos
  páginas **no mencionan** streaming, `stream_options`, `usage` en el stream ni
  razonamiento: lo resuelve la sonda.
- **Dato propio, 2026-10-20** (Ubuntu de casa, `glm-5.3-flash`, OpenCode Go, sin
  streaming): "Hola, responde solo con la palabra OK." → "OK",
  `[tokens: 22 in · 67 out]`. En el hito 2, 142 de salida para una frase (spec 2,
  §12.12). Causa desconocida (§1.7).

### 1.2 `complete()` sale del puerto; se deriva de `stream()`

**Dónde:** `ports/model.py` y `application/collect.py`.

```python
class ModelClient(Protocol):
    def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]: ...
```

Quien necesita la respuesta entera (evals del hito 8, resúmenes del 11,
subagentes) usa `await collect(client.stream(request))` (§1.5).

- **Por qué:** es lo que dice DESIGN §6; una sola ruta de código por adaptador
  (los hitos 4 y 9 no la duplican); lo que se prueba es lo que se usa.
- **Descartado:** mantener `complete()` junto a `stream()` (doble superficie en
  cada adaptador y fake, sin ganancia); borrarlo sin `collect()` (cada
  consumidor reescribiría el acumulador).
- **Sintaxis:** en el `Protocol`, `stream` va con `def`, no `async def`. Un
  generador asíncrono (`async def` con `yield`) devuelve el iterador
  directamente; un `async def` declarado sería una corrutina que *devuelve* un
  iterador, y mypy las ve distintas.

### 1.3 SSE a mano, sin librería

**Dónde:** `adapters/models/sse.py` (`parse_sse`) y el decodificador en
`adapters/models/openai_chat.py`.

- **Por qué a mano:** AGENTS.md pide a mano lo que es del agente, y el cliente
  del modelo es una pieza de ANALISIS §5. El formato es pequeño (~40 líneas) y
  es lo que la guía quiere enseñar.
- **Reglas del estándar** (WHATWG, §1.1) que implementa `parse_sse`:
  1. Las líneas acaban en CRLF, LF o CR (CR = `\r`, LF = `\n`) y **solo en
     esos**.
  2. Una línea vacía despacha el evento. **Si no hubo ninguna línea `data`
     desde el último despacho, no se despacha nada** (un comentario seguido de
     línea en blanco, dos líneas en blanco, un `event:` suelto).
  3. Cada `data` añade su valor más LF al búfer; al despachar se quita el LF
     final, así que varias líneas `data:` quedan unidas por LF. Una línea
     `data:` o `data` (sin dos puntos) es un `data` con valor vacío: despacha
     un evento con dato vacío.
  4. Una línea que empieza por `:` es un comentario (los *keep-alive*). Se
     ignora. `event:`, `id:` y `retry:` también.
  5. Tras los dos puntos se quita **un solo** espacio, si lo hay.
  6. Al acabar el stream, **lo pendiente se descarta**. Antes, un `\r` retenido
     al final se procesa como terminador de línea (puede despachar); lo que
     quede sin despachar, se pierde. Si el último trozo del servidor (el del
     `finish_reason`) llega sin línea en blanco final, se pierde y el adaptador
     falla con `ModelResponseError` (§1.8). Mejor un error claro que adivinar.
- **BOM** (*byte order mark*: los bytes `EF BB BF` que algunos programas ponen
  al principio de un fichero UTF-8): el estándar manda quitarlo. **Lo hace
  solo el decodificador del adaptador, no `parse_sse`** (un único sitio).
- **Forma:**

  ```python
  async def parse_sse(chunks: AsyncIterator[str]) -> AsyncIterator[str]:
      """Yield the data of each event. `chunks` is decoded text, any size."""
  ```

  Parte las líneas **él mismo** y guarda lo que no ha acabado. Un `\r` al final
  de un trozo espera al siguiente: si empieza por `\n`, es un CRLF y no dos
  saltos. Función pura sobre un iterador: se prueba sin red.
- **Tope de tamaño:** si una línea sin terminar o el dato de un evento pasan de
  1 MiB (1 048 576 caracteres), `parse_sse` lanza `ModelResponseError`. Un trozo
  real mide cientos de bytes (con herramientas, decenas de KB: hito 4); 1 MiB
  deja margen y acota la memoria ante un servidor roto u hostil. Un tope de
  salida total es del hito 4/11.
- **Decodificación:** `response.aiter_bytes()` más
  `codecs.getincrementaldecoder("utf-8-sig")(errors="replace")` (biblioteca
  estándar): no corta un carácter UTF-8 repartido entre dos trozos de red y
  quita el BOM inicial.
- **Descartado `aiter_lines()`:** parte con `str.splitlines()` en `\n`, `\r`,
  VT, FF, FS, GS, RS, NEL (U+0085), U+2028 y U+2029, más que SSE. Un JSON con
  U+2028, U+2029 o U+0085 crudos dentro de un string (válido sin escapar)
  partiría una línea `data:` y el trozo no validaría: fallo silencioso que
  solo sale con ciertos textos.
- **Descartado `aiter_text()`:** serviría, pero no está comprobado en la
  documentación; el decodificador estándar da lo mismo y lo controlamos. Si el
  implementador lo comprueba y lo prefiere, el diseño no cambia: `parse_sse`
  recibe texto.
- `[DONE]` es un dato más: lo interpreta el adaptador, no el analizador.

```
data: {"choices":[{"index":0,"delta":{"content":"Ho"}}]}

data: {"choices":[{"index":0,"delta":{"content":"la"}}]}

data: [DONE]
```

(Abreviado; datos inventados.)

### 1.4 Tipos del dominio

**Dónde:** `domain/events.py`.

```python
class TextDelta(BaseModel, frozen=True):
    type: Literal["text_delta"] = "text_delta"
    text: str


class MessageEnd(BaseModel, frozen=True):
    type: Literal["message_end"] = "message_end"
    stop_reason: StopReason
    usage: Usage
    model: str  # as the provider names it


type ModelEvent = TextDelta | MessageEnd
```

- **`MessageEnd` lleva `model`:** `ModelResponse.model` es obligatorio y solo
  llega en los trozos. Corrige DESIGN §5 (anotado). El adaptador usa
  `model or request.model` si el proveedor no lo manda (como spec 2, §12.4).
- **`MessageEnd` sale una vez, al final:** el `finish_reason` llega en un
  trozo y el `usage` en otro posterior (§1.1); `MessageEnd` junta los dos.
- **Es una unión de tipos, no una unión discriminada de Pydantic:** nada valida
  eventos desde JSON. `type` queda para las trazas del hito 7; si entonces
  se leen del disco, se añade `Field(discriminator="type")`.
- `TextDelta` es el mismo tipo que listará `AgentEvent` (DESIGN §5).

### 1.5 `collect()` y el acumulador

**Dónde:** `application/collect.py`.

```python
class Accumulator:
    def add(self, event: ModelEvent) -> None: ...
    def response(self) -> ModelResponse: ...  # ModelResponseError sin MessageEnd


async def collect(events: AsyncIterator[ModelEvent]) -> ModelResponse: ...
```

Junta los `TextDelta` en un `TextBlock` y toma `stop_reason`, `usage` y
`model` de `MessageEnd`. Va en `application` (lógica de caso de uso) y solo usa
tipos del dominio.

### 1.6 `Chat.stream()`: reenvía y guarda el turno

**Dónde:** `application/chat.py`.

`Chat.stream(text)` es un generador asíncrono:
1. arma la lista nueva (historial + mensaje del usuario);
2. recorre `client.stream(request)`, mete cada evento en un `Accumulator` y lo
   entrega a quien llama;
3. **al recibir `MessageEnd`, guarda el turno en el historial y solo después
   cede el `MessageEnd`**. Así el turno queda guardado aunque quien llama cierre
   el generador al verlo.

Si falla o se cancela antes de `MessageEnd`, no se guarda nada (mecanismo del
hito 2, spec 2 §12.2). Quien lo consume lo cierra con `contextlib.aclosing`.

- **Consecuencia aceptada:** tras un Ctrl+C, el texto ya impreso sigue en
  pantalla, pero el modelo no lo recuerda: el turno se repite. Guardar el
  parcial, marcado como cortado, es del hito 6.
  - Descartado guardarlo ya: un mensaje del asistente cortado y sin
    `stop_reason` real confunde al modelo, y la forma correcta es un diseño de
    sesiones.
- `Chat.send()` (hito 2) se queda solo mientras la terminal lo use; se borra
  en la misma pieza que cambia la terminal a `stream()` (§6, pieza 12).

### 1.7 Tokens de salida altos de `glm-5.3-flash`: se mide aquí, se resuelve en el hito 7

**Se sabe:** 67 tokens de salida para "OK", 142 para una frase (§1.1). **No se
sabe por qué.** "Probablemente razonamiento" (spec 2 §12.12) es una hipótesis.

**Se mide en este hito** con una sonda manual, fuera del repositorio (pieza 1;
prompt inventado, nunca la clave en la salida):
1. Petición con `stream: true` y `stream_options.include_usage`; volcado de los
   trozos crudos.
2. Claves de `delta` además de `content` y `role`. Z.ai documenta
   `delta.reasoning_content` (https://docs.z.ai/guides/capabilities/thinking-mode,
   agente, 2026-10-20) y otros hosts usan `reasoning`; **qué usa OpenCode Go
   no está verificado**. Cuántos trozos de razonamiento hay y cuánto tarda el
   primer `content`.
3. El `usage` completo del último trozo, con `completion_tokens_details`.
4. Si acepta `stream_options` (400, o lo ignora y no manda `usage`).
5. `Content-Type`, `Content-Encoding`, terminador de línea (`\n` o `\r\n`), si
   hay `[DONE]`, el orden `finish_reason` → `usage` → `[DONE]`, si el último
   evento acaba con línea en blanco y si hay comentarios `:` de *keep-alive*.
6. Un error en mitad del stream, si se puede provocar.
7. La misma pregunta **sin** streaming, para comparar `completion_tokens`.

El resultado va a §12, con fecha, sin ids ni claves.

**En el código:** `Usage` no cambia (`output_tokens` = `completion_tokens`, lo
que se factura). Los campos de razonamiento se ignoran. Si la sonda muestra
razonamiento visible o un silencio largo, el mantenedor decide (§11, duda 2).
**Hito 7:** `Usage.reasoning_tokens`, su coste y el catálogo de precios.

### 1.8 Errores, tiempos límite

**Dónde:** `adapters/models/openai_chat.py`. Sin tipos nuevos: los cinco
errores del hito 2 (spec 2, §1.7).

| Situación | Error |
|---|---|
| HTTP no 2xx antes del primer trozo | Como en el hito 2 (401/403 auth, 429 límite, otro 4xx petición, 5xx no disponible). Se lee el cuerpo (`aread()`) para sacar `error.message` |
| 200 con `Content-Type` JSON | Se intenta leer `error.message` (tapado y recortado como en el hito 2); `ModelResponseError` con ese mensaje, o "the provider did not stream" si no hay |
| 200 con otro `Content-Type` que no empieza por `text/event-stream` | `ModelResponseError` ("the provider did not stream") |
| `data:` que no es JSON ni `[DONE]`, o trozo que no valida | `ModelResponseError`, sin copiar el cuerpo (entrada no confiable) |
| Trozo con objeto `error` (formato **POR VERIFICAR**) | `ModelUnavailableError`, mensaje tapado y recortado |
| Fallo de red o de lectura (`httpx.RequestError`: corte, `ReadError`, `ReadTimeout`, `DecodingError`) | `ModelUnavailableError`. **Siempre falla, también si ya llegó el `finish_reason`** |
| Cierre limpio del stream sin `[DONE]` **y con** `finish_reason` | Válido (algunos servidores no mandan `[DONE]`) |
| Cierre limpio sin `finish_reason` (con o sin `[DONE]`) | `ModelResponseError` ("stream ended before the answer was complete") |
| Datos después de `[DONE]` | Se deja de leer y se cierra la conexión |

- Se captura `httpx.RequestError`, no solo `TransportError`: `DecodingError`
  (cuerpo mal comprimido) es hermana de esta (§1.1).
- Un error a mitad de stream es un `ModelError` más: `Chat` no guarda el turno
  y la terminal lo muestra y sigue (§1.10).
- La clave se tapa antes de recortar (spec 2, §12.3) en todo mensaje del
  proveedor.
- **Tiempos (cambian respecto al hito 2**, `Timeout(120.0, connect=10.0)`**):**
  `Timeout(connect=10, read=120, write=10, pool=10)`. `read` es el silencio
  máximo entre trozos (§1.1), no el tiempo de la respuesta: 120 s cubren un
  modelo que razona un rato antes del primer token, y una respuesta larga que
  sigue llegando no se corta. Sin tiempo total del turno (httpx no lo ofrece;
  es un límite del bucle, hito 4). Ctrl+C es la salida.

### 1.9 Reintentos: siguen sin hacerse

**Dónde:** no aplica (decisión de no construir).

Una respuesta empezada no se puede reintentar sin repetir texto ya impreso.
Solo se podría antes del primer trozo (429 y 5xx de arranque), que con una
persona delante se repiten a mano. Se valorará en el hito 8 (evals sin
persona) o en el 7 (con datos de fallos).

### 1.10 Terminal: texto en directo y Ctrl+C solo corta la respuesta

**Dónde:** `adapters/cli/conversation.py`.

```
maha 0.3.0 · opencode-go · glm-5.3-flash · /exit to quit
> Cuéntame un chiste corto
Un programador va al médico…          ← cada trozo se imprime al llegar
  [tokens: 18 in · 31 out]
> Cuéntame otro
Otro chiste, que se corta aq^C
  [interrupted]
> /exit
```

- Cada `TextDelta` se escribe en `out` con `flush`. Con `MessageEnd`, un salto
  de línea y la línea de tokens.
- **Si `usage` es todo ceros, no se imprime la línea de tokens** (0 no es un
  dato: es "desconocido"). Enlaza con la duda 5 de §11.
- **Error a mitad de stream:** se escribe `\n` en `out` (si ya se imprimió
  texto), luego `error: …` en stderr; el texto impreso se queda.
- **Ctrl+C con respuesta en curso:** corta la petición HTTP, escribe un salto
  de línea y `  [interrupted]`, y vuelve al prompt. El turno no se guarda.
- **Ctrl+C en el prompt:** sale con 130, como en el hito 2.
  - **Cambia el hito 2** (spec 2, §1.11 y §7.8), donde siempre salía.
    Descartado seguir saliendo siempre: no sería cancelar, sería cerrar.
- **Cómo, sin tarea hija:** SIGINT (la señal que manda Ctrl+C) sigue cancelando
  la tarea principal, como en el hito 2. `_turns` marca `in_turn = True` solo
  mientras consume `Chat.stream()`; si la cancelación llega con `in_turn`, la
  captura, llama a `task.uncancel()` (para que `asyncio` no siga cancelando),
  imprime `[interrupted]` y sigue; fuera de un turno, propaga y `converse`
  sale con 130. **Elegida sobre una tarea hija por turno:** una tarea menos y
  el mismo patrón (`uncancel()`) que ya tiene el hito 2. La hija obligaría a
  distinguir `task.cancelled()` de una cancelación externa al esperarla.
  - *Cancelación en `asyncio`:* `task.cancel()` lanza `CancelledError` en el
    siguiente `await` de la tarea; httpx cierra la conexión en su `finally`.

### 1.11 Petición y traducción de los trozos

**Dónde:** `adapters/models/openai_chat.py`.

`POST {base_url}/chat/completions`, como en el hito 2, más dos campos:

```json
{"model": "glm-5.3-flash",
 "messages": [{"role": "user", "content": "Hola"}],
 "stream": true,
 "stream_options": {"include_usage": true}}
```

- `include_usage` porque sin él no llega `usage` en el stream (§1.1). Si
  OpenCode no lo acepta: §10.
- Las cabeceras no cambian. No se añade `Accept`: ningún hecho comprobado lo
  pide.
- Se usa `client.stream("POST", "chat/completions", json=...)`.
- Solo se lee `choices[0]` (`maha` no pide `n`):

  | Trozo | El adaptador |
  |---|---|
  | `delta.content` no vacío | emite `TextDelta` |
  | `content` vacío/null, `role`, `obfuscation`, otros campos | ignora |
  | `finish_reason` no null | lo guarda (mapa del hito 2: `stop` → `end_turn`…) |
  | `usage` no null (`choices` vacío) | lo guarda |
  | `model` | lo guarda |
  | `[DONE]` o cierre limpio | emite `MessageEnd` y termina (reglas de §1.8) |

## 2. En la industria

| Pieza | M-Harness | Alternativas | Cuándo se elegirían |
|---|---|---|---|
| Streaming del modelo | httpx + SSE a mano | SDK oficial del proveedor (p. ej. `openai`); LiteLLM | SDK: un solo proveedor y prisa. LiteLLM: muchos proveedores sin escribir adaptadores |
| Analizador SSE | A mano (~40 líneas) | Librerías de SSE de terceros | Cuando haga falta reconexión o `Last-Event-ID` |
| Eventos del modelo | Unión de tipos propios | Los tipos del SDK de cada proveedor | Cuando no se piensa cambiar de proveedor |
| Cancelación | `Task.cancel()` desde SIGINT | `KeyboardInterrupt` en código síncrono | Código síncrono |
| Tokens en streaming | `stream_options.include_usage` | Contar con un tokenizador | Cuando el proveedor no informa de `usage` |
| Tests de streaming | respx con respuestas SSE simuladas | Servidor local de pruebas; VCR.py | Fijar respuestas reales |

*Solo se citan categorías y herramientas; no se afirma el comportamiento de
ningún producto concreto.*

## 3. Diseño de detalle

### 3.1 Ficheros

```
src/mharness/
├── domain/events.py               # nuevo: TextDelta, MessageEnd, ModelEvent
├── ports/model.py                 # stream(); complete() fuera al final
├── application/collect.py         # nuevo: Accumulator, collect()
├── application/chat.py            # Chat.stream(); send() fuera
└── adapters/
    ├── models/sse.py              # nuevo: parse_sse()
    ├── models/openai_chat.py      # stream(); complete() fuera al final
    └── cli/conversation.py        # deltas en directo; Ctrl+C por respuesta
tests/
├── fakes/model.py                 # emite eventos; reply(), HANG, Gate
├── fixtures/openai_chat/          # streams SSE de ejemplo (datos inventados)
├── unit/                          # test_events, test_collect, test_chat, test_fake_model
└── adapters/                      # test_sse, test_openai_chat, test_conversation
docs/guia/03-streaming.md
```

### 3.2 `FakeModelClient`

```python
gate = Gate()  # a pause the test releases
fake = FakeModelClient(
    [
        reply("Hola, Ane."),  # TextDelta(s) + MessageEnd
        [TextDelta(text="Hol"), ModelUnavailableError("cut")],  # error mid-stream
        [
            TextDelta(text="Uno"),
            gate,
            TextDelta(text="Dos"),
            end,
        ],  # pause in the middle
        [TextDelta(text="Esperando"), HANG],  # waits forever, for Ctrl+C
    ]
)
gate.release()  # from the test
```

- Cada paso es una lista de eventos. Una excepción en la lista se lanza en ese
  punto. `Gate` espera hasta que el test llama a `release()` (un
  `asyncio.Event`): permite comprobar que el texto sale **antes** de acabar el
  stream. `HANG` espera para siempre, hasta que lo cancelan.
- `reply(text, chunks=2)` parte el texto en `TextDelta` y añade el
  `MessageEnd`. Guion agotado → `AssertionError`.
- Mientras convivan `complete()` y `stream()` (§6, piezas 10 a 13), un paso
  `ModelResponse` también vale para `stream()` (se emite como eventos).

### 3.3 Configuración nueva

Ninguna. Los tiempos son constantes del adaptador (§1.8).

## 4. Plan de tests

Sin llamadas reales ni red. La numeración es `4.N.M`; las piezas (§6) la citan.

**4.1 Eventos** (`tests/unit/test_events.py`)
1. Son inmutables. 2. `type` toma su valor por defecto.

**4.2 `collect()`** (`tests/unit/test_collect.py`)
1. Junta los `TextDelta` en un bloque. 2. Toma `stop_reason`, `usage` y `model`
de `MessageEnd`. 3. Sin texto: mensaje sin bloques. 4. Sin `MessageEnd` →
`ModelResponseError`.

**4.3 SSE** (`tests/adapters/test_sse.py`), con trozos de texto en una lista
1. Un evento por línea en blanco; varias `data:` se unen con LF.
2. Comentarios `:`, `event:`, `id:` y `retry:` se ignoran.
3. Se quita un solo espacio tras `data:`. `data:` y `data` (sin dos puntos)
   despachan un evento con dato vacío.
4. Sin línea `data` no se despacha: comentario + línea en blanco; dos líneas en
   blanco; `event:` suelto.
5. Saltos `\n`, `\r\n` y `\r` sueltos.
6. `\r` al final de un trozo y `\n` al principio del siguiente: un solo salto.
7. Una línea cortada entre dos trozos sale entera.
8. **Un `data:` con U+2028, U+2029 y U+0085 crudos dentro del string JSON sale
   entero, en una sola línea de dato.** Fija la decisión de no usar
   `aiter_lines()`. El test los construye con `chr(0x2028)` (y los otros dos)
   para que este fichero no lleve los caracteres crudos.
9. Fin sin línea en blanco: el evento pendiente se descarta.
10. Fin en `data: x\r\r` → se despacha `x` (el `\r` retenido es un terminador);
    fin en `data: x\r` → no se despacha nada.
11. Una línea sin terminar o un evento de más de 1 MiB → `ModelResponseError`.

**4.4 Adaptador, stream** (`tests/adapters/test_openai_chat.py`), con respx y
`tests/fixtures/openai_chat/`
1. El JSON lleva `stream: true` y `stream_options.include_usage`, con y sin
   `system` (**migra el test de `_to_openai` del hito 2**). Fija §1.11.
2. Cabeceras: `Authorization`, `User-Agent`, la de sesión; sin clave no hay
   `Authorization` (**migra el del hito 2**).
3. Un stream normal: `TextDelta` en orden y un solo `MessageEnd` al final.
4. El trozo de `usage` con `choices: []` llega después del `finish_reason`, y
   `MessageEnd` lleva los dos. Fija §1.4.
5. `content` vacío o null, `role`, `obfuscation` y campos desconocidos
   (`reasoning_content`…) se ignoran.
6. Sin `usage` → `Usage()`. Sin `model` → el de la petición.
7. Cada `finish_reason`: `stop`, `length`, `tool_calls`, `content_filter`, otro.
8. Un BOM inicial se ignora, y un carácter UTF-8 de varios bytes repartido
   entre dos trozos de bytes llega entero.
9. `[DONE]` sin ningún `finish_reason` → `ModelResponseError`.
10. Sin `[DONE]` y con `finish_reason`: correcto. Sin `[DONE]` ni
    `finish_reason`: `ModelResponseError`.
11. Datos después de `[DONE]`: se ignoran y se cierra la conexión.
12. 401, 403, 429, 400, 404, 500 y 503 antes del stream → su error, con el
    `message` del proveedor, la clave tapada y el recorte a 300 (**migra los
    del hito 2**).
13. 200 con `Content-Type` JSON y `error.message` → `ModelResponseError` con
    ese mensaje (tapado y recortado); sin mensaje, o con otro tipo,
    "did not stream".
14. Trozo que no es JSON o no valida → `ModelResponseError`, sin copiar el
    cuerpo.
15. Trozo con objeto `error` → `ModelUnavailableError`, mensaje tapado y
    recortado.
16. Corte a mitad de cuerpo, `ReadTimeout` y `DecodingError` →
    `ModelUnavailableError`, también si ya llegó el `finish_reason`.
17. La clave nunca aparece en un error del stream.
18. Al cancelar o cerrar el consumidor, la respuesta HTTP se cierra: el cuerpo
    del test es un `httpx.AsyncByteStream` propio con una bandera `closed` que
    se comprueba al final (**POR VERIFICAR** que respx lo admite; mismo
    hallazgo que el de la pieza 7, §10).

**4.5 `FakeModelClient`** (`tests/unit/test_fake_model.py`)
1. Emite el guion en orden. 2. Lanza el error en su sitio, tras los eventos
previos. 3. `Gate` espera hasta `release()`; `HANG` espera y se cancela.
4. Guarda las peticiones. 5. Falla al agotarse.

**4.6 `Chat`** (`tests/unit/test_chat.py`), con el fake
1. Entrega los eventos en directo, uno a uno.
2. Tras `MessageEnd`, el historial tiene usuario + asistente, y la segunda
   llamada lleva los tres mensajes (mantiene spec 2, §1.4).
3. Un error a mitad de stream sube y la conversación queda como estaba.
4. Cancelar a mitad (con `HANG`) deja la conversación como estaba. Fija §1.6.
5. Tras recibir `MessageEnd` y cerrar el generador, el turno ya está
   guardado. Fija §1.6.

**4.7 Terminal** (`tests/adapters/test_conversation.py`)
1. Con un `Gate`, el primer `TextDelta` está en `out` **antes** de liberar el
   resto del stream.
2. Línea de tokens al final; sin ella si `usage` es todo ceros; `/exit` y
   Ctrl+D como antes.
3. Error a mitad de stream: el texto impreso se queda, se escribe `\n` en `out`
   y el error va a stderr; la conversación sigue.
4. Ctrl+C con la respuesta en curso (`HANG`): `[interrupted]`, no sale, y el
   siguiente turno funciona. Fija §1.10.
5. Ctrl+C en el prompt: sale con 130.

**4.8 De punta a punta** (`tests/test_bootstrap.py`): `main()` con
configuración temporal, respx que sirve un SSE y entrada guionizada. Dos
turnos; el segundo envía el historial. Y un stream cortado: el error sale por
stderr y el turno siguiente funciona.

**4.9 Arquitectura:** el test de imports del núcleo sigue igual (httpx solo en
el adaptador); `domain/events.py` solo usa la biblioteca estándar y Pydantic.

**Cómo se simula un stream con respx.** Un cuerpo SSE en bytes basta para
casi todo (`httpx.Response(200, headers={"content-type": "text/event-stream"},
content=b"data: ...\n\n...")`). Los cortes a mitad de cuerpo son **POR
VERIFICAR**. **Hipótesis (no hecho) a probar primero en la pieza 7:**
`httpx.Response(200, content=<generador asíncrono que entrega trozos y luego
lanza httpx.ReadError>)`. Plan B, comprobado en la documentación de httpx: un
`httpx.MockTransport` con manejador `async`, inyectado por un parámetro
opcional `transport` del constructor (solo para tests).

## 5. Evals

No aplica (nacen en el hito 8). No cambian prompts, skills, herramientas,
contexto ni memoria: cambia el transporte de la respuesta, no lo que dice el
modelo.

## 6. Orden de piezas para el implementador

Cada punto es un commit, con lo que exista hasta entonces en verde. El
adaptador gana `stream()` **antes** de que el puerto lo exija (PR 2), para que
cada commit pase mypy.

**PR 1** (`feature/hito-3-eventos`): núcleo y analizador, sin red.
1. **Sonda** (§1.7), fuera del repositorio, con la clave del `.env`. El
   resultado se pega en §12. Si contradice §1.8 o §1.11, se corrige la spec y
   se avisa al mantenedor **antes de seguir**.
   *Commit:* "Anotar en la spec el resultado de la sonda de streaming"
2. **Eventos.** `domain/events.py`; tests 4.1.
   *Commit:* "Añadir los eventos del modelo"
3. **Respuesta desde eventos.** `application/collect.py`; tests 4.2.
   *Commit:* "Añadir collect(), que construye la respuesta desde los eventos"
4. **SSE.** `adapters/models/sse.py`; tests 4.3.
   *Commit:* "Añadir el analizador de eventos SSE"
5. **Mapa.** *Commit:* "Actualizar el mapa con los eventos y el analizador SSE"

**PR 2** (`feature/hito-3-adaptador`): `stream()` en el adaptador.
6. **Petición y texto.** Petición de §1.11, decodificador, traducción de
   `content`, `finish_reason`, `usage` y `model`; fixtures; tests 4.4.1 a 4.4.8.
   *Commit:* "Emitir el texto de la respuesta en streaming"
7. **Errores.** Tabla de §1.8; tests 4.4.9 a 4.4.17. Empieza por el hallazgo de
   respx de §4.
   *Commit:* "Traducir los errores del stream a errores del modelo"
8. **Cierre de la conexión.** Test 4.4.18.
   *Commit:* "Cerrar la conexión al cancelar el stream"
9. **Mapa.** *Commit:* "Actualizar el mapa con el streaming del adaptador"

**PR 3** (`feature/hito-3-terminal`): puerto, `Chat`, terminal, limpieza.
10. **Puerto y fake.** `stream()` entra en el `Protocol` junto a `complete()`;
    el fake emite eventos (`Gate`, `HANG`); tests 4.5.
    *Commit:* "Añadir stream() al puerto ModelClient y al fake"
11. **`Chat.stream()`.** `Chat.send()` sigue; tests 4.6.
    *Commit:* "Añadir Chat.stream(), que guarda el turno al terminar"
12. **Terminal en directo.** `converse()` usa `Chat.stream()`; se borra
    `Chat.send()` (la producción ya no lo usa) y sus tests se adaptan aquí;
    tests 4.7.1 a 4.7.3.
    *Commit:* "Mostrar la respuesta según llega"
13. **Ctrl+C por respuesta.** §1.10; tests 4.7.4 y 4.7.5.
    *Commit:* "Cancelar solo la respuesta con Ctrl+C"
14. **Quitar `complete()`** del puerto, del fake y del adaptador. Los tests del
    hito 2 de `complete()` **ya están migrados a `stream()`** (4.4.1, 4.4.2 y
    4.4.12); solo se borran los que no tienen equivalente en streaming (la
    traducción de una respuesta entera).
    *Commit:* "Quitar complete(), ya derivado de stream()"
15. **Punta a punta.** Tests 4.8; `bootstrap` no cambia salvo que haga falta.
    *Commit:* "Probar el streaming de punta a punta"
16. **Mapa.** *Commit:* "Actualizar el mapa con la terminal en streaming"

**PR 4** (`feature/hito-3-cierre`): cierre.
17. **Versión.** `uv version --bump minor` → `0.3.0`.
    *Commit:* "Subir la versión a 0.3.0"
18. **Guía.** `docs/guia/03-streaming.md` y su fila en el índice.
    *Commit:* "Añadir la nota de la guía sobre streaming"
19. **Cierre de la spec.** IMPLEMENTADA y §12.
    *Commit:* "Cerrar la spec del hito 3"
20. **Documentación al día.** README, MAPA y ESTADO.
    *Commit:* "Actualizar la documentación al cerrar el hito 3"

**Tras el PR 4:** tag `v0.3.0` sobre el merge commit y push del tag.

## 7. Verificación a mano

Con `opencode-go` y `glm-5.3-flash`.

1. `uv run maha --version` → `maha 0.3.0`.
2. `uv run --env-file .env maha` con una pregunta de respuesta larga: el texto
   **aparece mientras se escribe**. Se anota el tiempo hasta el primer trozo.
3. La línea de tokens coincide con la de la sonda para el mismo prompt. Si no
   sale línea (ceros), `stream_options` no funciona (§10).
4. Dos turnos: el segundo recuerda al primero y los tokens de entrada crecen.
5. Ctrl+C a mitad de una respuesta larga: `[interrupted]`, vuelve el prompt, el
   proceso sigue. Un turno nuevo funciona; el modelo **no** recuerda la
   respuesta cortada (§1.6). Se prueba también en una terminal simulada (pty:
   un pseudo-terminal creado por el test), por el fallo del hito 2 (spec 2,
   §12.6).
6. Ctrl+C en el prompt, `/exit` y Ctrl+D: `echo $?` da 130, 0 y 0.
7. Clave inventada → `error:` de autenticación y la conversación sigue.
8. Modelo inexistente → `error:` del proveedor y la conversación sigue.
9. Cortar la red a mitad de respuesta: si el corte no manda un RST (cierre
   brusco de la conexión TCP), el error llega tras el timeout de lectura
   (120 s); con un corte que dé RST, al momento. Si no se puede provocar, se
   anota.
10. `maha < notas.txt` sigue funcionando.

## 8. Lo que no viaja por git y lo que necesita la release

- Clave y configuración: las del hito 2. `PUESTA_EN_MARCHA` sin cambios.
- Release: nada fuera de lo normal.
- `docs/MAPA.md`: los ficheros de §3.1.
- `docs/DESIGN.md` §5 (`MessageEnd` lleva `model`): ya corregido, con fecha.

## 9. Guía

`docs/guia/03-streaming.md`, "Qué es el streaming de un LLM, qué es SSE y cómo
se cancela":
1. SSE: un POST cuya respuesta no se cierra; trozos `data:` separados por línea
   en blanco (ejemplo de §1.3, datos inventados).
2. De los trozos a eventos propios; por qué el `usage` llega el último y solo si
   se pide.
3. Qué puede salir mal a mitad, y qué queda en la conversación (§1.6, §1.8).
4. Cancelar con Ctrl+C: `CancelledError` y el cierre de la conexión.
5. Los tokens de más: el dato de §1.1 y qué reveló la sonda.

"En la industria": la tabla de §2.

## 10. Riesgos

**POR VERIFICAR** (lo demás de §1.1 está comprobado):
- **OpenCode Go y Zen, streaming:** si aceptan `stream: true` y
  `stream_options`, si devuelven `usage` en el último trozo, `Content-Type`,
  formato de un error a mitad de stream. https://opencode.ai/docs/go/ y
  https://opencode.ai/docs/zen/ no lo dicen. Lo resuelve la sonda.
- **Razonamiento de `glm-5.3-flash` en OpenCode Go:** campo de `delta`
  (`reasoning_content` o `reasoning`) y `reasoning_tokens` en `usage`. Sonda.
- **respx 0.23.1:** servir un cuerpo que falle a mitad, y si admite un
  `httpx.AsyncByteStream` propio (https://lundberg.github.io/respx/guide/ no lo
  documenta). Pieza 7, con el plan B de §4.
- **`aiter_text()` de httpx 0.28.1:** solo si se prefiere a §1.3. No bloquea.

**Riesgos y contingencias:**
- **`stream_options` rechazado (400) o sin `usage`.** Lo detecta la sonda. Se
  deja de enviar o se acepta el `usage` en ceros: la terminal no imprime la
  línea (§1.10). `Usage` a `None` cambiaría §1.4 (duda 5).
- **Silencio largo antes del primer token** (modelos que razonan): `read=120`
  no corta, pero la terminal parece colgada. Si la sonda lo muestra, el
  mantenedor decide un indicador "pensando…" (duda 2).
- **Texto cancelado en pantalla que el modelo no recuerda** (§1.6): se explica
  en la guía; se corrige en el hito 6.
- **Ctrl+C y `CancelledError` mezclados:** ya falló en el hito 2. Se cubre con
  la prueba en pty de §7.5.
- **`filterwarnings = ["error"]`** puede romper tests por una respuesta no
  cerrada o una corrutina no esperada: es señal de que falta cerrar algo; se
  arregla el cierre, no se silencia.
- **`refusal` y `tool_calls` en el stream** se ignoran (solo `delta.content`).
  Una `refusal` se perdería en silencio; se trata en el hito 4.

## 11. Decisiones

Del humano (fecha): *ninguna todavía.*

Propuestas del agente (2026-10-20), pendientes de aprobación: **todas las de
§1.2 a §1.11 y los cuatro PRs de §6**, cada una explicada en su sitio.

**Por decidir por el mantenedor:**
1. ¿`complete()` fuera del puerto (propuesta, §1.2) o junto a `stream()`?
2. Si la sonda muestra razonamiento: ¿ignorarlo (propuesta), o añadir
   `ReasoningDelta` y/o un indicador "pensando…" ya en este hito?
3. ¿Ctrl+C a mitad de respuesta vuelve al prompt (propuesta, §1.10) o sale con
   130 como en el hito 2?
4. *(Cerrada: los endpoints de Go y Zen coinciden con `config.py`.)*
5. Si OpenCode no manda `usage`: ¿`Usage` admite `None` o se queda en ceros y
   la terminal omite la línea (propuesta)? Se decide con la sonda.

## 12. Aprendido al implementar (fecha)

*(Se rellena al implementar. La sonda de la pieza 1 anota aquí, con fecha, los
puntos de §1.7.)*
