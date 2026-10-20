Estado: PROPUESTA (2026-10-20) → APROBADA (2026-10-20, por el humano, sin cambios)

# Spec — Hito 2: Primera conversación

Referencias: `docs/DESIGN.md` §3 (arquitectura), §5 (contrato de datos), §6
(puerto `ModelClient`), §7 (stack y configuración), §8 (modelos), §10
(seguridad), §12 (tests) y §14 (hito 2); `docs/ANALISIS.md` §9 (privacidad);
spec del hito 1; `AGENTS.md` (reglas no negociables).

## 0. Alcance

**El problema.** `maha` solo responde a `--version`. Todavía no habla con
ningún modelo, y DESIGN §14 marca este hito como el primer riesgo que puede
matar el proyecto: hablar con un proveedor real con un cliente propio, sin
SDK.

**Lo que hace este cambio.** `maha`, sin argumentos, abre una conversación
en la terminal con el modelo configurado. Cada respuesta se pide con una
llamada HTTP propia en formato OpenAI (sin streaming), y la conversación
recuerda lo dicho porque se reenvía entera en cada llamada. Proveedor y
modelo salen de un fichero de configuración; la clave, de una variable de
entorno.

Dentro de alcance:
- Tipos del dominio: `TextBlock`, `Message`, `ModelRequest`,
  `ModelResponse`, `Usage`, `StopReason` y los errores del modelo.
- Puerto `ModelClient` con `complete(request) -> response`.
- `FakeModelClient` guionizado, en `tests/fakes/`.
- Caso de uso `Chat`: guarda la conversación en memoria y la reenvía entera.
- Adaptador `OpenAIChatClient` (httpx), compatible con OpenCode Go, OpenCode
  Zen y cualquier servidor con formato OpenAI.
- Configuración en TOML: proveedores predefinidos, del usuario y del
  proyecto.
- Conversación mínima en la terminal: escribir, leer la respuesta, ver los
  tokens, salir con `/exit` o Ctrl+D.
- `.env.example`, nota 02 de la guía y docs al día.

**Fuera de alcance** (y por qué):
- Streaming, `ModelEvent` y cancelación con Ctrl+C a mitad de respuesta:
  hito 3.
- Herramientas (`tools` en la petición, `ToolCallBlock`): hito 4.
- Límite de tokens de salida (`max_tokens`): llega con los límites del bucle
  (§1.6).
- System prompt: hito 10. Aquí la petición va sin él (§1.5).
- Guardar la conversación en disco, `/model` y `/sessions`: hito 6.
- Reintentos automáticos ante 429 o 5xx: se valoran con el streaming o las
  trazas (§1.9).
- Catálogo de modelos y coste: hito 7. Aquí solo se muestran los tokens.
- Bloques de razonamiento (`ReasoningBlock`): si el proveedor los devuelve,
  se ignoran (§10).
- Rich y prompt_toolkit: la interfaz completa es el hito 19. Aquí basta
  `input()` y `print()`.

## 1. Decisiones de fondo

### 1.1 Hechos comprobados hoy

Comprobados el 2026-10-20 en la documentación oficial y en PyPI.

