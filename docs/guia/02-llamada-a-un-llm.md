# 02. Qué es una llamada a un LLM y por qué el modelo no recuerda

Hito 2 (`v0.2.0`). Spec: `docs/specs/hito-2-primera-conversacion.md`. Diseño:
`docs/DESIGN.md` §5, §6 y §7.

## El problema

Para conversar con un modelo hay que hablar con su API. Un SDK lo esconde
todo detrás de una función, y entonces no se ve:
- qué viaja de verdad por la red;
- por qué el modelo "recuerda" lo dicho, y lo que eso cuesta;
- qué puede salir mal (claves, límites, caídas) y cómo se trata.

## Cómo lo resuelve M-Harness

### 1. Una llamada es un POST con JSON

Sin SDK: httpx envía la petición, y el adaptador construye y lee el JSON.

```
POST https://opencode.ai/inference/go/openai/v1/chat/completions
Authorization: Bearer <clave>
User-Agent: maha/0.2.0 (+https://github.com/ManexMartikorena/m-harness)
x-opencode-session: 3f2b…  (un id por ejecución de maha)
```

```json
{"model": "glm-5.3-flash",
 "messages": [{"role": "user", "content": "Hola, soy Ane"}]}
```

La respuesta (recortada):

```json
{"model": "glm-5.3-flash",
 "choices": [{"message": {"role": "assistant", "content": "Hola, Ane."},
              "finish_reason": "stop"}],
 "usage": {"prompt_tokens": 25, "completion_tokens": 9}}
```

- *Token:* el trozo de texto con el que trabaja el modelo (más o menos, una
  sílaba o una palabra corta). Se paga por tokens de entrada y de salida.
- *`finish_reason`:* por qué paró el modelo. `stop` es que terminó; `length`,
  que se quedó sin tokens de salida.

### 2. El modelo no recuerda: cada llamada lleva la conversación entera

La API no guarda nada entre llamadas. Para que el modelo "recuerde", `Chat`
reenvía todo el historial en cada turno:

```python
# application/chat.py
messages = [*self._messages, Message(role="user", blocks=[TextBlock(text=text)])]
response = await self._client.complete(
    ModelRequest(model=self._model, messages=messages)
)
self._messages = [*messages, response.message]
```

La segunda petición lleva tres mensajes: usuario, asistente, usuario. Por eso
los tokens de entrada crecen en cada turno. Medido con OpenCode Go el
2026-10-20:

```
> Hola, soy Ane. Responde en una sola frase.
¡Hola Ane, encantado de conocerte! ¿En qué puedo ayudarte hoy?
  [tokens: 25 in · 142 out]
> ¿Cómo me llamo? Responde en una sola frase.
Te llamas Ane.
  [tokens: 62 in · 50 out]
```

Una conversación larga cuesta cada vez más por turno, y acaba sin caber en la
*ventana de contexto* (lo máximo que el modelo puede leer de una vez). Es el
problema del hito 11.

Si la llamada falla, `Chat` no guarda el mensaje: la conversación queda como
estaba y se puede repetir.

### 3. Tipos propios y un adaptador

El núcleo no habla en JSON de OpenAI. Habla en tipos propios (`Message`,
`ModelRequest`, `ModelResponse`), y el adaptador traduce:

```
Chat ──ModelRequest──► ModelClient (puerto) ◄── OpenAIChatClient (adaptador)
                                            ◄── FakeModelClient (tests)
```

| OpenAI | Dominio |
|---|---|
| `choices[0].message.content` | `Message(role="assistant", blocks=[TextBlock(...)])` |
| `finish_reason`: `stop` / `length` / `tool_calls` | `StopReason`: `end_turn` / `max_tokens` / `tool_use` |
| `usage.prompt_tokens` / `completion_tokens` | `Usage.input_tokens` / `output_tokens` |

Así, los tests prueban `Chat` con un fake guionizado, sin red, y el hito 9
(Anthropic) será otro adaptador, sin tocar el núcleo.

### 4. Lo que puede salir mal

Cada fallo se traduce a un error del dominio, y la terminal lo muestra sin
cortar la conversación:

| Qué pasa | Error |
|---|---|
| 401 o 403: clave mala | `ModelAuthError` |
| 429: demasiadas peticiones | `ModelRateLimitError` |
| Otro 4xx: por ejemplo, un modelo que no existe | `ModelRequestError` |
| 5xx, tiempo agotado o sin red | `ModelUnavailableError` |
| Un 200 que no se entiende | `ModelResponseError` |

```
> Hola
error: HTTP 401: Upstream request failed: Invalid credential
>
```

Dos superficies de ataque:
- **La clave.** Solo vive en una variable de entorno, nunca sale en un error
  (si el proveedor la devuelve, se tapa con `[redacted]`) y no aparece en el
  `repr` de la configuración.
- **La configuración del proyecto.** Un repositorio ajeno con un
  `.maha/config.toml` podría apuntar `base_url` a un servidor suyo y quedarse
  con la clave. Por eso el proyecto solo puede elegir `provider` y `model`; los
  proveedores se declaran en la configuración del usuario.

## En la industria

| Pieza | M-Harness | Alternativas | Cuándo se elegirían |
|---|---|---|---|
| Cliente del modelo | httpx + adaptador propio | SDK `openai`; LiteLLM; AI SDK de Vercel (TypeScript, lo usa OpenCode) | SDK: un solo proveedor y prisa. LiteLLM: muchos proveedores sin escribir adaptadores |
| Pasarela de proveedores | Configuración propia (`base_url` por proveedor) | OpenRouter, LiteLLM Proxy, Portkey | Una sola clave y facturación para muchos modelos |
| Tipos de mensajes | Bloques propios (Pydantic) | Los tipos del SDK de cada proveedor | Cuando no se piensa cambiar de proveedor |
| Errores y reintentos | Errores propios, sin reintentos | Reintentos con espera exponencial del SDK `openai`; tenacity | En producción y sin persona delante |
| Configuración | TOML + Pydantic | pydantic-settings; Dynaconf; YAML o JSON | pydantic-settings: mezclar variables de entorno y ficheros con poco código |
| Tests HTTP | respx + respuestas de ejemplo | VCR.py, pytest-recording (graban respuestas reales) | Para fijar respuestas reales de un proveedor |
| Entrada en la terminal | Lectura de stdin sin hilos | prompt_toolkit, Rich, Textual | Historial, autocompletado, interfaz completa (hito 19) |

Los SDK hacen exactamente esto por dentro: un POST con JSON, tipos para la
respuesta y una jerarquía de errores (`AuthenticationError`,
`RateLimitError`…). Aquí se escribe a mano para verlo (DESIGN §7.1).
