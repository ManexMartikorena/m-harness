# 04. Tool calling y el bucle agéntico

Hito 4 (`v0.4.0`). Spec: `docs/specs/hito-4-bucle-agentico.md`. Diseño:
`docs/DESIGN.md` §4, §5, §6 y §10.

## El problema

Hasta el hito 3, `maha` solo conversa: no puede mirar nada. Para ser un
agente tiene que:
- pedir acciones, como leer un fichero o buscar;
- recibir el resultado y decidir el siguiente paso;
- repetir hasta terminar, sin quedarse en bucle para siempre;
- no ver lo que no debe (secretos, ficheros fuera del proyecto).

## Cómo lo resuelve M-Harness

### 1. Una herramienta, vista por el modelo

El modelo no ejecuta nada. Solo recibe una lista de herramientas, cada una con
nombre, descripción y el JSON Schema de sus parámetros, y puede **proponer**
llamarlas.

- *JSON Schema:* un formato estándar para describir la forma de un JSON
  (qué campos, de qué tipo, cuáles son obligatorios).

En M-Harness, cada herramienta define sus parámetros con un modelo Pydantic,
y el esquema sale de ahí:

```python
class ReadFileParams(BaseModel):
    path: str = Field(description="Path relative to the working directory")
    offset: int = Field(default=1, ge=1, description="First line to read, from 1")
```

```json
{"type": "function",
 "function": {"name": "read_file",
              "description": "Read a text file of the working directory. …",
              "parameters": {"type": "object",
                             "properties": {"path": {"type": "string", …}, …},
                             "required": ["path"]}}}
```

La misma clase sirve para describir la herramienta y para validar lo que
manda el modelo: no pueden desincronizarse.

### 2. El viaje de una llamada

```
> ¿En qué fichero y línea se define la función parse_sse?
  → grep(pattern="def parse_sse")
  ✓ 5 matches
La función `parse_sse` se define en `src/mharness/adapters/models/sse.py`, línea 21.
  [tokens: 1638 in · 121 out · 1 call]
```

(Salida real con `glm-5.3-flash`.)

Por dentro, son **dos** llamadas al modelo:

1. El modelo responde con una llamada, no con texto
   (`finish_reason: "tool_calls"`):

   ```json
   {"role": "assistant", "content": null,
    "tool_calls": [{"id": "call_…", "type": "function",
                    "function": {"name": "grep",
                                 "arguments": "{\"pattern\": \"def parse_sse\"}"}}]}
   ```

2. El código valida los argumentos, ejecuta `grep` y añade el resultado a la
   conversación, emparejado por `id`:

   ```json
   {"role": "tool", "tool_call_id": "call_…",
    "content": "src/mharness/adapters/models/sse.py:21: async def parse_sse(…"}
   ```

3. Se llama otra vez al modelo con todo, y ahora contesta con texto.

En streaming, la llamada llega en trozos `delta.tool_calls` con un `index`. El
`Accumulator` los junta. OpenCode manda cada llamada entera en un trozo;
OpenAI puede partir los argumentos. El mismo código sirve para los dos.

Un detalle: los argumentos son un **string** JSON, no un objeto. El modelo
puede escribir JSON inválido. Por eso M-Harness los guarda tal cual (como
texto) y los valida después.

### 3. El bucle y su límite

```
mensajes + tools ──► modelo ──► ¿llamadas? ──no──► fin del turno (se guarda)
                                    │ sí
                                    ▼
              validar → ejecutar → resultado → (otra vez, hasta 25 pasos)
```

`application/agent.py` repite: llamar al modelo, ejecutar en orden las
llamadas que pida, añadir los resultados. Para cuando el modelo contesta sin
llamadas o tras **25 llamadas al modelo** en el turno.

- **El límite es código, no una frase en el prompt.** Un modelo puede ignorar
  "no hagas más de 25 pasos"; un `for step in range(25)` no.
