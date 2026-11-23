Estado: PROPUESTA (2026-11-16) → APROBADA (2026-11-16, por el humano, con
las 12 decisiones de §11 y el recorte de lo que no hace el producto más
competitivo)

# Spec — Hito 11: Contexto virtual

Referencias: `docs/DESIGN.md` §4 (pieza 7: "antes de cada llamada: si no
cabe, se compacta"), §5 (sesión), §8 (system prompt fijo por sesión), §9
(evals), §10 (entrada no confiable) y §14 (hito 11, P6);
`docs/ANALISIS.md` §5 (pieza 7) y criterio 8; `docs/COMPARATIVA.md` §9;
specs 4 (§12.14, tokens de las herramientas), 6 (§5 y riesgos: sesiones
que no caben; la marca `[interrupted by the user]`), 8 (§1.1 topes; §11.8,
tareas con historial previo), 9 (§1.6 `max_tokens`; caché del prompt) y 10
(decisión 6, `AGENTS.md` de subcarpetas; §5, `todo_write`; §1.12, el
modelo pequeño); la auditoría tras el hito 10 ("A su hito": `grep` con
contexto o solo ficheros, la política de versiones del formato de sesión y
subir el tope de pasos); `AGENTS.md`.

*(El hito se llamaba "Gestión del contexto". Pasa a "Contexto virtual" por
decisión del mantenedor, 2026-11-16: el arnés tiene que ser barato con
cualquier modelo, también con sesiones enormes. DESIGN §14 se corrige en
el mismo PR.)*

## 0. Alcance

**El problema.** `maha` manda la conversación entera en cada llamada y no
sabe cuánto ocupa. En un agente eso pesa el doble: en cada paso se
**reenvía todo**, así que lo que entra una vez se paga en todos los pasos
siguientes. Una sesión larga se vuelve cara con cualquier modelo, el
modelo trabaja peor con tanto texto viejo, y al final el proveedor la
rechaza (`context_full`) y la sesión ya no sirve.

**Lo que hace este hito.** El modelo ve siempre una **ventana de trabajo
de tamaño fijo** (100.000 tokens por defecto, para todos los modelos): lo
fijo, un índice de lo anterior y los últimos pasos tal cual. Lo que sale
de esa ventana no se borra: va a un **archivo de la sesión en SQLite**,
con búsqueda por texto. Un **modelo barato hace de archivero**: resume lo
que se archiva y mantiene el índice. El modelo bueno tiene una
herramienta, **`recall`**, para recuperar del archivo justo lo que
necesite. Así cada llamada cuesta casi lo mismo, aunque la sesión tenga un
millón de tokens.

```
 Modelo de la sesión                     Modelo barato (archivero)
 ┌─────────────────────────────┐         ┌───────────────────────────┐
 │ system prompt + herramientas│         │ al pasar del presupuesto: │
 │ índice de lo archivado      │◄─índice─│ resume lo que sale de la  │
 │ últimos pasos, tal cual     │         │ ventana y rehace el índice│
 └─────────────┬───────────────┘         └────────────┬──────────────┘
               │ recall("test del IVA")               │
               ▼                                      ▼
        ┌──────────────────────────────────────────────────┐
        │ archivo de la sesión: SQLite + FTS5              │
        │ mensajes · resultados enteros · resúmenes        │
        └──────────────────────────────────────────────────┘
```

**Términos.**
- **Token:** el trozo de texto con el que cuenta un modelo (en inglés,
  unos 4 caracteres).
- **Ventana de contexto:** cuántos tokens caben en una llamada, prompt y
  respuesta juntos. Sale del catálogo (`context`).
- **Presupuesto de trabajo:** lo máximo que `maha` manda al modelo en una
  llamada. Fijo y el mismo para todos los modelos (100.000), salvo que la
  ventana del modelo sea menor.
- **Archivar:** sacar los pasos más viejos de lo que se manda, guardarlos
  en el archivo y dejar en su lugar un índice.
- **Archivo:** una base SQLite por sesión, con FTS5 (la búsqueda por
  texto de SQLite, de la biblioteca estándar de Python).
- **Archivero:** el modelo barato que resume lo que se archiva.
- **Índice:** el texto corto, siempre visible, que dice qué hay en el
  archivo.
- **Paso:** un mensaje de la persona, o una respuesta del modelo con sus
  resultados de herramientas. Se archiva por pasos enteros: una llamada
  nunca queda sin su resultado.
- **Caché del prompt:** el proveedor cobra a un 10 % la parte del
  principio de la petición que ya vio (§1.0). Solo funciona si ese
  principio no cambia.

Dentro de alcance:
- **El principio del arnés barato** (§1.1): parte fija acotada con un
  test, tope por resultado, prefijo estable y presupuesto fijo.
- **Conteo** (§1.2), **presupuesto** (§1.3) y `max_tokens` por llamada
  (§1.4).
- **El archivo** (§1.5), **las salidas grandes** (§1.6), **el archivero**
  (§1.7), **lo que ve el modelo** (§1.8) y **`recall`** (§1.9).
- **Cuándo** se archiva (§1.10), también a mitad de turno y cuando el
  proveedor dice que no cabe.
- **`/compact [instrucciones]`** y **`/context`** (§1.11).
- **La sesión** y **la política de versiones del formato** (§1.12).
- **La caché del prompt en los dos formatos** (§1.13).
- **`AGENTS.md` de subcarpetas** (§1.14), **`grep` con contexto y solo
  ficheros** (§1.15) y **el tope de pasos** (§1.16).
- **Trazas y `-p`** (§1.17).
- **Evals** (§5): tareas con historial previo (con la marca
  `[interrupted by the user]`), tareas largas con un presupuesto pequeño
  donde hay que recuperar lo archivado, y otra medida de `todo_write`.
- Nota 11 de la guía: el contexto virtual.

**Fuera de alcance** (y por qué):
- **La órbita larga** (`run_plan`: el modelo da varios pasos con su
  resultado esperado, y el código los ejecuta y solo vuelve al final o si
  algo no sale como se esperaba): es otra palanca de coste, pero toca el
  bucle, no el contexto. **Hito 12 nuevo**, por decisión del mantenedor
  (2026-11-16); los hitos 12 a 23 pasan a ser los 13 a 24 (DESIGN §14).
- **Code Mode** (el modelo escribe código que llama a las herramientas,
  §1.0): necesita un sandbox; tras el hito 16 (sandbox).
- **Buscar herramientas bajo demanda** (*tool search*, §1.0): con 10
  herramientas no compensa; entra con MCP (hito 18), cuando haya muchas.
- **Memoria entre sesiones:** hito 15. Usará el mismo adaptador SQLite.
- **La compactación del proveedor** (Anthropic, §1.0): es de un solo
  formato y haría una pieza del agente fuera de `maha` (DESIGN §7.1).
- **Un tokenizador local:** cada familia cuenta a su manera, y el
  proveedor ya da la cifra exacta de cada llamada (§1.2).
- **Archivar en segundo plano** antes de llegar al presupuesto (para que
  la persona no espere): mejora posible, si en el uso se nota la espera.
- **La barra de estado:** hito 22 (TUI). Aquí, `/context` y una línea al
  archivar.
- **Hooks antes y después de archivar:** hito 19. Este hito deja el
  evento.
- **Deshacer** y **bifurcar:** hito 13.

## 1. Decisiones de fondo

### 1.0 Hechos comprobados (2026-11-16)

Leídos en la documentación oficial y en el código. OpenCode: `dev` (V2,
commits `8bb7fab` y `b083c4d`) y el tag `v1.19.5` (V1); Codex: commits
`95946fa` y `cd18053`; Hermes Agent: commit `611f0ab`.

**Cómo hacen barato el arnés los demás**

| Hecho | Fuente |
|---|---|
| Prompt base de OpenCode: 756 bytes; añadidos por familia de 300 B a 8,7 KB. Instrucciones base de Codex: 20.903 bytes | OpenCode `core/session/runner/prompt/system.txt`, `core/plugin/system-prompt/`; Codex `protocol/src/prompts/base_instructions/default.md` |
| Claude Code carga bajo demanda las herramientas de MCP (`ENABLE_TOOL_SEARCH`) y las skills, y pide `CLAUDE.md` de menos de 200 líneas | https://code.claude.com/docs/en/mcp, `/costs` |
| *Tool search* de Anthropic (`defer_loading`): con 5 servidores MCP, unos 55.000 tokens de definiciones bajan más del 85 %; la elección pierde precisión pasadas 30-50 herramientas | https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool |
| Topes de resultados. Claude Code: unos 30.000 caracteres de un comando (el resto, a un fichero), 25.000 tokens por lectura. OpenCode: 2.000 líneas o 50 KiB (el resto, a un fichero con su ruta). Codex: 10.000 tokens, principio y final | https://code.claude.com/docs/en/tools-reference; OpenCode `core/tool-output.ts`, `core/shell.ts`; Codex `utils/string/src/truncate.rs` |
| Caché de Anthropic: lectura a 0,1x, escritura a 1,25x (5 min) o 2x (1 h); orden herramientas → system → mensajes; cambiar las herramientas la invalida entera | https://platform.claude.com/docs/en/build-with-claude/prompt-caching |
| Caché de OpenAI: automática por prefijo, desde 1.024 tokens; `prompt_cache_key` ayuda a que las peticiones de una sesión caigan en el mismo sitio | https://developers.openai.com/api/docs/guides/prompt-caching |
| OpenCode manda `promptCacheKey` = id de sesión; marca la caché de Anthropic en la última herramienta, el system y la cola | OpenCode `core/session/model-request.ts`, `packages/ai/src/cache-policy.ts` |
| Claude Code no reescribe lo ya enviado: tras editar un fichero añade un aviso al final, para no romper la caché | https://code.claude.com/docs/en/prompt-caching |
| Claude Code: "`/clear` costs nothing"; compactar es en sí una petición grande | https://code.claude.com/docs/en/costs |

**Contexto que se archiva y se recupera**

| Hecho | Fuente |
|---|---|
| Hermes Agent guarda todas las sesiones en SQLite con FTS5; `session_search` busca y lee mensajes de la base **sin modelo** ("no LLM"), 2.000 caracteres por mensaje como mucho | Hermes `hermes_state_fts.py`, `tools/session_search_tool.py` |
| Hermes comprime con **un modelo auxiliar barato** (`auxiliary.compression`); empieza al 50 % de la ventana (75 % en las de menos de 512K); protege los 3 primeros turnos y los 20 últimos mensajes; el resumen, 12K tokens como mucho | Hermes `agent/context_compressor.py`, `cli-config.yaml.example` |
| Hermes congela su memoria en el system prompt al empezar la sesión, para conservar la caché | Hermes `website/docs/user-guide/features/memory.md` |
| MemGPT: contexto principal fijo + almacén de mensajes donde buscar; aviso al 70 %, y al 100 % archiva la mitad y rehace un resumen recursivo | https://arxiv.org/abs/2310.08560 |
| MemGPT recupera lo olvidado: con GPT-4, del 32,1 % al 92,5 %. Fallo visto: el modelo deja de buscar antes de tiempo | mismo artículo, tabla 2 |
| Anthropic recomienda compactar, notas estructuradas, recuperar "justo a tiempo" (rutas, grep) y "lo más simple que funcione"; borrar resultados viejos es "the safest lightest touch" | https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents |

**Compactar en Claude Code, OpenCode y Codex**

| Hecho | Fuente |
|---|---|
| OpenCode cuenta con el uso de la última respuesta y estima lo que va después con caracteres / 4 | OpenCode `core/session/compaction.ts` (`estimatePrompt`), `util/token.ts` |
| OpenCode V2 compacta en `ventana − max(15 %, 16.000)`; conserva unos 15.000 tokens recientes; resume con el modelo de la sesión (o `agents.compaction.model`); repite una vez la llamada que el proveedor rechaza por larga | https://opencode.ai/docs/compaction |
| OpenCode V1 podaba resultados viejos (protegía 40.000 tokens, solo si liberaba 20.000); la V2 lo quitó | `v1.19.5` `session/compaction.ts`; https://opencode.ai/docs/migrate-v1 |
| Codex compacta en `min(configurado, 90 % de la ventana)` y conserva los mensajes de la persona hasta 20.000 tokens | Codex `protocol/src/openai_models.rs`, `core/src/compact.rs` |
| Claude Code: `/compact [instrucciones]`; tras compactar vuelve a meter el system prompt y el `CLAUDE.md` raíz; los de subcarpetas se recargan al leer allí; `/context` por partes | https://code.claude.com/docs/en/context-window, `/commands` |
| OpenCode carga los `AGENTS.md` entre el fichero leído y el directorio de trabajo, una vez (otra tras compactar), en un mensaje aparte; Claude Code, al leer, escribir o editar | https://opencode.ai/docs/instructions; https://code.claude.com/docs/en/memory |

**Errores de las APIs**

| Hecho | Fuente |
|---|---|
| Anthropic: un prompt que no cabe da 400 `invalid_request_error` ("prompt is too long"); en sus modelos recientes, prompt + `max_tokens` por encima de la ventana se acepta y la respuesta para con `model_context_window_exceeded` | https://platform.claude.com/docs/en/build-with-claude/context-windows |
| OpenAI: "the prompt and the generated output combined must be no more than the model's maximum context length"; Chat Completions no tiene endpoint para contar tokens | https://developers.openai.com/api/docs/concepts |

**Comprobado en el puesto:** el Python de `maha` (3.14.8) trae SQLite
3.53.1 con FTS5. No hace falta ninguna dependencia nueva.

**Sin comprobar** (POR VERIFICAR al implementar, con llamadas reales a
OpenCode Go): qué error exacto da el formato de OpenAI cuando el prompt no
cabe; si rechaza prompt + `max_tokens` por encima de la ventana; si acepta
`prompt_cache_key`.

### 1.1 El principio: barato con cualquier modelo

No se ajusta a un modelo: se acota lo que el arnés manda. Cuatro reglas,
cada una con su test:

1. **La parte fija, acotada.** System prompt base y herramientas no pasan
   de **3.500 tokens** estimados. Medido hoy (2026-11-16): base unos 700,
   herramientas unos 1.960 (9 herramientas, 7.840 caracteres). Un test lo
   fija: si un cambio lo pasa, el CI falla y lo decide el mantenedor. Las
   instrucciones del proyecto (`AGENTS.md`) no cuentan: son de la persona
   y ya tienen su tope (spec 10, 64 KiB).
2. **Cada resultado, con tope** (§1.6). Ninguna herramienta mete más de
   **40.000 caracteres** (unos 10.000 tokens, como Codex) de una vez.
3. **El principio de la petición no cambia** (§1.13). Lo fijo va primero
   y nunca se reescribe lo ya enviado, salvo al archivar.
4. **Presupuesto de trabajo fijo** (§1.3): 100.000 tokens como mucho por
   llamada, con cualquier modelo.

### 1.2 Contar: el uso del proveedor, y una estimación de lo nuevo

```
último input_tokens + último output_tokens   (exacto, del proveedor)
+ estimación de lo añadido después           (resultados, mensaje nuevo)
```

- **Lo exacto, del proveedor.** `input_tokens` cuenta todo el prompt,
  caché incluida (DESIGN §5), con el tokenizador real del modelo.
- **Lo nuevo, estimado:** caracteres / 4, redondeando hacia arriba, en
  `domain/context.py`. Como OpenCode (§1.0).
- **Sin llamada previa** (sesión nueva o recién retomada, o tras
  archivar): todo estimado.

```python
# domain/context.py
def estimate(text: str) -> int:
    return -(-len(text) // 4)
```

*Descartados:* un tokenizador por familia (dependencias, modelos sin
tokenizador público) y `count_tokens` de Anthropic (una llamada más por
paso, y de un solo formato).

### 1.3 El presupuesto de trabajo

```
ventana   = la del catálogo (desconocida: la del presupuesto)
reserva   = max(15 % de la ventana, 16.000)       como OpenCode V2 (§1.0)
techo     = min([context] budget, ventana − reserva)
```

- **Se archiva cuando la próxima llamada pasaría del techo.**
- **`[context] budget`, 100.000 por defecto**, igual para todos los
  modelos (decisión del mantenedor, 2026-11-16). En un modelo de 1M de
  ventana, `maha` nunca manda más de 100.000; en uno de 64.000, el techo
  es 48.000.
- **Por qué fijo:** el precio de una llamada crece con lo que se manda, y
  en un agente cada paso reenvía todo. Con un techo fijo, un paso cuesta
  lo mismo en el minuto 1 que en la hora 5. Algunos modelos además
  cambian de tramo de precio pasado un tamaño (el catálogo lo tiene,
  `tiers`).
- **Tras archivar** se manda: lo fijo, el índice (§1.8) y la **cola**, los
  últimos pasos enteros que quepan en el **30 %** del techo. Así se
  archiva cada 60.000-70.000 tokens nuevos, no en cada paso.

```toml
# ~/.config/maha/config.toml o .maha/config.toml
[context]
budget = 100_000         # tokens por llamada, como mucho
archivist_model = "…"    # opcional; por defecto, small_model (§1.7)
```

### 1.4 `max_tokens` por llamada

Hoy cada petición lleva `max_tokens = max_output` del catálogo (spec 9,
§1.6), que en algunos modelos es la ventana entera. La regla de OpenAI
dice que prompt y respuesta juntos no pasan de la ventana (§1.0).

- **Desde este hito:** `max_tokens = min(max_output, ventana − tamaño
  estimado del prompt)`. Por debajo del techo siempre queda al menos la
  reserva.
- Cierra el pendiente "el tope de cada llamada sigue para el hito 11"
  (DESIGN §5, 27/10/2026).

### 1.5 El archivo de la sesión

- **Un SQLite por sesión**, en
  `~/.local/state/maha/archive/<id-de-sesión>.db`, con permisos `0600`,
  como las sesiones (spec 6). Con `sqlite3` de la biblioteca estándar,
  desde un hilo (`asyncio.to_thread`): el bucle no se bloquea.
- **Es un índice, no la fuente.** La fuente sigue siendo el JSONL de la
  sesión (spec 6). El archivo se puede borrar o romper y se rehace desde
  el JSONL. Es la "caché local" de la sesión.
- **Qué guarda:**

  ```sql
  items(id, step, role, tool, text)            -- cada mensaje y resultado, entero
  items_fts USING fts5(text, content=items)    -- búsqueda por texto
  chunks(id, first_step, last_step, summary)   -- lo que escribió el archivero
  ```
- **Se borra con la sesión** (`/delete`, `maha sessions delete`).
- **Datos sensibles:** guarda lo mismo que el fichero de la sesión (ya en
  disco, `0600`, fuera del repo). Nada nuevo sale de la máquina.
- **Arquitectura:** puerto `ContextArchive` (`ports/archive.py`), con
  `add(items)`, `search(query, limit)`, `read(id, offset, limit)` y
  `rebuild(messages)`; adaptador `adapters/storage/archive_sqlite.py`; un
  fake en memoria para los tests. El hito 15 (memoria) reutiliza el
  adaptador.

### 1.6 Las salidas grandes, al archivo desde el principio

Es la palanca más grande (§1.0): lo que entra una vez se reenvía en cada
paso. En vez de podar después (rompe la caché), se acota al entrar.

- **Tope común: 40.000 caracteres por resultado** (unos 10.000 tokens),
  en `domain/context.py`. Hoy: `read_file` hasta 100.000, `run_command`
  30.000, `grep` unos 30.000.
- **Lo que pasa del tope se guarda entero en el archivo**, y el modelo ve
  el principio, el final y cómo pedir el resto:

  ```
  …primeras líneas…
  … [output cut: 182,340 characters; the whole output is archived as
  out-17; read it with recall(id="out-17", offset=…)]
  …últimas líneas…
  ```
- **`read_file`** no lo necesita: el fichero está en disco y ya lee por
  partes (`offset`). Su tope baja de 100.000 a 40.000 caracteres.
- **`run_command`**, `grep`, `glob` y `list_dir`: principio y final (en
  la salida de un comando, el final es lo que dice qué falló).
- *Descartada:* la poda de resultados viejos (OpenCode V1, Claude Code,
  §1.0). Con el tope al entrar aporta poco, y cada poda reescribe lo ya
  enviado y rompe la caché. OpenCode V2 la quitó.

### 1.7 El archivero

- **Quién:** `[context] archivist_model`; si no hay, `small_model` (el del
  catálogo por proveedor, spec 10, §1.12); si no hay, el de la sesión.
  Como el compresor de Hermes (§1.0). Si la ventana del archivero es menor
  que lo que tiene que leer, lo lee por partes.
- **Qué recibe:** el índice anterior y los pasos que salen de la ventana,
  delimitados como entrada no confiable (`<conversation>`): las
  instrucciones que aparezcan ahí (un fichero leído, una web) no se
  siguen, se resumen como datos (DESIGN §10).
- **Qué devuelve:** JSON validado con Pydantic:

  ```json
  {"summary": "Pasos 1-14: …", "index": "…el índice nuevo, ≤ 2.000 tokens…"}
  ```
  El resumen de cada tramo va a `chunks` (se puede buscar) y el índice, a
  la ventana. Se resume de forma recursiva (MemGPT, §1.0): el índice
  nuevo integra el anterior; nunca se vuelve a leer todo lo archivado.
- **Su prompt, en el repo:** `src/mharness/prompts/archive.md`, con
  huecos, como `title.md` (spec 10, §1.3). Pide: lo que pidió la persona,
  decisiones y por qué, lo hecho por fichero, errores y cómo se
  resolvieron, lo pendiente y el siguiente paso; rutas, comandos y errores
  exactos (como la plantilla de OpenCode, §1.0). Es código: se evalúa.
- **Sin herramientas** (`tools = []`), con `complete()`, y `max_tokens =
  4.000`.
- **Si falla** (error del proveedor tras reintentos, JSON no válido dos
  veces): se archiva igual, con un índice que construye el código solo
  (§1.8). Nunca se pierde nada: está en el archivo.
- **Su coste** cuenta en el turno, en la sesión y en los topes del turno,
  como cualquier llamada (`ModelCallFinished`).

### 1.8 Lo que ve el modelo tras archivar

Un mensaje al principio de la conversación, delimitado. Una parte la
escribe el código (exacta) y otra el archivero:

```
<context-archive>
Earlier steps of this conversation are archived. Search or read them
with the recall tool.

What the user asked, in their words:
- "Arregla el redondeo del IVA reducido"
- "Ahora añade un test para el 4 %"

Task list: [x] fix rounding · [ ] add 4 % test
Files changed: tienda/iva.py, tests/test_iva.py

Index (archivist):
Steps 1-14: fixed rounding in tienda/iva.py (round half up) …
</context-archive>
```

| Qué | Quién |
|---|---|
| System prompt, herramientas y permisos de la sesión | Intactos: no son conversación |
| Los mensajes de la persona | El código, tal cual, hasta 20.000 caracteres (los más recientes; como Codex, §1.0) |
| La lista de tareas | El código: la última de `todo_write` |
| Ficheros cambiados | El código: rutas de `write_file` y `edit_file` con éxito |
| El índice | El archivero (§1.7) |
| La cola | Intacta, con sus resultados |
| `AGENTS.md` de subcarpetas | Se olvidan; vuelven al leer allí (§1.14) |

### 1.9 `recall`: recuperar del archivo

Una herramienta de lectura, sin aprobación, siempre registrada (la lista
de herramientas no cambia en la sesión, §1.13):

```
{"query": "test iva 4"}                        buscar: hasta 5 trozos, con su id
{"id": "out-17", "offset": 200, "limit": 100}  leer un resultado o paso, por líneas
```

- **Buscar** usa FTS5, sin modelo (como Hermes, §1.0): es gratis, rápido
  y exacto. Da hasta 5 trozos con su id y su paso, 8.000 caracteres en
  total.
- **Leer** da un elemento archivado por líneas, con el tope común (§1.6).
- **Lo que devuelve va delimitado** como entrada no confiable: es lo que
  dijeron las herramientas.
- **Que el modelo sepa buscar:** el índice siempre está a la vista y una
  línea del prompt base explica cuándo usar `recall`. MemGPT vio que el
  modelo a veces deja de buscar antes de tiempo (§1.0): las evals (§5)
  miden que encuentra lo que necesita.
- Sin archivo todavía, responde "nothing archived yet".

### 1.10 Cuándo se archiva

- **Antes de cada llamada al modelo** (DESIGN §4): al empezar el turno,
  con el mensaje nuevo, y antes de cada paso, con los resultados del
  anterior.
- **También a mitad de turno.** Un turno de agente puede tener 50 pasos;
  se archivan sus pasos viejos igual que los de turnos anteriores. Por
  pasos enteros: una respuesta del modelo y sus resultados van juntos.
- **Si el proveedor dice que no cabe** (`context_full`, o el error de
  contexto excedido, §1.0) aunque la estimación dijera que sí: se archiva
  y se repite la llamada **una vez**. Si vuelve a pasar, el turno acaba
  con `context_full`. Cada adaptador traduce el error de su API a
  `ContextOverflowError`, del dominio: en Anthropic, el 400 "prompt is
  too long"; en el formato de OpenAI se fija al implementar con una
  llamada real (§1.0). Un error que no se reconoce sigue siendo el de hoy.
- **Una vez por paso** como mucho: nunca un bucle de archivar.
- **Atómico:** Ctrl+C o un fallo mientras archiva dejan la conversación
  como estaba.
- **La persona lo ve:** `[archiving 64,210 tokens of earlier steps…]` y
  después `[archived: 98,400 → 31,200 tokens; 0.002 $]`.

### 1.11 `/compact` y `/context`

- **`/compact [instrucciones]`:** archiva ya todo menos la cola, aunque no
  haga falta. Las instrucciones van al archivero (`/compact céntrate en
  el fallo del IVA`). Se llama así porque es el nombre que conocen las
  personas de Claude Code y OpenCode.
- **`/context`:** qué ocupa la ventana de trabajo, por partes, con la
  última cifra exacta y la caché:

  ```
  > /context
  budget 100,000 · window 262,144 · archives at 100,000
  system prompt     2,140   (base 700 · AGENTS.md 1,300 · environment 140)
  tools             2,110   (10 tools)
  archive index         0   (nothing archived)
  messages         61,300   (tool results 48,900)
  total            65,550   65.6 % of budget · last call 64,950 (exact)
  cache            last call 58,200 of 64,950 read from cache (89.6 %)
  ```
- Los dos, solo en la sesión interactiva; en `-p` archiva solo. `/help`
  los lista.

### 1.12 La sesión, y la política de versiones del formato

**Una entrada nueva**, sin reescribir el fichero (spec 6, §1.2):

```python
class ArchiveEntry(BaseModel, frozen=True):
    type: Literal["archive"] = "archive"
    # Cuántos mensajes de la conversación, desde el principio, sustituye.
    replaces: int
    # El mensaje que va en su lugar: el de §1.8.
    index: Message
    manual: bool = False  # /compact
```

- **Al retomar**, `replay()` aplica cada `ArchiveEntry` en su sitio: la
  conversación que vuelve es la de trabajo, y el archivo se rehace si
  falta.
- **`/export` y `maha export`** dan la conversación entera, con una marca
  donde se archivó. Lo que deja de ver el modelo no deja de verlo la
  persona.
- **`check_history`** comprueba también la conversación de trabajo.

**Política de versiones del formato** (pendiente de la auditoría tras el
hito 10):
- **El formato solo crece:** cada versión puede añadir tipos de entrada o
  campos opcionales; nunca cambia el significado de uno que existe.
- **Un tipo desconocido** da `SessionTooNew` ("this session was written by
  a newer maha (X.Y.Z); update maha to open it"), no "corrupto". La
  versión sale de la cabecera (`maha`, ya existe).
- Los `maha` anteriores (≤ 0.10.2) dirán "corrupto" con una sesión
  archivada: va en las notas de la release.

### 1.13 La caché del prompt, en los dos formatos

- **Orden fijo:** herramientas, system prompt, índice, cola. Lo que menos
  cambia, primero.
- **No se reescribe lo enviado**, salvo al archivar (una escritura de
  caché cada 60.000-70.000 tokens, §1.3). Por eso no hay poda (§1.6).
- **La lista de herramientas no cambia en la sesión:** `recall` está
  siempre (§1.9).
- **Formato de Anthropic:** la caché automática de hoy (spec 9, §1.8).
- **Formato de OpenAI:** se manda `prompt_cache_key` = id de sesión, como
  OpenCode (§1.0). Se comprueba con OpenCode Go al implementar. Solo si un
  proveedor lo rechaza se añade al catálogo una forma de apagarlo por
  proveedor; si no, no hay opción nueva. *(Recortado al aprobar, decisión
  13.)*
- **Se mide:** la parte leída de caché de cada llamada, en `/context`, en
  la traza y en el informe de `maha eval`.

### 1.14 `AGENTS.md` de subcarpetas

Hoy se cargan, en el system prompt, los de la raíz git hasta el directorio
de trabajo (spec 10, §1.4). Los de más abajo no se ven nunca.

- **Cuándo:** la primera vez que `read_file`, `edit_file` o `write_file`
  toca un fichero de una carpeta con un `AGENTS.md` (o `CLAUDE.md`, con
  `compat_claude`) entre ella y el directorio de trabajo que aún no se ha
  cargado. Como Claude Code (§1.0).
- **Dónde:** al final del resultado de esa herramienta, delimitado:

  ```
  <instructions source="packages/api/AGENTS.md">
  Los tests de este paquete se lanzan con `make test`.
  </instructions>
  ```
  No en el system prompt: cambiarlo rompe la caché (§1.13). OpenCode lo
  manda en un mensaje aparte; al final del resultado es más simple y no
  añade mensajes al turno.
- **Una vez por sesión**; tras archivar se olvidan y vuelven al leer allí.
- **Las mismas reglas** que spec 10: dentro del proyecto, sin secretos,
  sin enlaces fuera, UTF-8 y el tope de 64 KiB contando todos.
- **Arquitectura:** el puerto `ProjectInfo` gana `nested(path)`; cada
  herramienta dice qué ruta tocó (`touched(params) -> str | None`, nuevo en
  el puerto `Tool`); el bucle añade lo que dé `nested()`. Ningún adaptador
  importa otro.

### 1.15 `grep` con contexto y solo ficheros

Pendiente de la auditoría tras el hito 10. Dos parámetros nuevos:

```json
{"pattern": "def total", "context": 2}
{"pattern": "TODO", "output": "files"}
```
- `context` (0 a 10, 0 por defecto): líneas de antes y después. Evita
  leer el fichero entero para ver una función.
- `output`: `"lines"` (por defecto), `"files"` (solo rutas) o `"count"`.
  Claude Code da solo ficheros por defecto (§1.0); aquí se mide antes de
  cambiar el valor por defecto (§5).

### 1.16 El tope de pasos

Hoy 25 llamadas por turno (spec 8, §1.1), bajo porque un turno largo
llenaba el contexto. Con el presupuesto fijo ya no pasa, y el coste de
cada paso queda acotado.

- **Propuesta: 50**, confirmado con las tareas largas de §5. Se cambia en
  `[limits] max_steps`, como hoy. Los demás topes no cambian.

### 1.17 Trazas, eventos y `-p`

- **Eventos nuevos** (`domain/agent_events.py`): `ContextArchiving(before)`
  y `ContextArchived(before, after, steps, manual)`. El hito 19 (hooks) los
  usará.
- **La traza** los apunta, con el coste del archivero en su
  `ModelCallFinished`, y la parte de caché de cada llamada.
- **`maha -p`** archiva solo, igual que la sesión interactiva. La salida
  JSON no cambia: cuántas veces se archivó está en la traza. *(Recortado
  al aprobar, decisión 13.)*

## 2. En la industria

| Enfoque | Qué hace | Cuándo se elegiría |
|---|---|---|
| **Compactar por resumen** (Claude Code, OpenCode, Codex) | El modelo de la sesión resume todo y se sigue desde el resumen | Lo más probado; lo viejo se pierde para el modelo |
| **Contexto virtual** (MemGPT/Letta, Hermes Agent) | Ventana fija, lo viejo a un almacén con búsqueda, y una herramienta para recuperarlo | Sesiones muy largas con coste acotado: es lo de `maha` |
| **Poda de resultados** (OpenCode V1, Claude Code) | Borra salidas viejas, sin modelo | Barato, pero rompe la caché |
| **Ventana deslizante** (LangChain `trim_messages`) | Quita lo más viejo | Chats sin herramientas |
| **Del proveedor** (Anthropic *context editing* y *compaction*) | La API poda o resume | Con un solo proveedor |
| **Memoria con fichero** (herramienta *memory* de Anthropic) | El modelo escribe notas en ficheros y las lee | Entre sesiones: hito 15 |
| **Tokenizador local** (`tiktoken`) | Cuenta exacto antes de llamar | Con un solo proveedor |

## 3. Diseño de detalle

### 3.1 Ficheros

| Fichero | Capa | Qué |
|---|---|---|
| `domain/context.py` (nuevo) | domain | `estimate()`, `ContextPolicy` (ventana, reserva, techo, cola), `fit()` (tope con principio y final), elegir los pasos que se archivan y el índice del código (§1.8). Puro, sin E/S |
| `domain/archive.py` (nuevo) | domain | `ArchivedItem`, `Hit`, `ArchiveSummary` (lo que devuelve el archivero) |
| `domain/errors.py` | domain | `ContextOverflowError` |
| `domain/session.py` | domain | `ArchiveEntry`, `SessionTooNew`, `replay()` |
| `domain/agent_events.py`, `domain/trace.py` | domain | Los eventos y registros de archivar |
| `domain/limits.py` | domain | `MAX_STEPS = 50` |
| `ports/archive.py` (nuevo) | ports | `ContextArchive` |
| `ports/tools.py`, `ports/project.py` | ports | `touched()`, `nested()` |
| `application/context.py` (nuevo) | application | `Archivist`: decide, llama al archivero, guarda y construye el índice |
| `application/agent.py` | application | Archivar antes de cada llamada; repetir una vez tras `ContextOverflowError`; `max_tokens`; los `AGENTS.md` de subcarpetas |
| `application/sessions.py` | application | `ArchiveEntry`; rehacer el archivo; `/compact`; los datos de `/context` |
| `adapters/storage/archive_sqlite.py` (nuevo) | adapters | El archivo con `sqlite3` y FTS5 |
| `adapters/tools/recall.py` (nuevo) | adapters | La herramienta `recall` |
| `adapters/tools/files.py`, `shell.py` | adapters | El tope común; `touched()`; `grep` con `context` y `output` |
| `adapters/models/openai_chat.py`, `anthropic.py` | adapters | `ContextOverflowError`; `prompt_cache_key` |
| `adapters/project/local.py` | adapters | `nested()` |
| `adapters/cli/*` | adapters | `/compact`, `/context`, la línea al archivar y la marca en la exportación |
| `adapters/evals/toml_suite.py`, `domain/evals.py`, `application/evals.py` | varias | `history` y `context_budget` en una tarea; la caché en el informe |
| `src/mharness/prompts/archive.md` (nuevo) | — (datos) | El prompt del archivero |
| `src/mharness/prompts/base.md`, `tools.md` | — (datos) | Una línea sobre `recall` y el índice |
| `config.py` | — | `[context]` |
| `bootstrap.py` | — | El cableado |

### 3.2 Configuración nueva

```toml
[context]
budget = 100_000          # §1.3
archivist_model = "…"     # §1.7; opcional
```

Comandos: `/compact [instrucciones]` y
`/context`. Herramienta nueva: `recall`.

## 4. Plan de tests

Con fakes y ficheros temporales; ninguna llamada real.

1. `estimate()`: vacío, ASCII, multibyte; redondea hacia arriba.
2. `ContextPolicy`: techo con ventana grande, pequeña y desconocida;
   reserva del 15 % con mínimo de 16.000; `budget` configurado.
3. **Presupuesto de la parte fija:** base + herramientas ≤ 3.500 tokens
   estimados (§1.1).
4. `max_tokens` por llamada: nunca más que lo que queda.
5. `fit()`: bajo el tope, intacto; encima, principio, final y la marca con
   el id; las herramientas lo aplican.
6. Pasos que se archivan: por pasos enteros, también a mitad de turno;
   la cola en el 30 % del techo; nunca una llamada sin su resultado.
7. Índice del código: mensajes de la persona (los más recientes, 20.000
   caracteres), lista de tareas, ficheros cambiados.
8. `Archivist` con `FakeModelClient`: el JSON válido; uno no válido se
   repite una vez y después usa el índice del código; la llamada no lleva
   herramientas; las instrucciones de `/compact` llegan.
9. Atomicidad: Ctrl+C y error del proveedor dejan la conversación igual.
10. En el bucle: archiva antes de la primera llamada y a mitad de turno;
    una vez por paso; `ContextOverflowError` → archiva y repite una vez;
    la segunda, `context_full`.
11. Coste: el archivero cuenta en el turno, la sesión y los topes.
12. Archivo SQLite (`tmp_path`): añadir, buscar con FTS5, leer por líneas;
    `0600`; borrar con la sesión; rehacer desde los mensajes; uno roto se
    rehace.
13. `recall`: buscar (5 trozos, 8.000 caracteres), leer por id y líneas,
    "nothing archived yet", id desconocido como error al modelo.
14. Sesión: `ArchiveEntry` y `replay()`; retomar da la conversación de
    trabajo; `/export` da todo con la marca.
15. Formato: una entrada de un tipo inventado da `SessionTooNew`; una línea
    rota sigue siendo `SessionCorrupt`.
16. `AGENTS.md` de subcarpetas: una vez; no los del system prompt; tras
    archivar, otra vez; secretos, enlaces y el tope de 64 KiB.
17. `grep`: `context` y `output`; valores fuera de rango, error al modelo.
18. Adaptadores: el error de contexto excedido (respx con el cuerpo
    documentado); `prompt_cache_key` en el formato de OpenAI.
19. `/context` y `/compact` con un prompt y unas herramientas conocidos.
20. `-p` archiva solo; la traza lo apunta.
21. Evals: una tarea con `history` empieza con esa conversación; una con
    `context_budget` usa ese techo.
22. Arquitectura: import-linter en verde; `domain/context.py` sin E/S.

## 5. Evals

El hito toca el bucle, el contexto, dos prompts y una herramienta nueva:
la batería entera.

- **Tareas nuevas** (fixtures inventados):
  - `25-historial-previo` (train): empieza con una conversación anterior
    (`history.jsonl` en la tarea) donde el agente hizo la mitad; la
    instrucción dice "sigue".
  - `26-interrumpido` (train): el historial acaba en una respuesta cortada
    con `[interrupted by the user]` (spec 6, §5) y la persona corrige el
    rumbo.
  - `27-recuperar` (train): con `context_budget = 20_000`, una tarea larga
    donde un dato del principio (un valor que dio un comando) hace falta
    al final: solo está en el archivo. Mide que se archiva y que `recall`
    lo encuentra.
  - `28-tareas-largas` (validation): igual, con una lista de tareas larga;
    mide que la lista sobrevive, y otra vez el uso de `todo_write`
    (pendiente de spec 10).
  - `29-grep-contexto` (train): encontrar y arreglar algo en ficheros
    grandes, donde `grep` con contexto ahorra lecturas.
  - `30-recuperar-detalle` (train): un dato que solo está en lo archivado
    y que el índice no tiene, así que solo `recall` lo encuentra
    *(añadida en el PR 4, decisión 15)*.

  Con ellas, 30 tareas; la validación, 6 de 30 (20 %).
- **Modelos:** los de las líneas base del 2026-11-10, 5 repeticiones. El
  criterio es el mismo para todos: ningún ajuste para un modelo concreto.
- **Aceptación:**
  - sin ⚠ en las 24 tareas de antes, y en ellas no se archiva nunca (lo
    fija la traza): el presupuesto no cambia lo que ya funcionaba;
  - las nuevas, al menos 4/5 en cada modelo;
  - en 27 y 28 se archiva en todas las ejecuciones (si no, no miden nada);
  - **coste por tarea:** igual o menor en las tareas largas; la parte
    leída de caché, anotada por modelo;
  - los pasos de las tareas largas, anotados, para el tope de §1.16.
- **El conjunto de validación no se mira al escribir `archive.md`.**
- **Líneas base nuevas** al final del hito, con la batería de 30.

El resultado se anota aquí al implementar.

### Resultados (PR 1)

2026-11-17, `maha eval --models glm-5.3-flash,kimi-k2.7-code,claude-haiku-5-5
--repeat 5 --retry-errors`, contra las líneas base del 2026-11-10 (24
tareas). El PR 1 cambia lo que se manda (`max_tokens` en el formato de
Anthropic, `prompt_cache_key` en el de OpenAI), no el prompt.

| Modelo | Éxito | Validación | Coste total | Caché leída | Llamadas |
|---|---|---|---|---|---|
| `glm-5.3-flash` | 119/120 | 24/25 | 0,142 $ | 68,0 % | 608 |
| `kimi-k2.7-code` | 118/120 | 24/25 | 0,984 $ | 85,2 % | 660 |
| `claude-haiku-5-5` | 120/120 | 25/25 | 0,593 $ | 70,2 % | 479 |

- **Sin regresiones de éxito**; las bajadas de una tarea, dentro del
  ruido (p = 0,5).
- **El ⚠ de coste de Kimi (+51 %) no es de este PR.** Es el mismo +51 %
  de la auditoría tras el hito 10, por devolverle su razonamiento (R4,
  P8), que el mantenedor aceptó el 2026-11-11; las líneas base son de
  antes. Contra la pasada de `v0.10.2` (2026-11-13), Kimi cuesta menos
  (0,984 $ frente a 1,084 $) con las mismas llamadas (660 frente a 651).
- **`prompt_cache_key` no cambia la caché:** la parte leída de caché de
  cada modelo está en el rango de las pasadas del 10 al 13 de noviembre
  (GLM 67-73 %, Kimi 84,5-86,1 %, Haiku 68,9-71,2 %).
- Las líneas base nuevas, al final del hito (§5).

### Resultados (PR 2)

2026-11-17, la misma orden. El PR 2 añade `recall` (y su guía en
`tools.md`), el tope común y baja `read_file` a 36.000 caracteres.

| Modelo | Éxito | Validación | Coste total | Caché leída | Llamadas |
|---|---|---|---|---|---|
| `glm-5.3-flash` | 116/120 | 25/25 | 0,143 $ | 72,8 % | 601 |
| `kimi-k2.7-code` | 120/120 | 25/25 | 1,024 $ | 87,2 % | 649 |
| `claude-haiku-5-5` | 120/120 | 25/25 | 0,614 $ | 69,8 % | 458 |

- **GLM, `20-total-value` en 2/5** (p = 0,083, "dentro del ruido"). Los
  tres fallos son del modelo: su propio test espera un total que su
  método no da, en 4 pasos con salidas pequeñas; nada se archivó ni se
  usó `recall`. Repetida 10 veces: **9/10 con este PR y 8/10 con `main`
  sin él**; en pasadas anteriores, 3/5 y 4/5. Es ruido de la tarea.
- **Ninguna tarea de la batería archiva** (ninguna salida pasa de 40.000
  caracteres) ni usa `recall`: lo miden las tareas 27 y 28 del PR 3.
- **Coste:** Kimi +4 % y Haiku +4 % frente al PR 1, por la herramienta
  nueva en cada llamada (unos 250 tokens, casi todos de caché). El ⚠ de
  Kimi frente a la línea base es el ya aceptado (PR 1).
- **La pasada completa (10:31-11:19) no lleva `fefbd7e`** (la salida de un
  comando, entera hasta 8.000.000 de caracteres): arrancó antes. Las 10
  repeticiones de la tarea 20 sí lo llevan. Ninguna tarea usa
  `run_command` ni pasa de 40.000 caracteres, así que no cambia nada; el
  mantenedor da la pasada por buena sin repetirla (2026-11-17).

### Resultados (PR 3)

2026-11-17 (15:23-16:49), la misma orden, con 28 tareas (las 24 de
antes y de la 25 a la 28), contra las líneas base del 2026-11-10. El
PR 3 archiva, resume con el modelo barato y añade `/compact`. Una pasada
anterior (12:17) se cortó por un reinicio del PC a las 232 de 420
ejecuciones y no cuenta.

| Modelo | Éxito | Validación | Coste total | Caché leída | Llamadas |
|---|---|---|---|---|---|
| `glm-5.3-flash` | 139/140 | 30/30 | 0,246 $ | 70,1 % | 733 |
| `kimi-k2.7-code` | 136/140 | 29/30 | 1,730 $ | 78,9 % | 791 |
| `claude-haiku-5-5` | 138/140 | 28/30 → 30/30 | 1,080 $ | 59,7 % | 563 |

Solo las 24 tareas de antes, frente al PR 2:

| Modelo | Coste | Caché leída | Llamadas |
|---|---|---|---|
| `glm-5.3-flash` | 0,150 $ (0,143 $) | 73,5 % (72,8 %) | 603 (601) |
| `kimi-k2.7-code` | 1,019 $ (1,024 $) | 87,1 % (87,2 %) | 639 (649) |
| `claude-haiku-5-5` | 0,610 $ (0,614 $) | 69,4 % (69,8 %) | 451 (458) |

Las tareas largas nuevas (media de 5; la caché, de toda la tarea):

| Tarea | Modelo | Pasos | Coste | Caché leída | Archivados |
|---|---|---|---|---|---|
| 27 | `glm-5.3-flash` | 12,0 | 0,0083 $ | 69,1 % | 1 en cada una |
| 27 | `kimi-k2.7-code` | 5,8 | 0,0438 $ | 24,5 % | 2-4 |
| 27 | `claude-haiku-5-5` | 6,6 | 0,0316 $ | 21,6 % | 2-3 |
| 28 | `glm-5.3-flash` | 9,8 | 0,0097 $ | 57,3 % | 1-2 |
| 28 | `kimi-k2.7-code` | 20,4 | 0,0910 $ | 77,7 % | 2 en cada una |
| 28 | `claude-haiku-5-5` | 10,6 | 0,0534 $ | 50,8 % | 3 en cada una |

(La fila de Haiku en la 28 es la de la repetición, más abajo.)

La aceptación de §5, punto por punto:

- **Las 24 de antes, sin ⚠ y sin archivar: se cumple.** Ninguna archiva
  (el informe solo da `archived` en la 27 y la 28). Las bajadas de Kimi
  (04, 08 y 12, de 5/5 a 4/5) son ruido (p = 0,5) y fallos del modelo. El
  único ⚠ es el coste de Kimi (+56 %), el ya aceptado (PR 1): con las 24
  tareas, Kimi cuesta lo mismo que en el PR 2.
- **Las nuevas, al menos 4/5 en cada modelo: se cumple tras la
  repetición.** La 25 y la 26, 5/5 en los tres. La 27: GLM 5/5, Kimi 4/5,
  Haiku 5/5; el fallo de Kimi es un `timeout` a los 300 s con solo 4
  pasos, por la lentitud del proveedor esa tarde. La 28: GLM 5/5, Kimi
  5/5 y **Haiku 3/5**.
- **Los dos fallos de Haiku en la 28 no son del archivo.** Los dos
  escribieron `informes/indice.md` en vez de `indice.md`: todas las demás
  rutas de la instrucción empiezan por `informes/`. Uno lo decidió en su
  primera lista de tareas, antes de archivar nada; en el otro, el índice
  del archivo copiaba tal cual las palabras de la persona («Escribe
  indice.md»). **Decisión del mantenedor (2026-11-17):** la comprobación
  acepta el índice en la raíz o en `informes/`; la instrucción no cambia
  (`eecfc19`). Repetida la 28 con Haiku (17:56): **5/5**, una de ellas con
  el índice en `informes/`. Una repetición anterior con los tres modelos
  (17:00) coincidió con un corte de OpenCode Go (sin datos durante 120 s,
  respuestas que no llegaban) y casi todo quedó en errores del proveedor;
  no cuenta. La 28 de GLM y de Kimi no se repite: ya tenían 5/5 con el
  índice en la raíz, y el cambio solo afloja la comprobación.
- **En la 27 y la 28 se archiva en todas las ejecuciones: se cumple**
  (15/15 en cada tarea).
- **Coste de las tareas largas:** las de antes (12, 23 y 24) no archivan y
  cuestan lo mismo que en la línea base y en el PR 2. La 27 y la 28 no
  tienen con qué compararse; quedan como referencia para la línea base
  del final del hito. Archivar reescribe el principio del prompt y la caché
  se pierde desde ahí: en la 27, Kimi y Haiku leen de caché solo un
  22-25 %.
- **Pasos de las tareas largas, para el tope de §1.16:** como mucho 27
  (Kimi en la 28), con un tope de 40. Ninguna ejecución llega al tope.
- **`recall` casi no se usa:** ninguna vez en la pasada completa, y una
  vez en la repetición de Haiku. La 27 se resuelve sin él porque el índice
  del archivero ya trae el dato. La 27 mide que se archiva y que el dato
  sobrevive, pero no que `recall` lo encuentre. Queda para el PR 4
  (instrucciones y herramientas, §6), a decidir con el mantenedor.

### Resultados (PR 4) y líneas base nuevas

2026-11-23 (12:19-13:55), `maha eval --models
glm-5.3-flash,kimi-k2.7-code,claude-haiku-5-5 --repeat 5 --retry-errors
--save`, con las 30 tareas, contra las líneas base del 2026-11-10. El
PR 4 trae los `AGENTS.md` de subcarpetas (y la línea de `base.md` que dice
seguirlos), `grep` con `context` y `output` (y su línea en `tools.md`),
el tope de 50 pasos y las tareas 29 y 30. Una pasada anterior (12:16) se
paró a los pocos minutos para cambiar `base.md` y no cuenta.

| Modelo | Éxito | Validación | Coste total | Caché leída | Llamadas |
|---|---|---|---|---|---|
| `glm-5.3-flash` | 148/150 | 30/30 | 0,322 $ | 73,1 % | 796 |
| `kimi-k2.7-code` | 148/150 | 29/30 | 1,832 $ | 78,5 % | 828 |
| `claude-haiku-5-5` | 149/150 | 30/30 | 1,230 $ | 60,8 % | 600 |

Solo las 24 tareas de antes, frente al PR 3:

| Modelo | Coste | Caché leída | Llamadas |
|---|---|---|---|
| `glm-5.3-flash` | 0,163 $ (0,150 $) | 79,7 % (73,5 %) | 630 (603) |
| `kimi-k2.7-code` | 1,035 $ (1,019 $) | 86,9 % (87,1 %) | 650 (639) |
| `claude-haiku-5-5` | 0,644 $ (0,610 $) | 69,0 % (69,4 %) | 445 (451) |

Las tareas largas y las nuevas (media de 5; la caché, de toda la tarea):

| Tarea | Modelo | Pasos | Coste | Caché leída | Archivados | `recall` |
|---|---|---|---|---|---|---|
| 27 | `glm-5.3-flash` | 9,8 | 0,0093 $ | 61,9 % | 1-2 | 0 |
| 27 | `kimi-k2.7-code` | 5,4 | 0,0378 $ | 28,2 % | 2 | 0 |
| 27 | `claude-haiku-5-5` | 8,0 | 0,0350 $ | 40,4 % | 2-3 | 0 |
| 28 | `glm-5.3-flash` | 10,6 | 0,0126 $ | 63,6 % | 1-2 | 0 |
| 28 | `kimi-k2.7-code` | 18,0 | 0,0803 $ | 75,8 % | 2 | 0 |
| 28 | `claude-haiku-5-5` | 11,0 | 0,0597 $ | 49,9 % | 3 | 0 |
| 29 | `glm-5.3-flash` | 4,6 | 0,0046 $ | 61,1 % | 0 | 0 |
| 29 | `kimi-k2.7-code` | 4,6 | 0,0237 $ | 64,6 % | 0 | 0 |
| 29 | `claude-haiku-5-5` | 4,2 | 0,0057 $ | 71,6 % | 0 | 0 |
| 30 | `glm-5.3-flash` | 4,0 | 0,0040 $ | 71,2 % | 1 | 1-3 |
| 30 | `kimi-k2.7-code` | 3,4 | 0,0087 $ | 76,8 % | 1 | 1-2 |
| 30 | `claude-haiku-5-5` | 3,8 | 0,0090 $ | 65,5 % | 1 | 1-3 |

La aceptación de §5, punto por punto:

- **Las 24 de antes, sin ⚠ y sin archivar: se cumple.** Ninguna archiva ni
  usa `recall`. Las bajadas de una tarea (GLM en la 13 y la 20, Kimi en la
  08 y la 18, de 5/5 a 4/5) son ruido (p = 0,5) y fallos del modelo; la 20
  de GLM es la misma de los PRs 2 y 3. El único ⚠ es el coste de Kimi
  (+58 %), el ya aceptado (PR 1). Frente al PR 3, las 24 cuestan un 2-9 %
  más: la parte fija creció unos 175 tokens (`grep` y las dos líneas
  nuevas del prompt), y GLM dio 27 llamadas más.
- **Las nuevas, al menos 4/5 en cada modelo: se cumple.** La 29 y la 30,
  5/5 en los tres. De las del PR 3, todas 5/5 salvo la 27 de Haiku, 4/5:
  escribió `informes/resumen.md` en vez de `resumen.md` (archivó dos veces
  y el lote estaba bien), la misma lectura de la ruta que en la 28 (PR 3).
  La comprobación de la 27 no se afloja: no lo ha decidido el mantenedor.
- **En la 27, la 28 y la 30 se archiva en todas las ejecuciones: se
  cumple** (15/15 en cada una).
- **`recall` (decisión 15): se usa en las 15 ejecuciones de la 30**, entre
  una y tres veces, y las 15 dan el código bien. En la 27 y la 28, ninguna
  vez: el índice ya basta.
- **Coste de las tareas largas:** la 12, la 23 y la 24 no archivan, y el
  informe no da ⚠ en ninguna tarea. La 27 y la 28, frente al PR 3: Kimi
  cuesta menos (0,0438 → 0,0378 $ y 0,0910 → 0,0803 $), y GLM y Haiku más
  (GLM 0,0083 → 0,0093 $ y 0,0097 → 0,0126 $; Haiku 0,0316 → 0,0350 $ y
  0,0534 → 0,0597 $), con más archivados en la 28 de GLM y la 27 de
  Haiku. Son 5 ejecuciones por tarea, y la línea base nueva queda como
  referencia. La caché leída de la 27 sube en Kimi y Haiku (del 22-25 %
  al 28-40 %).
- **Pasos, para el tope de §1.16:** como mucho 27 (Kimi en la 28), con un
  tope de 50. Ninguna ejecución llega al tope.
- **`grep` con contexto:** la 29 se resuelve en 4-5 pasos con los tres
  modelos. El valor por defecto de `output` sigue en `lines`.

**`todo_write`, otra vez** (pendiente de spec 10, §5, "Resultados (PR
2)"; de las sesiones de esta pasada): la 28 lo usa en 15/15 y la 23 en
10/15 (GLM y Kimi siempre, Haiku nunca). Sin pedirlo, aparece poco: Kimi
en la 07 (3/5), GLM y Kimi en la 27 (1/5 cada uno), Haiku en la 11 (1/5).
La 12 ya no lo usa ningún modelo. Lo usan donde hay una lista de pasos, y
nadie lo usa de relleno: la guía de `tools.md` no se toca.

**Líneas base nuevas:** `evals/baselines/2026-11-23-opencode-go-*.json`,
con la batería de 30 (§5).

## 6. Orden de piezas para el implementador

Cada punto, un commit pequeño, con tests y lint en verde.

**PR 1 — contar, acotar y ver** (`feature/hito-11-contar`)
1. Los números de hito en los comentarios del código, al día con el plan
   nuevo (§0). *Commit:* "Renumerar los hitos en los comentarios"
2. `domain/context.py`: `estimate`, `ContextPolicy`, `fit`. *Commit:*
   "Estimar el tamaño del contexto en el dominio"
3. `[context]` en la configuración. *Commit:* "Añadir la sección context a
   la configuración"
4. `max_tokens` por llamada. *Commit:* "Limitar max_tokens a lo que queda
   de ventana"
5. El presupuesto de la parte fija, con su test. *Commit:* "Fijar con un
   test el tamaño de la parte fija"
6. `prompt_cache_key` y la caché en la traza. *Commit:* "Mandar la clave
   de caché en el formato de OpenAI"
7. `/context`. *Commit:* "Añadir /context"

**PR 2 — el archivo** (`feature/hito-11-archivo`)
1. `ports/archive.py`, el fake y `archive_sqlite.py`. *Commit:* "Guardar
   el archivo de la sesión en SQLite con FTS5"
2. El tope común con el archivo (§1.6). *Commit:* "Acotar cada resultado y
   archivar el resto"
3. `recall`. *Commit:* "Añadir la herramienta recall"

**PR 3 — archivar** (`feature/hito-11-archivar`)
1. Pasos que se archivan e índice del código. *Commit:* "Elegir qué se
   archiva y construir el índice"
2. `prompts/archive.md` y el `Archivist`. *Commit:* "Resumir lo archivado
   con el modelo barato"
3. Archivar en el bucle y repetir tras `ContextOverflowError`, también
   cuando el proveedor corta el prompt en silencio (decisión 14).
   *Commit:* "Archivar antes de cada llamada si no cabe"
4. `ArchiveEntry`, `replay()` y `SessionTooNew`; también cada salida
   entera archivada, para rehacer el archivo desde la sesión (§12, PR 2).
   *Commit:* "Guardar el archivado en la sesión"
5. `/compact`, la línea al archivar, `-p` y `/export`. *Commit:* "Añadir
   /compact"
6. Evals: `history` y `context_budget`; tareas 25 a 28; la pasada,
   anotada aquí. *Commit:* "Añadir a las evals tareas con historial y con
   archivo"

**PR 4 — instrucciones y herramientas** (`feature/hito-11-herramientas`)
1. `nested()` y `touched()`. *Commit:* "Cargar los AGENTS.md de subcarpetas
   al leer allí"
2. `grep` con `context` y `output`. *Commit:* "Dar a grep líneas de
   contexto y modo solo ficheros"
3. El tope de pasos (§1.16). *Commit:* "Subir el tope de pasos a 50"
4. La tarea 29, la pasada final y las líneas base nuevas. *Commit:*
   "Anotar las evals y las líneas base del hito 11"

**Cierre** (`docs/cierre-hito-11`): spec IMPLEMENTADA, nota 11 de la
guía, los dos README, `PROYECTO.md`, `MAPA.md`, `HISTORIAL_DESARROLLO.md`
y ESTADO.

## 7. Verificación a mano

**Cuándo** *(decisión del mantenedor, 2026-11-17)*: la lista entera se
hace al cerrar el hito, después del PR 4. El PR 3 se integró sin ella;
sus puntos (2, 4, 5, 6 y 9) solo se han visto en las evals (§5,
"Resultados (PR 3)").

En un directorio desechable, con OpenCode Go:
1. `/context` en una sesión nueva: cifras razonables.
2. Con `[context] budget = 20_000`: leer varios ficheros y lanzar comandos
   hasta que archive solo; la línea lo dice; el agente sigue la tarea.
3. Preguntar por algo del principio: el agente usa `recall` y lo
   encuentra.
4. `/compact céntrate en X`: antes y después; el índice lo respeta.
5. Ctrl+C mientras archiva: la conversación sigue como estaba.
6. Salir y `/resume`: vuelve la conversación de trabajo; `/export`, entera.
   Borrar el `.db` y retomar: se rehace.
7. Un comando con una salida enorme: principio, final y el id; `recall`
   la lee por partes.
8. Un `AGENTS.md` en una subcarpeta: al leer allí, el resultado lo trae.
9. `maha -p` con un presupuesto pequeño: archiva y la traza lo cuenta.
10. La parte leída de caché en `/context`, en los dos formatos.

## 8. Lo que no viaja por git y lo que necesita la release

- Nada en `.env`. `[context]` es opcional. El archivo vive en
  `~/.local/state/maha/archive/` de cada máquina.
- Notas de la release: una sesión archivada no la abre un `maha` anterior
  (§1.12).
- `docs/MAPA.md`: los ficheros nuevos y las tareas.
- GitHub: los milestones de los hitos 12 a 23 se renombran a 13 a 24, y se
  crea "Hito 12 — Órbita larga" (§0).

## 9. Guía

`docs/guia/11-contexto-virtual.md`:
1. Por qué un agente se encarece: cada paso reenvía todo (nota 2: el
   modelo no recuerda).
2. Contar tokens: lo que da el proveedor y lo que se estima.
3. Ventana fija, archivo y `recall`: memoria de trabajo y archivo, como un
   sistema operativo con memoria virtual.
4. La caché del prompt: por qué no se reescribe lo enviado.
5. En la industria: compactar, contexto virtual, poda, el del proveedor.

## 10. Riesgos

- **El modelo no busca lo que olvidó** (MemGPT, §1.0). Mitigación: índice
  siempre visible, mensajes de la persona tal cual, una línea en el
  prompt y las tareas 27 y 28.
- **Un índice malo** del archivero barato. Mitigación: la parte del
  código es exacta, lo archivado sigue entero en el archivo, y las evals
  comparan; si el modelo pequeño no llega, `archivist_model` lo cambia.
- **La estimación se queda corta:** la reserva y la repetición tras
  `ContextOverflowError` lo cubren.
- **Inyección por lo archivado:** un fichero leído con "ignora lo
  anterior" acaba resumido o recuperado. Mitigación: delimitado y marcado
  como no confiable en `archive.md` y en `recall`; nunca cambia
  herramientas ni permisos.
- **Un archivo en otro sitio con datos de la persona:** los mismos que la
  sesión, mismos permisos, borrado con ella.
- **Sesiones que el `maha` anterior no abre:** §1.12 y las notas de la
  release.

## 11. Decisiones

Del mantenedor (2026-11-16):
1. **El arnés tiene que ser barato con cualquier modelo**, sin ajustes
   para modelos concretos (§1.1).
2. **Contexto virtual** en lugar de la compactación clásica: archivo
   SQLite + FTS5, modelo barato que resume e indexa, y `recall` (§1.5 a
   §1.9).
3. **Presupuesto de trabajo por defecto: 100.000 tokens**, igual para
   todos los modelos (§1.3).
4. **La órbita larga, hito 12 nuevo**; los siguientes se renumeran y la
   1.0 pasa al hito 24 (§0).

Propuestas del agente, aprobadas por el mantenedor (2026-11-16):
5. **Contar con el uso del proveedor y estimar lo nuevo** (caracteres /
   4), sin tokenizador (§1.2).
6. **Tope común de 40.000 caracteres por resultado**, y lo que sobra al
   archivo; **sin poda** (§1.6).
7. **`recall` sin modelo**, solo FTS5 (§1.9).
8. **Archivar a mitad de turno**, por pasos enteros, y **repetir una vez**
   tras el error de contexto excedido (§1.10).
9. **`ArchiveEntry`** en la sesión y la **política de versiones: el formato
   solo crece** (§1.12).
10. **`prompt_cache_key`** en el formato de OpenAI (§1.13).
11. **`AGENTS.md` de subcarpetas al final del resultado** (§1.14).
12. **`grep` con `context` y `output`** (§1.15) y **tope de pasos a 50**
    (§1.16).

Del mantenedor, al aprobar (2026-11-16):
13. **Solo entra lo que hace el producto verdaderamente competitivo, útil
    y profesional.** Revisada la spec con ese criterio, se quitan el campo
    `archived` de la salida JSON de `-p` (ningún competidor lo tiene; la
    traza ya lo cuenta) y la opción `cache_key` del catálogo (solo si un
    proveedor rechaza la clave). Lo demás se queda: cada pieza la tiene al
    menos un competidor, baja el coste con cualquier modelo o evita perder
    sesiones. El mismo criterio vale al implementar: lo que no lo cumpla
    se quita, y se anota en §12.

Del mantenedor, tras el PR 1 (2026-11-17):
14. **Ningún límite aceptado: un producto robusto y competitivo.** El
    proveedor que corta el prompt en silencio (§12, `hy3`) se detecta y
    se trata como el error de contexto excedido (§1.10): si el proveedor
    cuenta bastantes menos tokens de los que se mandaron y lo mandado no
    cabía en la ventana, se archiva y se repite la llamada una vez. Entra
    en el PR 3, pieza 3, con su test.

Del mantenedor, en el PR 4 (2026-11-23):
15. **`recall` se mide con una tarea nueva, la 30** (train). En la 27 no
    se usaba, porque el índice del archivero ya trae el código de lote. La
    30 empieza con un historial donde el agente leyó un registro largo y
    lo rotó. La línea CRÍTICO está en medio de esa lectura, donde el
    archivero no mira (lee 2.000 caracteres de cada bloque, del principio
    y del final). La 27 sigue igual: mide que el índice conserva el dato.

## 12. Aprendido al implementar

**PR 1 (2026-11-17):**
- **Lo "Sin comprobar" de §1.0, comprobado con OpenCode Go** (formato de
  OpenAI, llamadas reales del 2026-11-17, unos 0,03 $ en total):
  - **El error cuando el prompt no cabe** (`iceman-contributor-free`,
    ventana de 262.144): HTTP 400,
    `{"error":{"type":"invalid_request_error","message":"Upstream request
    failed: [invalid_request_error] Input token count (600025) exceeds the
    model's maximum context length of (262144), no tokens left for
    generation"}}`. Se reconoce por el 400 y "maximum context length" en
    el mensaje (es también la frase de la documentación de OpenAI).
  - **No siempre hay error.** Con `hy3` (ventana de 256.000) el mismo
    prompt de 300.000 palabras dio **200**, `finish_reason: stop`, y
    `prompt_tokens: 196608`: el proveedor **cortó el prompt en silencio**
    (196.608 es justo el 75 % de 262.144) y cobró 0,028 $. Con ese
    proveedor, la repetición tras `ContextOverflowError` (§1.10) nunca
    salta: la única defensa es no llegar, con el techo y la reserva
    (§1.3). Decidido por el mantenedor: se detecta y se trata (decisión 14).
  - **Prompt + `max_tokens` por encima de la ventana se acepta**:
    `kimi-k2.7-code` con 10 + 262.144 y `hy3` con 15 + 250.000 dieron 200.
  - **`prompt_cache_key` se acepta** (`glm-5.3-flash`, tres llamadas con
    el mismo system de 3.772 tokens): la segunda y la tercera leyeron
    3.264 de caché. Sin la clave, con la misma cabecera
    `x-opencode-session`, también: en OpenCode Go la clave no cambia nada
    medible, pero no estorba y ayuda en otros proveedores (§1.13). Se
    queda, sin opción para apagarla (decisión 13).
  - **OpenCode Go exige la cabecera `x-opencode-session`**: sin ella, 400
    `MissingSessionID`. `maha` ya la manda (spec 2).
- **El formato de OpenAI no manda `max_tokens`** (spec 9, §1.6: "los
  servidores compatibles tienen su propio límite"); §1.4 decía que cada
  petición lo lleva, y es así solo en el de Anthropic. Con lo comprobado
  arriba, no se empieza a mandar: `ModelRequest.max_tokens` pasa a ser
  `min(max_output, ventana − prompt estimado)` y cada adaptador sigue
  decidiendo si lo manda.
- **La reserva, como mucho media ventana.** Con la fórmula de §1.3, un
  modelo local de 8.192 tendría una reserva de 16.000 y un techo
  negativo. La reserva queda en `min(max(15 %, 16.000), ventana / 2)`:
  con 8.192, techo de 4.096.
- **Lo que §1.3 no decía del presupuesto:** 10.000 como mínimo (la parte
  fija ya ronda los 3.500, y las instrucciones del proyecto llegan a
  16.000), y un proyecto solo puede bajarlo, como los límites (spec 8,
  §3.2): un repositorio ajeno no hace más cara cada llamada. Un
  `archivist_model` del proyecto se avisa al arrancar, como
  `small_model`.
- **La parte fija, medida con el test:** base 706 y herramientas 1.829
  (2.535 en total, de 3.500); §1.1 estimaba 700 y 1.960.
- **La estimación se queda corta, y la reserva lo cubre.** En una sesión
  nueva con `glm-5.3-flash`, `/context` estimó 2.083 tokens y el
  proveedor contó 2.385 (un 13 % menos). Tras la primera llamada, el
  total parte de la cifra exacta (§1.2). Se vuelve a mirar con el PR 3,
  con sesiones largas.
- **`prompt_cache_key` es el id de sesión del proveedor**, el de la
  cabecera (uno por ejecución de `maha`, spec 2), no el de la sesión de
  `maha`: el cliente se crea antes que la sesión, y la clave solo
  reparte, la caché va por prefijo. Va también sin cabecera de sesión.
- **La caché ya estaba en la traza:** cada `ModelCallFinished` lleva su
  `Usage` con `cache_read_tokens`, y `/trace` la enseña. El informe de
  `maha eval`, con el PR 3 (§3.1).
- **`/context`, sin la línea del índice** hasta que haya archivo (PR 3).
  El porcentaje del total es del techo ("archives at"), no del
  presupuesto: con una ventana pequeña son distintos, y lo que importa es
  cuánto falta para archivar.

**PR 2 (2026-11-17):**
- **`recall` vive en `application`, no en `adapters`** (§3.1 decía
  `adapters/tools/recall.py`). No hace E/S propia: usa el puerto
  `ContextArchive`. Y necesita el archivo de *la sesión en curso*, que
  cambia con `/resume` y `/new`, mientras las herramientas se crean una
  vez por `maha`. Cada agente tiene su `ArchiveSlot`, compartido con su
  `recall`; la sesión pone ahí su archivo. Un hueco común se descartó:
  al cerrar la conversación que se deja tras `/resume`, su guardado puede
  cambiarle el id y reapuntaría el hueco a su archivo.
- **El archivo sigue al id de la sesión.** El id puede cambiar antes de
  que exista el fichero de la sesión (otro `maha` tomó el mismo): las
  salidas de su primer turno ya están archivadas con el id viejo, y se
  mueven con él. Se borra con la sesión (`/delete`, `maha sessions
  delete`).
- **Perezoso:** el `.db` se crea con lo primero que se archiva. Abrir una
  sesión que no archiva nada no deja fichero.
- **Lo que el modelo ve de una salida cortada lo calcula el bucle**, no
  cada herramienta: vale igual para las de hoy y para las de MCP (hito
  18). El resumen de la terminal ("4.210 líneas") sale de la salida
  entera.
- **Un comando guarda entera su salida hasta 8.000.000 de caracteres**
  (2 M del principio y 6 M del final; antes, 30.000), para que vaya
  entera al archivo. Decisión del mantenedor (2026-11-17): "la más
  competitiva". Claude Code y OpenCode guardan en disco la salida entera
  de un comando largo (§1.0); sin ningún tope, un comando desbocado
  (`yes`) llenaría la memoria o el disco hasta el tiempo límite. Ocho
  millones cubren entero cualquier log, build o batería de tests real;
  por encima, el centro se pierde y la marca dice cuántos bytes. Unos 8
  MB de memoria normalmente, 32 MB como mucho. El ejecutor recibe el tope
  (`head`, `tail`), y sus tests lo prueban con uno pequeño (AGENTS.md).
- **`read_file` baja a 36.000 caracteres**, no a 40.000 (§1.6): con los
  números de línea, una lectura entera sigue por debajo del tope común y
  nunca se archiva. El fichero está en disco y se lee por partes.
- **Visto con un modelo real:** `cat` de un log de unos 980 KB, salida
  cortada y archivada, y el modelo usó `recall(query="ERROR")` y dio el
  código bien. Pero citó la línea como `[ERROR]`: los corchetes eran el
  resaltado que FTS5 pone alrededor de lo encontrado, y el modelo los tomó
  como parte del dato. El fragmento va ahora tal cual, con su test.
- **La parte fija, con `recall`:** base 758 y herramientas 2.078 (2.836
  de 3.500).
- **Para el PR 3 (decisión 14):** hoy las salidas enteras solo están en
  el `.db`. Si se borra, `recall` ya no las encuentra, y §1.5 dice que el
  archivo es un índice que se rehace desde el JSONL. En el PR 3, pieza 4,
  la sesión guarda también cada salida entera archivada (una entrada
  nueva, como `ArchiveEntry`), y `rebuild()` la recupera de ahí.

**PR 3 (2026-11-17):**
- **La conversación entera se queda; el modelo recibe la de trabajo.** El
  agente guarda todos los mensajes, cuántos sustituye el índice y el
  índice; lo que manda es `[índice, *mensajes[archivados:]]`.
  `ArchiveEntry.replaces` cuenta desde el principio de la conversación
  entera, no de la de trabajo: varios archivados se componen sin
  reescribir nada, y `/export` tiene todos los mensajes.
- **Un turno que archivó pasos suyos se guarda entero**, termine como
  termine: si no, el índice hablaría de mensajes que no están.
- **Atómico de verdad:** el archivero y el archivo se esperan primero, y el
  cambio de la ventana se hace de una vez al final. Los mensajes
  archivados tienen la id de su posición (`msg-1` es el primero) y el
  resumen, la de su corte (`sum-N`): si un Ctrl+C corta tras escribir en
  el archivo, archivar otra vez lo mismo no añade nada (`ON CONFLICT DO
  NOTHING`; `INSERT OR IGNORE` también se tragaba un `NOT NULL` roto, y lo
  vio un test).
- **El prompt cortado en silencio (decisión 14) se detecta por la cuenta,
  no por la ventana.** La regla de la decisión ("lo mandado no cabía en la
  ventana") casi nunca salta: el bucle archiva antes de pasar del techo, y
  `hy3` corta en un tope suyo (196.608, el 75 % de 262.144), por debajo de
  la ventana del catálogo. La señal robusta: un prompt contiene entero al
  anterior, así que el proveedor no puede contar menos que la llamada
  anterior más una cuarta parte de lo añadido, cuando lo añadido son
  1.000 tokens o más. Solo con el mismo modelo, porque otro cuenta con
  otro tokenizador. La regla de la ventana se queda como segunda señal.
  La respuesta de un prompt cortado se paga y no se guarda.
- **Un `context_full` como motivo de parada** (Anthropic,
  `model_context_window_exceeded`) se trata como el error: se archiva y se
  repite una vez. Tras el error, se archiva todo menos el último paso
  (cola 0). Si ni así cabe, el turno acaba en `context_full` y, como tras
  cualquier llamada fallida, no se guarda si nada se ejecutó. "Una vez
  por paso" queda en un archivado antes de la llamada y, como mucho, uno
  tras el error.
- **El archivero cuesta, pero no es un paso.** Sus llamadas son
  `ModelCallFinished` con `archivist`: cuentan en el turno, en la sesión y
  en los topes, pero `-p` y las evals no las cuentan como pasos ni toman su
  texto como respuesta.
- **El archivero lee cada bloque cortado a 2.000 caracteres** (como el
  `session_search` de Hermes, §1.0): lo entero ya está en el archivo, y así
  cuesta mucho menos. Lee por partes si su ventana no da. Si falla, el
  índice del archivero anterior se conserva, no se pierde.
- **`call_cost()` sale del bucle a `application/pricing.py`**: el bucle
  importa el archivero, y el archivero lo necesitaba.
- **Cada salida entera va también a la sesión** (`OutputEntry`, pieza 4).
  Al retomar, si el archivo falta o está roto, se rehace con los mensajes
  archivados, los resúmenes y las salidas, con sus ids.
- **`SessionTooNew`**: "line N is of a newer maha ('tipo'); update maha to
  open it". La versión de la cabecera es la del `maha` que creó la
  sesión, no la del último que escribió, así que el mensaje no la nombra.
- **`/context` enseña siempre la fila del índice** ("nothing archived"
  hasta que lo haya), como en §1.11; el PR 1 la dejó para cuando hubiera
  archivo.
- **Las evals:** `Sessions.start(history=…)` y el `history.jsonl` de una
  tarea; `context_budget` por tarea. La tarea 27 no tiene `run_command`
  (no lo hay en las evals hasta el hito 16): el dato del principio sale de
  un fichero que el agente cambia después. La 28 lleva `max_steps = 40`,
  hasta que el PR 4 sube el tope a 50. El informe de `maha eval` dice la
  parte leída de caché y en qué tareas se archivó y se usó `recall`
  (§3.1; pendiente del PR 1).
- **Visto con un modelo real** (GLM, tarea 27, una ejecución): archivó a
  22.506 tokens y quedaron 7.092; el índice del archivero guardaba el
  código de lote, lo hecho por fichero y lo pendiente; el archivero costó
  0,001 $. No usó `recall`: el índice ya tenía el dato.

**PR 4 (2026-11-23):**
- **Qué está ya cargado se lee de la ventana, no de un registro aparte.**
  El bucle busca los bloques `<instructions source="…">` al final de los
  resultados que siguen en la ventana de trabajo, y los del paso en curso.
  Así "tras archivar se olvidan y vuelven" y una sesión retomada no los
  repite, sin estado nuevo en la sesión. Un bloque acaba en su primera
  etiqueta de cierre (la del fichero va escapada, como en el system
  prompt).
- **Solo carpetas por debajo del directorio de trabajo.** Las de encima, y
  la suya, ya están en el system prompt (spec 10, §1.4). Un fichero fuera
  del directorio de trabajo no trae nada, como en Claude Code. Un fichero
  que ya nombra un glob de `instructions` no se repite: la sesión pasa al
  bucle las capas de instrucciones de su prompt (`Agent.instructions`).
- **El tope de 64 KiB cuenta todos:** los del system prompt, los que
  siguen en la ventana y los nuevos. Lo que no cabe deja la marca
  `[truncated: N bytes more]`, y el aviso nombra el tope entero, no lo que
  quedaba (`cap(…, of=)`).
- **Lo que no se puede leer** (un secreto, un enlace fuera, no UTF-8) se
  avisa a la persona una vez por sesión (`ToolFinished.warnings`, solo en
  el JSON si hay alguno), como los del system prompt. Al modelo no le
  llega nada.
- **El prompt base decía que solo mandan los bloques "de este prompt"**, y
  el modelo hizo bien en no seguir uno que llegaba en un resultado. Visto
  a mano con GLM (un `api/AGENTS.md` que pide acabar con una palabra):
  el bloque llegaba intacto y no se seguía. Ahora `base.md` dice que
  también mandan los que `maha` añade al final de `read_file`,
  `edit_file` o `write_file`. Con el cambio, GLM y Haiku lo siguen. Solo
  esas tres herramientas, y no por casualidad: un fichero no puede fingir
  un bloque al final de `read_file` (sus líneas van numeradas), y un
  bloque en la salida de un comando sigue siendo un dato.
- **`grep`:** `context` da los grupos como grep y ripgrep (`ruta:N:` la
  coincidencia, `ruta-N-` alrededor, `--` entre grupos que no se tocan y
  entre ficheros). El tope de 100 cuenta coincidencias, no líneas, y en
  `files` y `count`, ficheros. El resumen de la terminal sale del texto
  ("4 matches", "2 files"). El valor por defecto sigue siendo `lines`: se
  mide con la tarea 29 (§5) antes de cambiarlo.
- **El tope de pasos, 50 también en las evals** (`TASK_LIMITS`). La 28 deja
  su `max_steps = 40`; la 27 conserva sus 30.
- **La parte fija, medida con el test:** base 819 y herramientas 2.191
  (3.010 de 3.500).
- **La tarea 30 no archivaba en la primera prueba.** Con la ventana del
  catálogo, el techo es el presupuesto entero (20.000), no la mitad: el
  historial cabía y el modelo leyó el código directamente. Con manuales
  más largos, el historial pasa del techo él solo, y un test lo fija
  (`test_task_30_needs_recall`). Probada con GLM (2/2): archiva y usa
  `recall` en las dos.