**OpenCode Go** (https://opencode.ai/docs/go/):
- Chat completions: `https://opencode.ai/inference/go/openai/v1/chat/completions`.
- Pide a los clientes de terceros un User-Agent propio (por ejemplo,
  `my-coding-agent/1.0`) y un id de sesión estable en la cabecera
  `x-opencode-session`.
- Modelos por chat completions, entre otros: `glm-5.3-flash`, `glm-5.3`,
  `kimi-k3`, `deepseek-v4.1-flash`. Ninguno de los modelos de chat
  completions entrena con los datos. Los que sí entrenan (Gemini 4 Argon
  Contributor y Muse Spark 1.2 y 1.3 Contributor) van por otros endpoints.
- Solo para espacios de trabajo de un miembro. Límites en dólares por mes,
  con ventanas de 5 horas (20 %) y semanal (50 %).
- **No documenta la cabecera de autenticación.** Se supone
  `Authorization: Bearer`, como en Zen (§10).

**OpenCode Zen** (https://opencode.ai/docs/zen/):
- Chat completions: `https://opencode.ai/inference/openai/v1/chat/completions`.
- Autenticación: `Authorization: Bearer $OPENCODE_API_KEY`.
- Pago por uso por millón de tokens (por ejemplo, `glm-5.3-flash`: 0,15 $ de
  entrada y 0,50 $ de salida). Tiene modelos gratis, y algunos sí usan los
  datos (Big Pickle, LL Alpha Free, Exo Free, MiMo Free).
- **Los ids cambian entre Go y Zen**, y algunos modelos van por endpoints
  distintos en cada uno. Por eso cada proveedor tiene su URL propia y el
  modelo se escribe tal cual.

**OpenAI Chat Completions** (https://developers.openai.com/api/reference/resources/chat):
- Petición: `model` y `messages` (roles `system`, `developer`, `user`,
  `assistant`, `tool`). `max_tokens` está obsoleto en favor de
  `max_completion_tokens`.
- Respuesta: `choices[].message.content`, `choices[].finish_reason` (`stop`,
  `length`, `tool_calls`, `content_filter`) y `usage` (`prompt_tokens`,
  `completion_tokens`, `prompt_tokens_details.cached_tokens`).
- Errores (https://developers.openai.com/api/docs/guides/error-codes): cuerpo
  `{"error": {"message", "type", "param", "code"}}`. 401 clave mala, 403
  región no admitida, 429 límite, 500 error del servidor, 503 sobrecarga.

**Dependencias** (PyPI):

| Librería | Versión | Publicada | Para qué |
|---|---|---|---|
| pydantic | 2.14.1 | 2026-10-11 | Tipos del dominio y configuración |
| httpx | 0.28.1 | 2024-12-06 | Llamadas HTTP asíncronas al proveedor |
| respx | 0.23.1 | 2026-04-08 | Simular respuestas HTTP en los tests (solo `dev`) |

Las tres se importan sin avisos (`python -W error`) en Python 3.14.8 y
3.15.0, y pydantic-core 2.50.1 publica wheels para las dos.

### 1.2 Dependencias nuevas, justificadas

Son las primeras dependencias de ejecución del proyecto.

- **pydantic:** DESIGN D4 y D7. Valida la configuración y la respuesta del
  proveedor, y da los tipos del dominio con serialización (las sesiones del
  hito 6 la usarán).
- **httpx:** DESIGN D1. Cliente HTTP asíncrono. Se ve el JSON exacto que
  viaja, que es lo que el proyecto quiere enseñar.
  - Descartado: el SDK `openai`. Escondería justo la pieza que se construye
    (ANALISIS §7: los adaptadores de formato son propios).
- **respx** (`dev`): DESIGN §7. Simula httpx en los tests, sin red.

### 1.3 El puerto, sin streaming: `complete()`

```python
class ModelClient(Protocol):
    async def complete(self, request: ModelRequest) -> ModelResponse: ...
```

- **Por qué:** el hito 2 pide la respuesta entera. DESIGN §6 describe el
  puerto final, `stream()`, que llega con `ModelEvent` en el hito 3. Ahí se
  decide si `complete()` se queda (útil para evals y resúmenes) o se
  sustituye.
- **`async` desde ya:** el bucle y la E/S son asíncronos (AGENTS.md).
- *`Protocol`:* una interfaz que se cumple por forma, sin heredar de ella. El
  adaptador real y el fake la cumplen, y mypy lo comprueba.

### 1.4 El modelo no recuerda: `Chat` reenvía todo

`application/chat.py` guarda la lista de mensajes en memoria. En cada
`send()`:

1. añade el mensaje del usuario;
2. llama al modelo con **todos** los mensajes;
3. añade la respuesta y la devuelve.

Si la llamada falla, quita el mensaje del usuario. Así la conversación queda
como estaba y se puede repetir.

- **Por qué:** la API no guarda nada entre llamadas. Recordar es reenviar el
  historial. Por eso los tokens de entrada crecen en cada turno, y la
  terminal los muestra. Es la idea central de la nota 02 de la guía.
- **Descartado:** dejar el mensaje fallido en la conversación. El siguiente
  envío llevaría dos mensajes de usuario seguidos y un hueco sin respuesta.

### 1.5 Sin system prompt en este hito

`ModelRequest.system` existe (DESIGN §5) y el adaptador lo sabe enviar, pero
`Chat` lo deja vacío.

- **Por qué:** un prompt es código que pasa por evals (AGENTS.md), y las
  evals nacen en el hito 8. El system prompt por capas es el hito 10.
- **Consecuencia:** el modelo responde con su comportamiento por defecto.
  Basta para conversar.

### 1.6 Sin límite de tokens de salida, de momento

No se envía `max_tokens` ni `max_completion_tokens`.

- **Por qué:** OpenAI marca `max_tokens` como obsoleto, y no está
  documentado cuál de los dos aceptan los modelos de OpenCode. Enviar el que
  no toca puede dar un 400. Los límites de tokens llegan con el bucle (hito 4)
  y el contexto (hito 11), y ahí se decide con esa información.
- **Riesgo aceptado:** cada modelo usa su límite por defecto.

### 1.7 Errores del modelo, en el dominio

`domain/errors.py`:

| Error | Cuándo |
|---|---|
| `ModelAuthError` | 401 o 403 |
| `ModelRateLimitError` | 429 |
| `ModelRequestError` | Otro 4xx (por ejemplo, un modelo que no existe) |
| `ModelUnavailableError` | 5xx, tiempo agotado o fallo de red |
| `ModelResponseError` | Respuesta 200 con un cuerpo que no se entiende |

Todos heredan de `ModelError`.

- **Por qué en el dominio:** el caso de uso y la terminal reaccionan a ellos
  sin saber que hay HTTP debajo. El adaptador traduce los errores de httpx a
  estos.
- **El mensaje del proveedor** (`error.message`) se incluye, recortado a 300
  caracteres. Es entrada no confiable, pero solo se muestra al usuario; no
  vuelve al modelo. Un test comprueba que la clave nunca aparece en un
  error.
- **Sin reintentos:** el error se muestra y la conversación sigue (§1.9).

### 1.8 El adaptador traduce, no decide

`adapters/models/openai_chat.py`, `OpenAIChatClient`:

- **Petición:** `POST {base_url}/chat/completions`.

  ```json
  {"model": "glm-5.3-flash",
   "messages": [{"role": "user", "content": "Hola, soy Ane"},
                {"role": "assistant", "content": "Hola, Ane."},
                {"role": "user", "content": "¿Cómo me llamo?"}]}
  ```

  - `system`, si lo hay, va primero como `{"role": "system", ...}`. Se usa
    `system` y no `developer`, porque es el que entienden los servidores
    compatibles.
  - Los bloques de texto de un mensaje se unen con un salto de línea.
- **Cabeceras:**
  - `Authorization: Bearer <clave>`, si el proveedor tiene clave;
  - `User-Agent: maha/<versión> (+https://github.com/ManexMartikorena/m-harness)`;
  - la cabecera de sesión del proveedor (`x-opencode-session` en los de
    OpenCode), con un UUID por ejecución de `maha`.
- **Respuesta:** se valida con modelos Pydantic privados del adaptador. Se
  toma `choices[0]`:

  | OpenAI | Dominio |
  |---|---|
  | `message.content` | `Message(role="assistant", blocks=[TextBlock(...)])` |
  | `finish_reason`: `stop` / `length` / `tool_calls` / `content_filter` / otro | `StopReason`: `end_turn` / `max_tokens` / `tool_use` / `content_filter` / `other` |
  | `usage.prompt_tokens` / `completion_tokens` / `prompt_tokens_details.cached_tokens` | `Usage.input_tokens` / `output_tokens` / `cache_read_tokens` |
  | `model` | `ModelResponse.model` |

  Si falta `usage`, los tokens quedan a 0. Campos que no se conocen (por
  ejemplo, `reasoning_content`) se ignoran.
- **Tiempo límite:** 10 s para conectar y 120 s para la respuesta entera
  (`httpx.Timeout`). Sin streaming, una respuesta larga tarda.
- **El adaptador crea y cierra su `httpx.AsyncClient`**
  (`async with OpenAIChatClient(...) as client:`). Los tests lo interceptan
  con respx.

*Adaptador (patrón Adapter):* traduce entre dos interfaces. Aquí, entre los
tipos del dominio y el JSON de OpenAI. No decide nada del agente.

### 1.9 Sin reintentos en este hito

- **Por qué:** con una persona delante, un error visible se repite a mano.
  Los reintentos automáticos esconden el problema que la guía quiere
  enseñar.
- **En la industria:** el SDK `openai` reintenta 2 veces 429, 5xx y fallos
  de conexión, con espera exponencial. Se valora en el hito 3 (streaming) o
  en el 8 (evals sin persona delante).

### 1.10 Configuración: TOML, con dos niveles y un límite de seguridad

`src/mharness/config.py`. Lee, valida y combina (DESIGN §7):

1. **Proveedores predefinidos**, en el código: `opencode-go` y
   `opencode-zen`, con su URL, `OPENCODE_API_KEY` y `x-opencode-session`.
2. **Usuario:** `$XDG_CONFIG_HOME/maha/config.toml` (por defecto,
   `~/.config/maha/config.toml`).
3. **Proyecto:** `.maha/config.toml` en el directorio de trabajo.

```toml
# ~/.config/maha/config.toml
provider = "opencode-go"
model = "glm-5.3-flash"

# Opcional: proveedores propios (cualquier servidor con formato OpenAI).
[providers.local]
base_url = "http://localhost:11434/v1"
# api_key_env = "MI_CLAVE"      # opcional; sin ella, no se envía Authorization
```

- **El proyecto solo puede elegir `provider` y `model`.** Si declara
  `[providers]`, `maha` se niega a arrancar y dice por qué.
  - **Por qué:** un repositorio ajeno con un `.maha/config.toml` podría
    poner `base_url` en un servidor suyo y `api_key_env = "OPENCODE_API_KEY"`.
    `maha` le enviaría la clave del usuario. Es un fallo real en otros
    agentes: la configuración de proyecto es entrada no confiable.
  - **Corrige DESIGN §7**, que decía "la configuración del proyecto
    prevalece sobre la del usuario" sin límite. Se anota allí, con fecha.
- **Campos desconocidos son error** (`extra="forbid"`): una errata
  (`modle = ...`) se ve al arrancar, no se ignora.
- **Sin modelo por defecto en el código.** Los ids cambian a menudo (§1.1).
  Sin `model`, `maha` explica qué escribir y dónde.
- **La clave sale del entorno.** `maha` nunca lee `.env` (DESIGN §7). En
  desarrollo: `uv run --env-file .env maha`. Si falta, el mensaje lo dice.
- **`api = "openai-chat"`** en cada proveedor, el único formato por ahora. El
  hito 9 añade `"anthropic"`.
- **Capa:** `config` es hermana de `adapters`, debajo de `bootstrap`
  (`"adapters | config"` en import-linter, probado el 2026-10-20). Solo la
  usa `bootstrap`, y no puede importar adaptadores, ni ellos a ella.
  - Lee ficheros y no está detrás de un puerto. Es aceptable porque es
    fontanería de arranque: se ejecuta una vez, antes del núcleo, y el
    núcleo nunca la ve. Los valores llegan a cada pieza por su constructor.

### 1.11 `maha` sin argumentos abre la conversación

| Orden | Hace |
|---|---|
| `maha` | Abre la conversación |
| `maha --help` | La ayuda |
| `maha --version` | `maha 0.2.0`, sin necesitar configuración |

- **Cambia la decisión 3.3 del hito 1** ("`maha` sin argumentos muestra la
  ayuda"), como estaba previsto: es lo que hacen Claude Code y OpenCode. El
  test correspondiente se actualiza.

**En la terminal:**

```
maha 0.2.0 · opencode-go · glm-5.3-flash · /exit to quit
> Hola, soy Ane
Hola, Ane. ¿En qué te ayudo?
  [tokens: 12 in · 9 out]
> ¿Cómo me llamo?
Te llamas Ane.
  [tokens: 31 in · 5 out]
```

Los textos de `maha` van en inglés (decisión 1.6 del hito 1); la
conversación, en el idioma del usuario. Los tokens de entrada pasan de 12 a
31 porque la segunda llamada reenvía el primer turno.

- `/exit` o Ctrl+D: sale con 0. Ctrl+C: sale con 130 (la convención de la
  terminal para una interrupción).
- Línea vacía: no se envía.
- Error del modelo: `error: …` en stderr, y la conversación sigue.
- Error de configuración o falta la clave: mensaje en stderr y sale con 1,
  antes de abrir la conversación.
- Entrada con `input()` en un hilo aparte (`asyncio.to_thread`), para no
  bloquear el bucle de asyncio.

### 1.12 Cableado en `bootstrap.py`

```python
def main(argv: Sequence[str] | None = None) -> int:
    options = cli.parse(argv)              # --version y --help terminan aquí
    if isinstance(options, int):
        return options
    settings = config.load(cwd=Path.cwd()) # puede fallar: mensaje y 1
    return asyncio.run(_converse(settings))

async def _converse(settings: Settings) -> int:
    provider = settings.active_provider()
    async with OpenAIChatClient(base_url=..., api_key=..., ...) as client:
        chat = Chat(client, model=settings.model)
        return await cli.converse(chat, ...)
```

`bootstrap` es el único sitio que conoce `config`, el adaptador de modelos,
el caso de uso y la terminal (DESIGN §3).

## 2. En la industria

| Pieza | M-Harness | Alternativas | Cuándo se elegirían |
|---|---|---|---|
| Cliente del modelo | httpx + adaptador propio | SDK `openai`; LiteLLM; AI SDK de Vercel (TypeScript, lo usa OpenCode) | SDK: un solo proveedor y prisa. LiteLLM: muchos proveedores sin escribir adaptadores |
| Pasarela de proveedores | Configuración propia (`base_url` por proveedor) | OpenRouter, LiteLLM Proxy, Portkey | Una sola clave y facturación para muchos modelos |
| Tipos de mensajes | Bloques propios (Pydantic) | Los tipos del SDK de cada proveedor | Cuando no se piensa cambiar de proveedor |
| Errores y reintentos | Errores propios, sin reintentos | Reintentos con espera exponencial del SDK `openai`; tenacity | En producción y sin persona delante |
| Configuración | TOML + Pydantic | pydantic-settings; Dynaconf; YAML o JSON | pydantic-settings: mezclar variables de entorno y ficheros con poco código |
| Tests HTTP | respx + respuestas de ejemplo | VCR.py, pytest-recording (graban respuestas reales) | Para fijar respuestas reales de un proveedor |
| Entrada en la terminal | `input()` | prompt_toolkit, Rich, Textual | Historial, autocompletado, interfaz completa (hito 19) |

*Nombres comprobados en PyPI y en la documentación oficial el 2026-10-20.*

## 3. Diseño de detalle

### 3.1 Ficheros

```
src/mharness/
├── config.py                      # Settings, ProviderSettings, load()
├── bootstrap.py                   # cambia: cablea config, adaptador, Chat y cli
├── domain/
│   ├── messages.py                # TextBlock, Message
│   ├── model.py                   # ModelRequest, ModelResponse, Usage, StopReason
│   └── errors.py                  # ModelError y sus cinco tipos
├── ports/
│   └── model.py                   # ModelClient (Protocol)
├── application/
│   └── chat.py                    # Chat: historial en memoria y send()
└── adapters/
    ├── models/
    │   ├── __init__.py
    │   └── openai_chat.py         # OpenAIChatClient
    └── cli/
        ├── app.py                 # cambia: parse() en lugar de run()
        └── conversation.py        # converse(): leer, enviar, mostrar
tests/
├── fakes/
│   ├── __init__.py
│   └── model.py                   # FakeModelClient
├── fixtures/openai_chat/          # respuestas de ejemplo (datos inventados)
├── unit/                          # dominio, Chat y config
├── adapters/                      # test_openai_chat.py, test_cli*.py
└── test_bootstrap.py              # de punta a punta, con respx
.env.example                       # OPENCODE_API_KEY=
```

### 3.2 Tipos del dominio

```python
Role = Literal["user", "assistant", "tool"]
StopReason = Literal["end_turn", "max_tokens", "tool_use", "content_filter", "other"]


class TextBlock(BaseModel):  # frozen
    type: Literal["text"] = "text"
    text: str


class Message(BaseModel):  # frozen
    role: Role
    blocks: list[TextBlock]  # el hito 4 añade ToolCallBlock…

    @property
    def text(self) -> str: ...  # los bloques de texto, unidos


class ModelRequest(BaseModel):  # frozen
    model: str
    system: str | None = None
    messages: list[Message]  # el hito 4 añade tools


class Usage(BaseModel):  # frozen
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


class ModelResponse(BaseModel):  # frozen
    message: Message
    stop_reason: StopReason
    usage: Usage
    model: str
```

- **Inmutables** (`frozen=True`): un mensaje enviado no cambia. `Chat` añade
  mensajes nuevos, no edita los anteriores.
- **`type` en cada bloque:** un discriminador. Cuando haya varios tipos de
  bloque, Pydantic sabrá cuál es cada uno al leer una sesión del disco.

### 3.3 `FakeModelClient`

```python
fake = FakeModelClient([reply("Hola, Ane."), ModelRateLimitError("slow down")])
await fake.complete(request)  # → la primera respuesta
await fake.complete(request)  # → lanza el error
fake.requests  # las peticiones recibidas, para comprobarlas
```

Guion agotado → `AssertionError`: un test que llama más de lo previsto falla
claro. Cumple `ModelClient`, y mypy lo comprueba (mira `tests/`, hito 1).

### 3.4 Configuración nueva

| Qué | Dónde | Por defecto |
|---|---|---|
| `provider`, `model` | `~/.config/maha/config.toml` o `.maha/config.toml` | `provider = "opencode-go"`; `model`, ninguno |
| `[providers.<nombre>]`: `api`, `base_url`, `api_key_env`, `session_header` | Solo en la del usuario | `opencode-go` y `opencode-zen` predefinidos |
| `OPENCODE_API_KEY` | Variable de entorno (`.env` en desarrollo) | — |

## 4. Plan de tests

Sin llamadas reales ni red.

1. **Dominio** (`tests/unit/test_messages.py`, `test_model.py`):
   1. `Message.text` une los bloques; un mensaje es inmutable.
   2. `Usage` vale 0 por defecto; `ModelRequest` sin `system` es válido.
2. **`FakeModelClient`** (`tests/unit/test_fake_model.py`): devuelve el
   guion en orden, lanza los errores guionizados, guarda las peticiones y
   falla al agotarse.
3. **`Chat`** (`tests/unit/test_chat.py`), con el fake:
   1. La segunda llamada lleva los tres mensajes: usuario, asistente,
      usuario. **Fija la decisión 1.4.**
   2. La petición lleva el modelo configurado y no lleva `system` (1.5).
   3. Si la llamada falla, el error sube y la conversación queda como
      estaba.
4. **Adaptador** (`tests/adapters/test_openai_chat.py`), con respx y
   respuestas de `tests/fixtures/openai_chat/`:
   1. El JSON enviado es exactamente el de §1.8, con y sin `system`.
   2. Cabeceras: `Authorization`, `User-Agent` y la de sesión; sin clave,
      no hay `Authorization`.
   3. La respuesta se traduce: texto, `StopReason` (cada `finish_reason`),
      `Usage` (con y sin `cached_tokens`, y sin `usage`).
   4. 401, 403, 429, 400, 404, 500 y 503 → su error; con el `message` del
      proveedor, recortado.
   5. Tiempo agotado y fallo de conexión → `ModelUnavailableError`.
   6. Un 200 con JSON roto o sin `choices` → `ModelResponseError`.
   7. Ningún error contiene la clave.
5. **Configuración** (`tests/unit/test_config.py`), con directorios
   temporales:
   1. Usuario y proyecto se combinan; el proyecto gana en `provider` y
      `model`.
   2. `[providers]` en el proyecto → error. **Fija la decisión 1.10.**
   3. Sin `model`, con un proveedor desconocido o con un campo desconocido →
      error con un mensaje que dice qué hacer.
   4. Respeta `XDG_CONFIG_HOME`; sin ficheros, usa los predefinidos.
   5. La clave sale del entorno; si falta, el error nombra la variable.
6. **Terminal** (`tests/adapters/test_cli.py` y `test_conversation.py`), con
   el fake y una entrada guionizada:
   1. `--version` y `--help` siguen igual; sin argumentos, `parse()` devuelve
      las opciones (cambia el test 1.3 del hito 1).
   2. Escribe la respuesta y la línea de tokens.
   3. `/exit` y Ctrl+D (EOF) salen con 0; una línea vacía no llama al
      modelo.
   4. Un error del modelo va a stderr y la conversación sigue.
7. **De punta a punta** (`tests/test_bootstrap.py`): `main()` con
   configuración temporal, clave en el entorno, respx y entrada guionizada.
   Dos turnos; el segundo envía el historial. Y sin configuración, `main()`
   sale con 1 y explica qué falta.
8. **Arquitectura:** el contrato de capas con `"adapters | config"`; el
   test de imports del núcleo sigue igual (pydantic permitido; httpx solo en
   el adaptador).

## 5. Evals

No aplica: las evals nacen en el hito 8. Este hito no tiene system prompt ni
herramientas.

## 6. Orden de piezas para el implementador

Cada punto es un commit, con lo que exista hasta ese momento en verde.

**PR 1** (`feature/hito-2-nucleo`): el núcleo, sin red.
1. **Pydantic.** Dependencia de ejecución.
   *Commit:* "Añadir Pydantic como dependencia"
2. **Mensajes.** `domain/messages.py` y sus tests.
   *Commit:* "Añadir los mensajes del dominio"
3. **Petición y respuesta.** `domain/model.py` y sus tests.
   *Commit:* "Añadir la petición y la respuesta del modelo"
4. **Errores.** `domain/errors.py`.
   *Commit:* "Añadir los errores del modelo"
5. **Puerto.** `ports/model.py`.
   *Commit:* "Añadir el puerto ModelClient"
6. **Fake.** `tests/fakes/model.py` y sus tests.
   *Commit:* "Añadir el FakeModelClient guionizado"
7. **Chat.** `application/chat.py` y sus tests.
   *Commit:* "Añadir el caso de uso Chat, que reenvía el historial"
8. **Mapa.** *Commit:* "Actualizar el mapa con el núcleo del hito 2"

**PR 2** (`feature/hito-2-openai`): el adaptador.

9. **httpx y respx.** *Commit:* "Añadir httpx y respx"
10. **Petición.** `OpenAIChatClient` construye y envía la petición, con sus
    cabeceras; tests 4.1 y 4.2.
    *Commit:* "Enviar la conversación en formato OpenAI"
11. **Respuesta.** Traducción de la respuesta; test 4.3 y fixtures.
    *Commit:* "Traducir la respuesta de OpenAI al dominio"
12. **Errores.** Traducción de errores; tests 4.4 a 4.7.
    *Commit:* "Traducir los errores HTTP a errores del modelo"
13. **Mapa.** *Commit:* "Actualizar el mapa con el adaptador de OpenAI"

**PR 3** (`feature/hito-2-terminal`): configuración, terminal y cableado.

14. **Configuración.** `config.py`, la capa en import-linter y los tests 5.
    *Commit:* "Leer la configuración de proveedor y modelo"
15. **Conversación.** `adapters/cli/conversation.py`; tests 6.2 a 6.4.
    *Commit:* "Añadir la conversación en la terminal"
16. **Cableado.** `cli.parse()`, `bootstrap.py`, test 6.1 y 7.
    *Commit:* "Abrir la conversación al lanzar maha"
17. **Variables.** `.env.example` y `PUESTA_EN_MARCHA` (§8).
    *Commit:* "Documentar la configuración y la clave del proveedor"
18. **Mapa.** *Commit:* "Actualizar el mapa con la terminal del hito 2"

**PR 4** (`feature/hito-2-cierre`): cierre del hito.

19. **Versión.** `uv version --bump minor` → `0.2.0`.
    *Commit:* "Subir la versión a 0.2.0"
20. **Guía.** `docs/guia/02-llamada-a-un-llm.md` y su fila en el índice.
    *Commit:* "Añadir la nota de la guía sobre la llamada a un LLM"
21. **Cierre de la spec.** IMPLEMENTADA y "Aprendido al implementar".
    *Commit:* "Cerrar la spec del hito 2"
22. **Documentación al día.** README, MAPA y ESTADO.
    *Commit:* "Actualizar la documentación al cerrar el hito 2"

**Tras integrar el PR 4:** tag `v0.2.0` sobre el merge commit y push del
tag.

## 7. Verificación a mano

Con el entorno de desarrollo y una clave real (§8).

1. `uv run maha --version` → `maha 0.2.0`, sin configuración.
2. Sin `~/.config/maha/config.toml`: `uv run maha` explica qué escribir y
   sale con 1.
3. Con la configuración de §1.10 y sin la clave: `uv run maha` nombra
   `OPENCODE_API_KEY` y sale con 1.
4. `uv run --env-file .env maha`: dos turnos. En el segundo, el modelo
   recuerda lo dicho en el primero, y los tokens de entrada han crecido.
5. **Autenticación de Go** (riesgo de §10): si el punto 4 funciona con
   `opencode-go`, `Authorization: Bearer` es correcto. Se anota en
   "Aprendido al implementar".
6. Una clave inventada → `error:` de autenticación, y la conversación sigue.
7. Un modelo que no existe → `error:` del proveedor, y la conversación
   sigue.
8. `/exit`, Ctrl+D y Ctrl+C salen; `echo $?` da 0, 0 y 130.
9. Un directorio desechable con un `.maha/config.toml` que declara
   `[providers]` → `maha` se niega a arrancar.

## 8. Lo que no viaja por git y lo que necesita la release

- **Clave del proveedor** (humano): el mantenedor ya tiene la suscripción a
  OpenCode Go. Falta poner la clave en `OPENCODE_API_KEY` del `.env` de cada
  PC. Solo hace falta para la verificación a mano; los tests no la usan.
- **`~/.config/maha/config.toml`** en cada PC, con `provider` y `model`.
- **`.env.example`** nuevo, con `OPENCODE_API_KEY=` vacío.
- **`PUESTA_EN_MARCHA`:** §0 (tras el pull: `uv sync`, crear la
  configuración y el `.env`), §2 (la variable ya está en la tabla) y una
  sección nueva para `config.toml`.
- **Release:** nada fuera de lo normal.
- **`docs/MAPA.md`:** los ficheros de §3.1.

## 9. Guía

`docs/guia/02-llamada-a-un-llm.md`, "Qué es una llamada a un LLM y por qué
el modelo no recuerda":

1. Una llamada es un POST con JSON: la petición y la respuesta reales, con
   datos inventados.
2. El modelo no recuerda: cada llamada lleva la conversación entera. Los
   tokens de entrada crecen en cada turno, y eso cuesta.
3. Tipos propios y un adaptador: el dominio habla en bloques y el
   adaptador traduce a OpenAI. Así, el hito 9 (Anthropic) es otro adaptador.
4. Lo que puede salir mal: errores HTTP, tiempos límite, y la clave y la
   configuración del proyecto como superficie de ataque.

"En la industria": la tabla de §2.

## 10. Riesgos

- **La autenticación de Go no está documentada.** Se supone
  `Authorization: Bearer`, como en Zen. Si falla, se comprueba a mano y se
  corrige en el adaptador (el proveedor tendría su propio esquema). Ver §7.5.
- **Formato de errores de OpenCode sin documentar.** El adaptador lee
  `error.message` si está y, si no, usa el código HTTP. Nunca falla por no
  entender el cuerpo de un error.
- **`reasoning_content` y bloques de razonamiento.** Algunos modelos
  (GLM, DeepSeek) pueden devolver el razonamiento aparte. Se ignora. Si un
  modelo devuelve `content` vacío con el texto en otro campo, se anota y se
  decide en el hito 3.
- **Sin `max_tokens`** (§1.6): una respuesta puede ser muy larga o cortarse
  con el límite por defecto del modelo (`StopReason = "max_tokens"`).
- **Ids de modelo que cambian:** no hay ninguno en el código, solo en la
  configuración y en los ejemplos de la documentación.
- **Modelos gratis que usan los datos** (Zen): la documentación avisa de no
  usarlos con datos privados. `maha` no lo impide en este hito. El catálogo
  del hito 7 puede marcarlos.
- **httpx 0.28.1 es de 2024.** Sigue siendo la última versión; si sale la
  1.0 con cambios, se valora en una mejora aparte.
- **`filterwarnings = ["error"]`** puede romper los tests por un aviso de
  httpx o respx. Si pasa, se ignora solo ese aviso, con su referencia.

## 11. Decisiones

Del humano (2026-10-20):
- Proveedor para el desarrollo: **OpenCode Go**, con su suscripción. Cierra
  el pendiente de ANALISIS §12. La verificación a mano (§7) se hace con
  `provider = "opencode-go"`.
- Aprueba la spec sin cambios, en el PR #7.

Propuestas del agente, aprobadas por el humano (2026-10-20):
1. Dependencias: pydantic y httpx de ejecución; respx de desarrollo (§1.2).
2. Puerto `ModelClient.complete()`, sin streaming; `stream()` en el hito 3
   (§1.3).
3. `Chat` reenvía el historial entero y deshace el turno si falla (§1.4).
4. Sin system prompt (§1.5) y sin límite de tokens de salida (§1.6) en este
   hito.
5. Cinco errores del modelo en el dominio, sin reintentos (§1.7 y §1.9).
6. Adaptador: `system` como rol, User-Agent propio, `x-opencode-session` y
   tiempos límite de 10 s y 120 s (§1.8).
7. Configuración en TOML con proveedores predefinidos, sin modelo por
   defecto, y el proyecto limitado a `provider` y `model`. Corrige DESIGN §7
   (§1.10).
8. `maha` sin argumentos abre la conversación; cambia la decisión 3.3 del
   hito 1 (§1.11).
9. Cuatro PRs de implementación (§6).

## 12. Aprendido al implementar

1. **`frozen` como argumento de la clase** (PR 1, pieza 2):
   `class Message(BaseModel, frozen=True)`, no `model_config =
   ConfigDict(frozen=True)`. Pydantic usa `dataclass_transform`, y mypy solo
   ve `frozen` en la primera forma. Así, asignar a un campo es error de tipos,
   además de error al ejecutar.
2. **`Chat` deshace el turno sin borrar nada** (PR 1, pieza 7): construye la
   lista nueva aparte y solo la guarda si la llamada termina bien. También
   cubre la cancelación, que no es un `ModelError`.
