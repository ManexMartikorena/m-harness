# 03. Streaming: el texto que llega a trozos

Hito 3 (`v0.3.0`). Spec: `docs/specs/hito-3-streaming.md`. Diseño:
`docs/DESIGN.md` §5 y §6.

## El problema

Sin streaming, `maha` espera la respuesta entera y la imprime de golpe. Con una
respuesta larga, la terminal se queda en blanco mucho rato, y no hay forma de
cortar sin matar el programa. Un agente de terminal tiene que:
- mostrar el texto mientras el modelo lo escribe;
- dejar cortar una respuesta sin perder la conversación.

## Cómo lo resuelve M-Harness

### 1. SSE: una respuesta HTTP que no se cierra

Se pide lo mismo que en el hito 2, con dos campos más:

```json
{"model": "glm-5.3-flash",
 "messages": [{"role": "user", "content": "Hola"}],
 "stream": true,
 "stream_options": {"include_usage": true}}
```

El servidor contesta `200` con `Content-Type: text/event-stream` y va mandando
trozos sin cerrar la respuesta. Es SSE:

- *SSE (Server-Sent Events):* un formato de texto para que un servidor mande
  eventos por una respuesta HTTP abierta. Cada evento son líneas `data:` y
  acaba en una línea en blanco.

```
data: {"choices":[{"delta":{"content":"Hola, "}}]}

data: {"choices":[{"delta":{"content":"Ane."},"finish_reason":"stop"}]}

data: {"choices":[],"usage":{"prompt_tokens":18,"completion_tokens":31}}

data: [DONE]
```

(Abreviado; datos inventados.)

`adapters/models/sse.py` lo analiza a mano, en unas 40 líneas. Dos detalles
que no se ven a simple vista:
- **Un evento llega partido entre dos lecturas de red**, a veces a mitad del
  JSON. El analizador guarda lo que falta hasta que llega el resto.
- **Las líneas se parten solo en `\r\n`, `\n` o `\r`.** `str.splitlines()` de
  Python parte también en U+2028 y otros caracteres, que pueden venir dentro
  de un JSON válido. Usarlo rompería respuestas solo con ciertos textos.

### 2. De los trozos a eventos propios

El núcleo no ve SSE ni JSON. El adaptador traduce cada trozo a un evento del
dominio (`domain/events.py`):

```python
TextDelta(text="Hola, ")
TextDelta(text="Ane.")
MessageEnd(
    stop_reason="end_turn",
    usage=Usage(input_tokens=18, output_tokens=31),
    model="glm-5.3-flash",
)
```

- `MessageEnd` sale **una vez, al final**: el `finish_reason` llega en un trozo
  y el `usage` en otro posterior. `MessageEnd` junta los dos.
- El `usage` llega el último, en un trozo con `choices` vacío. En OpenAI solo
  llega si se pide con `include_usage`; OpenCode lo manda siempre.

Quien necesita la respuesta entera la monta con `collect()`:

```python
response = await collect(client.stream(request))
```

El puerto ofrece las dos formas: `stream()` y `complete()` (decisión del
mantenedor).

### 3. Lo que puede salir mal a mitad

Un stream puede fallar después de haber mandado texto. Cada caso se traduce a
los errores del hito 2:

| Qué pasa | Error |
|---|---|
| Error HTTP antes del primer trozo | El del código (401 → `ModelAuthError`…) |
| Un 200 que no es un stream | `ModelResponseError` |
| Un trozo ilegible | `ModelResponseError` |
| Un trozo con un objeto `error` | `ModelUnavailableError` |
| Se corta la red, aunque ya llegara el `finish_reason` | `ModelUnavailableError` |
| El stream acaba sin `finish_reason` | `ModelResponseError` |

El texto que ya salió se queda en pantalla, pero **el turno no se guarda**:
`Chat.stream()` solo guarda el turno al recibir `MessageEnd`. La conversación
queda como estaba y se puede repetir.

```
> Cuéntame algo
Había una vez un
error: the connection to the provider failed: ReadError
>
```

### 4. Cancelar con Ctrl+C