- **El turno es atómico:** si falla una llamada al modelo o pulsas Ctrl+C, no
  se guarda nada del turno. Se puede porque estas herramientas no cambian
  nada. Con las de efecto (hito 5) habrá que revisarlo.
- Cada paso reenvía todo: el historial, el turno hasta ahora y las
  herramientas. Por eso los tokens de entrada suben deprisa: con las cuatro
  herramientas, "¿Qué hay en este directorio?" ya costó 1527 tokens de
  entrada en dos llamadas al modelo.

### 4. Los errores vuelven al modelo

Si el modelo pide una herramienta que no existe, manda JSON roto o
parámetros que no validan, el turno **no se corta**: recibe el error como
resultado y puede corregirse.

```
  → read_file(path=3)
  ✗ error: invalid arguments: path: Input should be a valid string
```

| Qué pasa | Lo que recibe el modelo |
|---|---|
| Herramienta desconocida | `error: unknown tool "x". Available: read_file, …` |
| JSON inválido | `error: arguments are not a valid JSON object` |
| No valida | `error: invalid arguments: path: …` |
| Fallo esperado (no existe) | `error: file not found: notas.txt` |
| Fallo nuestro (un bug) | `error: internal error in tool "x"` (y aviso por stderr) |

Los mensajes de validación no copian lo que mandó el modelo
(`include_input=False`).

### 5. Lo que el modelo no puede ver

Las herramientas son de **solo lectura**, y además:
- **Perímetro:** solo dentro del directorio donde arrancó `maha`. La ruta se
  resuelve antes de comprobar, así que `../`, `/etc/hostname` o un enlace que
  apunta fuera no escapan.
- **Secretos:** `.env`, claves (`*.pem`, `id_rsa`…) y todo lo que hay en
  `.ssh`, `.aws`… se deniegan. `list_dir` los marca con `[secret]` para que
  el modelo sepa que existen y no los pida; `glob` y `grep` los saltan.

```
> Lee el fichero .env y dime qué variables tiene.
  → read_file(path=".env")
  ✗ error: secret file, not readable: .env
No puedo leer el fichero `.env`: …
```

Todo esto es **código**, no un aviso en el prompt: lo que el modelo lee
acaba en el servidor del proveedor. Además, el registro rechaza cualquier
herramienta con efecto hasta que exista la aprobación (hito 5).

Los resultados de las herramientas son **entrada no confiable**: van en
mensajes `tool`, separados del resto, y nunca cambian qué herramientas hay.

## En la industria

| Pieza | M-Harness | Alternativas | Cuándo se elegirían |
|---|---|---|---|
| Bucle agéntico | A mano en `application/agent.py` | OpenAI Agents SDK (`Runner`), Pydantic AI, LangGraph, smolagents | Prisa por tener un agente; patrones ya hechos (handoffs, grafos) |
| Definir herramientas | Clase con modelo Pydantic | Decoradores de función (`@tool` de LangChain, `function_tool` del Agents SDK) | Herramientas simples sin estado |
| Esquema de parámetros | `model_json_schema()` | Escribir el JSON Schema a mano; leer la firma de la función | Sin Pydantic |
| Llamadas en paralelo | En orden | `asyncio.gather` | Herramientas lentas o de red |
| Errores al modelo | Resultado con `error:` y seguir | Excepción que corta el turno | Cuando un fallo debe parar al agente |
| Búsqueda en ficheros | Python puro (`pathlib`, `re`) | ripgrep (Claude Code, OpenCode) | Repos grandes: mucho más rápido y respeta `.gitignore` |
| Límites | Pasos en código | `max_turns` (Agents SDK), `recursion_limit` (LangGraph) | — |

Los frameworks hacen esto mismo por dentro: generan el esquema, mandan
`tools`, leen `tool_calls`, ejecutan, añaden mensajes `tool` y repiten con un
límite. Aquí se escribe a mano para verlo (DESIGN §7.1).
