# 09. Dos formatos para hablar con un modelo

Hito 9 (`v0.9.0`). Spec: `docs/specs/hito-9-anthropic.md`.
Diseño: `docs/DESIGN.md` §5, §6, §7.1 y §14.

## El problema

Hasta el hito 8, `maha` solo hablaba el formato de OpenAI (Chat
Completions). Pero los modelos no hablan todos igual:

- **Claude** se sirve con el formato de Anthropic (la Messages API).
- **Un mismo proveedor** mezcla formatos: OpenCode Go sirve GLM y Kimi con
  el de OpenAI, y Claude Haiku 5.5, MiniMax M3 y Qwen 3.8 con el de
  Anthropic, cada uno en su URL.
- Faltaban dos palancas que dan los proveedores: **cuánto razona** el modelo
  (*effort*) y la **caché del prompt**, que abarata mucho un agente porque
  cada paso reenvía toda la conversación.

## Cómo lo resuelve M-Harness

### 1. Los dos formatos, lado a lado

- *Formato de API:* la forma del JSON que se manda y se recibe.

La misma pregunta con una herramienta, en los dos:

```jsonc
// OpenAI (Chat Completions): el system es un mensaje más; cada resultado,
// un mensaje "tool".
{"model": "glm-5.3-flash", "messages": [
  {"role": "system", "content": "…"},
  {"role": "user", "content": "Lee notas.txt"},
  {"role": "assistant", "content": null, "tool_calls": [
    {"id": "c1", "type": "function",
     "function": {"name": "read_file", "arguments": "{\"path\": \"notas.txt\"}"}}]},
  {"role": "tool", "tool_call_id": "c1", "content": "uno\ndos"}]}
```

```jsonc
// Anthropic (Messages): el system va aparte; todo son bloques; el resultado
// va en un mensaje "user"; max_tokens es obligatorio.
{"model": "claude-haiku-5-5", "max_tokens": 128000, "system": "…",
 "messages": [
  {"role": "user", "content": [{"type": "text", "text": "Lee notas.txt"}]},
  {"role": "assistant", "content": [
    {"type": "thinking", "thinking": "", "signature": "Eq…"},
    {"type": "tool_use", "id": "toolu_1", "name": "read_file",
     "input": {"path": "notas.txt"}}]},
  {"role": "user", "content": [
    {"type": "tool_result", "tool_use_id": "toolu_1", "content": "uno\ndos"}]}]}
```

| | OpenAI | Anthropic |
|---|---|---|
| System | un mensaje `system` | campo `system` aparte |
| Mensajes | texto, y las llamadas aparte | lista de bloques (`text`, `thinking`, `tool_use`…) |
| Argumentos de una llamada | texto JSON | objeto JSON (`input`) |
| Resultado de una herramienta | mensaje `tool` | bloque `tool_result` en un mensaje `user` |
| `max_tokens` | opcional | obligatorio |
| Streaming | trozos con `delta`, y `[DONE]` al final | eventos con nombre por bloque (`content_block_delta`…) |
| Tokens de entrada | todo el prompt | solo lo que va tras el último punto de caché |

El dominio de `maha` ya hablaba en bloques desde el hito 2 (DESIGN §5). Por
eso el adaptador nuevo solo traduce: el bucle no ha cambiado.

### 2. El formato es de cada modelo

```toml
# El catálogo (adapters/catalog/models.toml)
[models."opencode-go/claude-haiku-5-5"]
api = "anthropic"          # sin `api`, el formato del proveedor
max_output = 128_000
```

- *Router:* `ModelRouter` (en `application`) cumple el puerto `ModelClient`
  y manda cada petición al cliente del formato de su modelo. Por eso
  `/model` puede saltar de GLM a Claude a mitad de sesión.
- Un formato que `maha` aún no habla da un error claro antes de llamar:

```
error: gpt-6-luna uses the openai-responses API, which maha does not speak yet
```

### 3. El razonamiento con firma: devolverlo intacto

- *Thinking:* lo que el modelo piensa antes de responder. Anthropic lo
  devuelve con una **firma**, una copia cifrada.
- Hay que devolverlo **intacto y en su sitio** en la llamada siguiente. Si
  no, el modelo pierde lo que pensó.
- Desde Claude 5.1, un bloque de razonamiento solo vale si **todo lo
  enviado antes** llega igual: el system, las herramientas y los mensajes.

Por eso `maha`:
- guarda el razonamiento en la sesión, como cualquier bloque;
- rehace cada respuesta con sus bloques en el orden en que llegaron;
- tiene un test que fija la regla **"lo que se manda al modelo solo crece
  por el final"**. Los hitos 10 (system por capas) y 11 (compactación)
  tendrán que respetarla.

### 4. Effort y caché del prompt

- *Effort:* cuánto se esfuerza el modelo, de `low` a `max`. En OpenAI va
  como `reasoning_effort`; en Anthropic, como `output_config.effort`.

```
maha --effort high            # para esta ejecución
/effort low                   # en la conversación
effort = "high"               # en config.toml
```

  Medido en la batería: Claude Haiku 5.5 con `high` saca lo mismo (100/100)
  y cuesta un 22 % más. Por eso, por defecto, cada modelo usa el suyo.

- *Caché del prompt:* el proveedor guarda el principio de la petición; si
  la siguiente empieza igual, lo cobra mucho más barato.
  - En OpenAI es automática en el servidor.
  - En Anthropic, `maha` pide la caché automática (`cache_control` arriba
    de la petición) y el punto de caché avanza solo con la conversación.

  Medido por OpenCode: con un system de 2.546 tokens, la segunda llamada
  los leyó de la caché y costó 0,00005 $ en vez de 0,00034 $.

  `cache_ttl = "1h"` alarga la caché a una hora: escribir cuesta el doble
  (2 × la entrada frente a 1,25 ×), pero aguanta las pausas de una
  conversación.

### 5. Comparar proveedores con las evals

| Modelo (OpenCode Go) | Formato | Éxito | Coste de 100 ejecuciones |
|---|---|---|---|
| `glm-5.3-flash` | OpenAI | 93/100 | 0,07 $ |
| `kimi-k2.7-code` | OpenAI | 98/100 | 0,55 $ |
| `claude-haiku-5-5` | Anthropic | 100/100 | 0,29 $ |

La misma batería, el mismo bucle y las mismas herramientas: solo cambian el
modelo y el formato.

## En la industria

- **SDK oficial `anthropic`:** cliente con tipos, streaming, reintentos y
  `get_final_message()`. Es lo habitual en un producto. Aquí se escribió a
  mano para ver el JSON exacto (DESIGN §7.1).
- **LiteLLM** (Python) y el **AI SDK de Vercel** (TypeScript, el que usa
  OpenCode): una interfaz para muchos proveedores, que traduce entre
  formatos como hace `maha`.
- **models.dev:** dice qué paquete del AI SDK sirve cada modelo y sus
  límites; `maha` copia la idea en su catálogo.
- **Claude Code** solo habla el formato de Anthropic y tiene `/effort`;
  **OpenCode** habla varios y llama a sus niveles "variantes".