Ctrl+C a mitad de respuesta corta esa respuesta y vuelve al prompt. En el
prompt, Ctrl+C cierra `maha` (código 130).

```
> Escribe los números del 1 al 60
uno, dos, tres, … cuarenta y ocho, cu^C
  [interrupted]
>
```

Cómo funciona, con `asyncio`:
1. Ctrl+C manda la señal SIGINT. El manejador la anota y cancela la tarea
   principal: `task.cancel()`.
2. En el siguiente `await`, la tarea recibe un `CancelledError`. Sube por el
   `async with` de httpx, que cierra la conexión: el servidor deja de
   generar.
3. `_answer` captura ese `CancelledError` solo si lo provocó Ctrl+C, y llama
   a `task.uncancel()` para que `asyncio` deje de tratar la tarea como
   cancelada. Escribe `[interrupted]` y sigue.

- *`uncancel()`:* retira una petición de cancelación de una tarea. Sin él, la
  tarea seguiría marcada y la siguiente espera podría fallar.

Hasta el hito 5, el modelo **no** recordaba la respuesta cortada. Desde el
hito 6 (`v0.6.0`) se guarda, marcada como cortada, y el modelo sabe que no
terminó (nota 06, punto 4).

### 5. Los tokens de más: el razonamiento

"Responde solo con OK" puede costar 48 o 99 tokens de salida. No es un error:
`glm-5.3-flash` **razona** antes de contestar, y ese razonamiento se factura
como salida.

```json
"usage": {"prompt_tokens": 20, "completion_tokens": 46,
          "completion_tokens_details": {"reasoning_tokens": 43}}
```

En el stream, el razonamiento llega en `delta.reasoning_content`, un campo que
OpenAI no documenta. `maha` lo ignora por ahora; el desglose y el coste son
del hito 7.

### 6. El silencio inicial y el spinner

Con OpenCode Go hay unos 5 s de silencio antes del primer byte. Para que no
parezca colgado, gira un spinner con "maha", cada letra en un color:

```
⠋ maha   →   ⠙ maha   →   ⠹ maha   …   (los colores avanzan como una ola)
```

- Es una tarea de `asyncio` aparte que redibuja la línea cada 0,1 s con `\r`.
  Se para con el primer evento, y `\r\x1b[2K` borra la línea antes del
  texto.
- Los colores son códigos de escape ANSI escritos a mano (`\x1b[31m` es rojo).
  Rich llega en el hito 19.
- Solo se dibuja si la salida es una terminal (`isatty()`). Con
  `maha < notas.txt > salida.txt`, el fichero queda limpio.
- Con la variable `NO_COLOR` (convención de https://no-color.org), gira sin
  colores.

## En la industria

| Pieza | M-Harness | Alternativas | Cuándo se elegirían |
|---|---|---|---|
| Streaming del modelo | httpx + SSE a mano | SDK oficial del proveedor (p. ej. `openai`); LiteLLM | SDK: un solo proveedor y prisa. LiteLLM: muchos proveedores sin escribir adaptadores |
| Analizador SSE | A mano (~40 líneas) | Librerías de SSE de terceros | Cuando haga falta reconexión o `Last-Event-ID` |
| Eventos del modelo | Unión de tipos propios | Los tipos del SDK de cada proveedor | Cuando no se piensa cambiar de proveedor |
| Cancelación | `Task.cancel()` desde SIGINT | `KeyboardInterrupt` en código síncrono | Código síncrono |
| Tokens en streaming | `stream_options.include_usage` | Contar con un tokenizador | Cuando el proveedor no informa de `usage` |
| Spinner y colores | ANSI a mano | Rich, yaspin, Halo | En cuanto la interfaz crece (hito 19) |
| Tests de streaming | respx con respuestas SSE simuladas | Servidor local de pruebas; VCR.py | Fijar respuestas reales |

Los SDK hacen esto mismo por dentro: abren la respuesta, parten el SSE, y
entregan objetos "chunk" que se recorren con `for` o `async for`. Aquí se
escribe a mano para verlo (DESIGN §7.1).
