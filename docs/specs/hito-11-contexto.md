Estado: PROPUESTA (2026-11-16)

# Spec — Hito 11: Gestión del contexto

Referencias: `docs/DESIGN.md` §4 (pieza 7: "antes de cada llamada: si no
cabe, se compacta"), §5 (sesión), §8 (system prompt fijo por sesión), §9
(evals), §10 (entrada no confiable) y §14 (hito 11, P6);
`docs/ANALISIS.md` §5 (pieza 7) y criterio 8; `docs/COMPARATIVA.md` §9;
specs 4 (§12.14, tokens de las herramientas), 6 (§5 y riesgos: sesiones
que no caben; la marca `[interrupted by the user]`), 8 (§1.1 topes; §11.8,
tareas con historial previo), 9 (§1.6 `max_tokens`; caché del prompt) y 10
(decisión 6, `AGENTS.md` de subcarpetas; §5, `todo_write`); la auditoría
tras el hito 10 ("A su hito": `grep` con contexto o solo ficheros, la
política de versiones del formato de sesión y subir el tope de pasos);
`AGENTS.md`.

## 0. Alcance

**El problema.** `maha` manda la conversación entera en cada llamada y no
sabe cuánto ocupa. Una sesión larga crece hasta que el proveedor la
rechaza o corta la respuesta (`context_full`), y entonces la sesión ya no
sirve: no hay forma de seguir sin empezar otra. Antes de llegar ahí, cada
llamada cuesta más y el modelo trabaja peor con tanto texto viejo.

**Lo que hace este hito.** `maha` cuenta los tokens de cada llamada, sabe
cuánto le queda de ventana y, antes de llenarla, libera sitio: primero
poda los resultados viejos de las herramientas y, si no basta, resume la
conversación con el modelo y sigue con el resumen. La persona lo ve
(`/context`), lo puede pedir (`/compact`) y la sesión guarda lo que pasó
sin perder nada en disco.

**Términos.**
- **Token:** el trozo de texto con el que cuenta un modelo (en inglés,
  unos 4 caracteres).
- **Ventana de contexto:** cuántos tokens caben en una llamada, prompt y
  respuesta juntos. Sale del catálogo (`context`).
- **Reserva:** la parte de la ventana que se deja libre para la respuesta
  del modelo.
- **Poda (*prune*):** cambiar el texto de un resultado de herramienta
  viejo por una marca corta. Sin llamar al modelo.
- **Compactar:** cambiar el principio de la conversación por un resumen
  que escribe el modelo.
- **Umbral:** el tamaño a partir del cual `maha` compacta solo.

Dentro de alcance:
- **Conteo** (§1.1): cuánto ocupa la conversación, con el uso que da el
  proveedor y una estimación de lo nuevo.
- **Umbral y reserva** (§1.2), y `max_tokens` por llamada (§1.3).
- **Poda de resultados viejos** (§1.4).
- **Compactación por resumen** (§1.5), **qué sobrevive** (§1.6) y su
  **prompt** en el repo (§1.7).
- **Cuándo** se comprueba (§1.8): antes de cada llamada, también a mitad
  de turno, y una vez más si el proveedor dice que no cabe.
- **`/compact [instrucciones]`** y **`/context`** (§1.9).
- **La sesión** (§1.10): la compactación como entrada nueva, y la
  **política de versiones del formato** (pendiente de la auditoría).
- **`AGENTS.md` de subcarpetas** (§1.11), cargados al leer un fichero de
  allí.
- **Herramientas que gastan menos** (§1.12): `grep` con líneas de
  contexto y modo "solo ficheros"; el coste de las herramientas, medido.
- **El tope de pasos** (§1.13), revisado con la compactación.
- **Trazas** (§1.14) y **`-p`** (§1.15).
- **Evals** (§5): tareas con historial previo (con la marca
  `[interrupted by the user]`), tareas largas que compactan con una
  ventana pequeña forzada, y otra medida de `todo_write`.
- Nota 11 de la guía: la ventana de contexto.

**Fuera de alcance** (y por qué):
- **La compactación del proveedor** (Anthropic: edición del contexto y
  compactación en la API, §1.0): es de un solo formato y haría una pieza
  del agente fuera de `maha` (DESIGN §7.1, "a mano lo que es del agente").
- **Un tokenizador local** (`tiktoken` u otro): cada familia cuenta a su
  manera, y el proveedor ya da la cifra exacta de cada llamada (§1.1).
- **La barra de estado con el contexto:** hito 21 (TUI). Aquí, `/context`
  y una línea cuando se compacta.
- **Hooks antes y después de compactar:** hito 18. Este hito deja el
  evento que usarán.
- **Deshacer una compactación** y volver a un punto: hito 12 (deshacer).
  La sesión guarda todo, así que el hito 12 lo podrá hacer.
- **Bifurcar una sesión:** hito 12 (ya asignado).
- **Memoria entre sesiones:** hito 14.

## 1. Decisiones de fondo

### 1.0 Hechos comprobados (2026-11-16)

Leídos en la documentación oficial y en el código. OpenCode: `dev` en el
commit `8bb7fab` (ya es la V2) y el tag `v1.19.5` (la V1); Codex: commit
`95946fa`.

| Hecho | Fuente |
|---|---|
| OpenCode cuenta con el uso de la última respuesta del proveedor y estima lo que va después con caracteres / 4 (`CHARS_PER_TOKEN = 4`) | código, `packages/core/src/session/compaction.ts` (`estimatePrompt`), `util/token.ts` |
| OpenCode V2 compacta en `ventana − max(15 % de la ventana, 16.000)` (`compaction.buffer`, por defecto `"15%"`); conserva unos 15.000 tokens recientes tal cual (`compaction.keep.tokens`) | https://opencode.ai/docs/compaction, `compaction.ts` (`calculateCeiling`) |
| OpenCode V2 repite una vez la llamada que el proveedor rechaza por larga, tras compactar | https://opencode.ai/docs/compaction |
| OpenCode resume con el modelo de la sesión, salvo `agents.compaction.model`. Su plantilla: objetivo, requisitos, decisiones, estado (hecho, en curso, bloqueado), siguiente paso, ficheros (15 como mucho) y contexto; rutas, comandos y errores exactos; "Do not continue the task or call tools" | https://opencode.ai/docs/compaction, `compaction.ts` (`SUMMARY_TEMPLATE`) |
| OpenCode V1 podaba: de atrás hacia delante, sin tocar los dos últimos turnos de la persona, protegía los últimos 40.000 tokens de salidas (`PRUNE_PROTECT`) y solo podaba si liberaba más de 20.000 (`PRUNE_MINIMUM`); la marca, `[Old tool result content cleared]`. La V2 quitó `prune`: acorta las salidas largas dentro de la parte que conserva | `v1.19.5`, `packages/opencode/src/session/compaction.ts`; https://opencode.ai/docs/migrate-v1 |
| OpenCode carga los `AGENTS.md` entre el fichero leído y el directorio de trabajo, el más cercano primero, una vez mientras siga en el historial (otra vez tras compactar). Van en un mensaje aparte, `Instructions from: <ruta>`, no en el resultado | https://opencode.ai/docs/instructions, `tool/plugin/read.ts`, `session/instructions.ts` |
| Claude Code, tras compactar: vuelve a meter el system prompt, el `CLAUDE.md` de la raíz y el plan; los `CLAUDE.md` de subcarpetas se recargan al leer allí; relee hasta 5 ficheros recientes | https://code.claude.com/docs/en/context-window |
| Claude Code carga un `CLAUDE.md` de subcarpeta la primera vez que lee, escribe o edita allí | https://code.claude.com/docs/en/memory |
| Claude Code: `/compact [instrucciones]`; compacta cerca del límite (unos 967K en los modelos de 1M); tras varios intentos fallidos para con un error en vez de repetir; `/context` por partes (system prompt, herramientas, memoria, skills, mensajes) | https://code.claude.com/docs/en/commands, `/model-config`, `/how-claude-code-works`, `/debug-your-config` |
| Claude Code borra resultados viejos de herramientas, y lo cuenta como una reconstrucción esperada de la caché | https://code.claude.com/docs/en/costs |
| Hook `PreCompact` de Claude Code: `manual` o `auto`, puede bloquear | https://code.claude.com/docs/en/hooks |
| Codex compacta en `min(configurado, 90 % de la ventana)`; conserva mensajes recientes de la persona hasta 20.000 tokens | código, `codex-rs/protocol/src/openai_models.rs`, `codex-rs/core/src/compact.rs` |
| Anthropic: `count_tokens` es gratis y da una estimación; *context editing* (beta `context-management-2025-06-27`) y compactación en la API (beta `compact-2026-01-12`) | https://platform.claude.com/docs/en/build-with-claude/token-counting, `/context-editing`, `/compaction-threshold` |
| Anthropic: un prompt que no cabe da 400 `invalid_request_error` ("prompt is too long"); en los modelos 4.5 y posteriores, prompt + `max_tokens` por encima de la ventana se acepta, y la respuesta para con `model_context_window_exceeded` | https://platform.claude.com/docs/en/build-with-claude/context-windows |
| OpenAI: "the prompt and the generated output combined must be no more than the model's maximum context length"; Chat Completions no tiene endpoint para contar tokens | https://developers.openai.com/api/docs/concepts, `/guides/token-counting` |
| OpenAI: con `stream_options.include_usage`, el uso llega en un trozo final; si el stream se corta, se puede perder | referencia de `chat/completions/create` |

**Sin comprobar** (POR VERIFICAR al implementar, con una llamada real a
OpenCode Go): qué error exacto (estado y cuerpo) da Chat Completions, y
GLM y Kimi por OpenCode, cuando el prompt no cabe; si rechazan prompt +
`max_tokens` por encima de la ventana.

### 1.1 Contar: el uso del proveedor, y una estimación de lo nuevo

El tamaño de la conversación en la próxima llamada es:

```
último input_tokens + último output_tokens   (exacto, del proveedor)
+ estimación de lo añadido después           (resultados, mensaje nuevo)
```

- **Lo exacto, del proveedor.** Cada llamada ya devuelve `Usage`
  (`input_tokens` cuenta todo el prompt, caché incluida, DESIGN §5). Es la
  cifra con el tokenizador real del modelo, el system prompt y las
  herramientas incluidos.
- **Lo nuevo, estimado:** caracteres / 4, redondeando hacia arriba, en
  `domain/context.py`. Es lo que hacen OpenCode y Claude Code para lo que
  aún no ha medido el proveedor (§1.0). Se equivoca en código y en otros
  idiomas, así que el margen de §1.2 lo cubre.
- **Sin llamada previa** (sesión nueva, recién retomada, tras compactar):
  todo estimado. El system prompt y las herramientas, también por
  caracteres.
- **El uso de la última llamada se guarda** en la sesión (ya está en
  `UsageEntry`, por turno) y en el agente, por llamada: al retomar, la
  primera estimación usa la última llamada que se guardó.

```python
# domain/context.py
def estimate(text: str) -> int:
    return -(-len(text) // 4)


class ContextSize(BaseModel, frozen=True):
    measured: int  # del proveedor, la última llamada
    estimated: int  # lo añadido después

    @property
    def total(self) -> int: ...
```

*Alternativas descartadas:* un tokenizador por familia (dependencias,
modelos sin tokenizador público); el endpoint `count_tokens` de Anthropic
(una llamada más por paso, y solo un formato).

### 1.2 Umbral y reserva

```
ventana útil = min(ventana del catálogo, [context] window)
reserva      = max(15 % de la ventana útil, 16_000)
umbral       = ventana útil − reserva
```

- **Se compacta cuando la próxima llamada pasaría del umbral.**
- **La reserva** es para la respuesta y para el error de la estimación.
  Es la fórmula de OpenCode V2 (§1.0). Con 1M de ventana compacta a
  850.000; con `kimi-k2.7-code` (262.144), a unos 222.800; con 30.000
  (evals), a 14.000.
- **No sale de `max_output`**, porque hay modelos con `max_output` igual a
  su ventana (`kimi-k2.7-code`: 262.144 de los dos): reservarlo todo
  dejaría cero para la conversación.
- **`[context] window`** limita la ventana. Sirve para tres cosas:
  - **coste:** en `claude-haiku-5-5`, pasar de 100.000 tokens de entrada
    multiplica el precio por 5 (`models.toml`, tramo `above = 100_000`);
  - **calidad:** los modelos atienden peor con contextos muy largos;
  - **evals:** una ventana pequeña obliga a compactar en una tarea corta
    y barata (§5).
- **Valor por defecto de `window`:** sin límite (la del catálogo). Ver
  decisión 2: se propone medir con evals si conviene uno.
- **Ventana desconocida** (el catálogo no tiene `context`): no se compacta
  solo. `/compact` funciona, y `/context` dice que no se sabe la ventana.

```toml
# ~/.config/maha/config.toml o .maha/config.toml
[context]
auto_compact = true   # false: solo con /compact
window = 200_000      # opcional: tope de la ventana, en tokens
```

### 1.3 `max_tokens` por llamada

Hoy cada petición lleva `max_tokens = max_output` del catálogo (spec 9,
§1.6). Con `kimi-k2.7-code` eso es su ventana entera. La regla de OpenAI
dice que prompt y respuesta juntos no pasan de la ventana (§1.0); si el
proveedor la aplica, la llamada falla en cuanto la conversación crece.
Anthropic lo acepta en sus modelos recientes y corta la respuesta.

- **Desde este hito:** `max_tokens = min(max_output, ventana útil −
  tamaño estimado del prompt)`. Por debajo del umbral siempre queda al
  menos la reserva de §1.2; por encima, se compacta antes (§1.8).
- Cierra el pendiente "el tope de cada llamada sigue para el hito 11"
  (DESIGN §5, anotado el 27/10/2026).

### 1.4 Primer nivel: podar resultados viejos

Lo que más ocupa en un agente de código son los resultados de las
herramientas: un fichero leído, una salida de tests. Pasados unos pasos,
el modelo ya los usó.

- **Qué se poda:** el `content` de los `ToolResultBlock` más viejos, de
  atrás hacia delante, dejando intactos los resultados de los últimos
  **40.000 tokens** estimados. Se cambia por:

  ```
  [old tool result cleared to free context; run the tool again if you need it]
  ```
- **Qué no se poda nunca:** los mensajes de la persona, el texto y las
  llamadas del modelo, los bloques de razonamiento (Anthropic los
  comprueba con su firma), los resultados de error (cortos y útiles) y
  los de `todo_write` y `ask_user` (son decisiones, no datos).
- **Solo si compensa:** si la poda libera menos de **20.000 tokens**, no
  se hace y se pasa al resumen (§1.5). Romper la caché del proveedor
  (§1.0) por poco no vale la pena.
- **El par llamada-resultado se conserva** siempre: la API exige un
  resultado por llamada (spec 4, §1.1); la poda solo cambia el texto.
- **Deja la conversación bajo el objetivo:** la poda tiene que bajar del
  **60 %** de la ventana útil; si no llega, se pasa al resumen.
- Los números (40.000 y 20.000) son los de OpenCode V1 (§1.0); Claude
  Code también borra resultados viejos. Se ajustan con evals.
- **OpenCode V2 quitó la poda** (§1.0) y solo resume. Lo que se gana con
  ella: una sesión de muchas lecturas sigue sin llamar al modelo y sin
  perder nada de lo que dijeron la persona y el modelo. Lo que se pierde:
  otra pieza que probar, y otra rotura de la caché. Las evals deciden si
  se queda (decisión 3); si no gana, el PR 2 la quita y queda solo el
  resumen.

### 1.5 Segundo nivel: resumir

Cuando podar no basta, el modelo resume la conversación y la parte vieja
se cambia por el resumen.

- **Qué se resume:** todo menos la cola reciente. La **cola** son los
  últimos turnos enteros que quepan en **20.000 tokens** estimados (Codex
  conserva 20.000 y OpenCode 15.000, §1.0), y como mínimo el último
  mensaje de la persona. Turnos enteros: una llamada
  nunca queda sin su resultado.
- **Quién resume:** el modelo de la sesión, con el mismo proveedor, los
  mismos reintentos y el mismo respaldo (spec 8, §1.14). No el modelo
  pequeño: su ventana puede ser menor y el resumen es la pieza que más
  pesa en la calidad de lo que sigue. Se puede cambiar con `[context]
  compact_model`.
- **Sin herramientas:** la llamada de resumen no lleva herramientas
  (`tools = []`), así que el modelo solo puede escribir texto. Lleva el
  system prompt de la sesión (la caché del proveedor lo reutiliza).
- **Si lo que se resume no cabe** en la llamada de resumen (por ejemplo,
  el modelo de respaldo tiene menos ventana): se poda primero, en esa
  petición, todo lo podable; si aún no cabe, se resume por partes, de la
  más vieja a la más nueva, cada parte con el resumen de la anterior.
- **El resultado** es un mensaje de la persona al principio de la
  conversación, marcado y delimitado:

  ```
  <conversation-summary>
  This conversation was compacted. Summary of the earlier part:
  …
  </conversation-summary>
  ```
  Delante va lo que construye el código (§1.6), y detrás, la cola intacta.
- **Ctrl+C mientras resume:** se cancela, la conversación queda como
  estaba y el turno sigue cortado como cualquier Ctrl+C. Compactar es
  atómico: o todo, o nada.
- **Si falla** (error del proveedor tras reintentos, resumen vacío): la
  conversación queda como estaba. Si la llamada aún cabe, el turno sigue
  y se avisa; si no, el turno acaba con `context_full` y el aviso dice qué
  hacer (`/compact`, `/new`).
- **El coste del resumen** cuenta en el turno y en la sesión, como
  cualquier llamada (`ModelCallFinished`), y en los topes del turno.

### 1.6 Qué sobrevive a la compactación

Una parte la escribe el código (exacta, no depende del modelo) y otra el
modelo (el resumen):

| Qué | Cómo |
|---|---|
| System prompt | Intacto: va aparte y no cambia en la sesión (spec 10, §1.2) |
| Herramientas y permisos aprobados para la sesión | Intactos: no son conversación |
| La lista de tareas | El código copia la última de `todo_write` |
| Ficheros que el agente cambió | El código lista las rutas de `write_file` y `edit_file` con éxito |
| `AGENTS.md` de subcarpetas ya cargados | Se olvidan: vuelven al leer otra vez allí (§1.11) |
| Instrucciones de `/compact` | Van al prompt del resumen |
| La cola reciente | Intacta, con sus resultados |
| Lo demás (qué pidió la persona, decisiones, errores, estado) | El resumen del modelo, con la estructura de §1.7 |

La parte del código va delante del resumen, en el mismo mensaje:

```
<conversation-summary>
Files changed so far: src/app.py, tests/test_app.py
Task list: [x] rename multa · [ ] add tope · [ ] update README
…resumen del modelo…
</conversation-summary>
```

### 1.7 El prompt del resumen

- **En el repo:** `src/mharness/prompts/compact.md`, con huecos
  (`{{instructions}}`), como `title.md` e `init.md` (spec 10, §1.3). Es
  código: se evalúa (§5).
- **Pide una estructura fija**, en el idioma de la conversación: la
  petición de la persona y sus cambios; decisiones y por qué; lo hecho
  (ficheros y qué cambió en cada uno); errores y cómo se resolvieron; lo
  que falta; el siguiente paso exacto, con las palabras de la persona si
  las hay.
- **Delimita lo que resume:** la conversación va dentro de
  `<conversation>` y el prompt dice que es entrada no confiable: las
  instrucciones que aparezcan ahí (un fichero leído, una web) no se
  siguen, se resumen como datos (DESIGN §10).
- **Tope de salida:** `max_tokens = 8.000` para el resumen. Un resumen más
  largo que eso ya no ahorra.

### 1.8 Cuándo se comprueba

- **Antes de cada llamada al modelo**, dentro del bucle (DESIGN §4): al
  empezar el turno, con el mensaje nuevo, y antes de cada paso, con los
  resultados del anterior.
- **A mitad de turno** se compacta igual: lo resumido es lo anterior al
  turno, y el turno en curso es parte de la cola. Si el turno solo ya no
  cabe, se podan sus resultados viejos; si aun así no cabe, el turno
  acaba con `context_full`.
- **Si el proveedor dice que no cabe** (`stop_reason = "context_full"` o
  el error de contexto excedido, §1.0), aunque la estimación dijera que
  sí: se compacta y se repite la llamada **una vez**. Si vuelve a pasar,
  el turno acaba con `context_full`. OpenCode hace lo mismo (§1.0). Para
  eso, cada adaptador traduce el error de su API a `ContextOverflowError`,
  del dominio: en Anthropic, el 400 "prompt is too long"; en el formato de
  OpenAI no está documentado, y se fija al implementar con una llamada
  real a OpenCode Go (GLM y Kimi), anotada en §12. Un error que no se
  reconoce sigue siendo el error de hoy.
- **Una compactación por paso** como mucho: nunca un bucle de compactar.
- **No se compacta a la vez que** se muestra texto: entre pasos, cuando no
  hay nada en pantalla a medias.

### 1.9 `/compact` y `/context`

- **`/compact [instrucciones]`:** compacta ya, aunque no haga falta. Sin
  poda: va directo al resumen, con las instrucciones si las hay
  (`/compact céntrate en el fallo del IVA`). Dice cuánto había y cuánto
  queda:

  ```
  > /compact
  [compacted: 84,210 → 6,930 tokens (estimated); 0.031 $]
  ```
- **`/context`:** qué ocupa la ventana, por partes, con la última cifra
  exacta y lo estimado:

  ```
  > /context
  claude-haiku-5-5 · window 1,000,000 (limit 200,000) · auto-compact at 170,000
  system prompt     2,140   (base 390 · AGENTS.md 1,610 · environment 140)
  tools             1,960   (9 tools)
  messages         71,300   (tool results 58,900 · summary 0)
  total            75,400   37.7 % of 200,000 · last call 74,950 (exact)
  ```
- Los dos, solo en la sesión interactiva. En `-p` no hay comandos (spec
  8): ahí compacta solo.
- **`/help`** los lista.

### 1.10 La sesión, y la política de versiones del formato

**Una entrada nueva**, sin reescribir el fichero (la sesión es
`append-only`, spec 6, §1.2):

```python
class CompactionEntry(BaseModel, frozen=True):
    type: Literal["compaction"] = "compaction"
    # Cuántos mensajes del historial, desde el principio, sustituye.
    replaces: int
    # El mensaje que va en su lugar (§1.6): el resumen.
    summary: Message
    # "prune": cambió resultados; "summary": resumió; "manual": /compact.
    kind: Literal["prune", "summary", "manual"]
    # Para la poda: los ids de las llamadas cuyo resultado se podó.
    pruned: list[str] = []
```

- **Al retomar**, `replay()` aplica cada `CompactionEntry` en su sitio: la
  conversación que vuelve es la compactada. Los mensajes originales siguen
  en el fichero.
- **`/export` y `maha export`** dan la conversación entera, con una marca
  donde se compactó y el resumen. Lo que se borra para el modelo no se
  borra para la persona.
- **`check_history`** comprueba también la conversación compactada.

**Política de versiones del formato** (pendiente de la auditoría tras el
hito 10). Hoy un `maha` viejo que encuentra una entrada que no conoce dice
"fichero corrupto". Se decide:
- **El formato solo crece:** cada versión puede añadir tipos de entrada o
  campos opcionales; nunca cambia el significado de uno que existe.
- **Un tipo desconocido** no es "corrupto": `SessionTooNew`, con el
  mensaje "this session was written by a newer maha (X.Y.Z); update maha
  to open it". La versión sale de la cabecera (`maha`, ya existe).
- **Se aplica desde este hito**, que es el primero que añade un tipo que
  cambia la conversación. Los `maha` de antes (≤ 0.10.2) seguirán diciendo
  "corrupto" con una sesión compactada: se anota en las notas de la
  release.
- Un test fija que una entrada de un tipo inventado da `SessionTooNew` y
  no `SessionCorrupt`.

### 1.11 `AGENTS.md` de subcarpetas

Hoy se cargan, en el system prompt, los `AGENTS.md` de la raíz git hasta
el directorio de trabajo (spec 10, §1.4). Los de carpetas más abajo
(`packages/api/AGENTS.md`) no se ven nunca.

- **Cuándo:** la primera vez que `read_file`, `edit_file` o `write_file`
  toca un fichero de una carpeta que tiene, entre ella y el directorio de
  trabajo, un `AGENTS.md` (o `CLAUDE.md`, con `compat_claude`) que no se ha
  cargado.
- **Dónde:** al final del resultado de esa herramienta, delimitado como en
  el system prompt:

  ```
  …contenido del fichero…

  <instructions source="packages/api/AGENTS.md">
  Los tests de este paquete se lanzan con `make test`.
  </instructions>
  ```
  No en el system prompt: cambiarlo a mitad de sesión rompe la caché
  (spec 10, §1.2). OpenCode lo manda como un mensaje aparte de la persona
  (§1.0); al final del resultado es más simple (no añade mensajes al
  turno, y el par llamada-resultado no cambia) y el modelo lo ve igual de
  cerca. Claude Code lo carga al leer, escribir o editar, como aquí.
- **Una vez por sesión** cada fichero. Tras compactar se olvidan (§1.6):
  vuelven la próxima vez que se lea allí.
- **Las mismas reglas** que los de spec 10: dentro del proyecto, sin
  secretos, sin enlaces fuera, UTF-8, y el tope de 64 KiB contando todos
  los cargados en la sesión.
- **Arquitectura:** el puerto `ProjectInfo` gana `nested(path) ->
  list[Layer]`; la herramienta no lo llama (un adaptador no importa otro).
  Lo hace el bucle: cada herramienta dice qué ruta tocó (`touched(params)
  -> str | None`, nuevo en el puerto `Tool`, `None` por defecto), y el
  agente añade lo que devuelva `nested()`.
- **Confianza:** son instrucciones del proyecto, igual que las del system
  prompt (spec 10, §1.6). El modelo ve de qué fichero salen.

### 1.12 Herramientas que gastan menos

**`grep`** (pendiente de la auditoría tras el hito 10). Hoy siempre da
`ruta:línea: texto`. Se añaden dos parámetros:

```json
{"pattern": "def total", "context": 2}
{"pattern": "TODO", "output": "files"}
```
- `context` (0 a 10, 0 por defecto): líneas de antes y después, como
  `grep -C`. Evita leer el fichero entero para ver una función.
- `output`: `"lines"` (por defecto), `"files"` (solo las rutas) o
  `"count"` (cuántas por fichero). Para saber dónde algo, sin traer todo.

**El coste de las herramientas en cada llamada** (spec 4, §12.14). Medido
hoy (2026-11-16) con sus esquemas en JSON: **9 herramientas, 7.840
caracteres, unos 1.960 tokens** estimados. Las que más: `ask_user` (488)
y `todo_write` (375). Se decide:
- `/context` lo enseña en cada sesión (§1.9).
- No se recortan descripciones en este hito sin evals: cada palabra de una
  descripción cambia el comportamiento (spec 10). Se anota el número en
  la guía y se mide con la caché: con la caché del proveedor, la parte
  fija (system prompt y herramientas) se cobra a precio de caché.

### 1.13 El tope de pasos

Hoy son 25 llamadas por turno (`MAX_STEPS`, spec 8, §1.1). Se puso bajo
porque un turno largo llenaba el contexto. Con la compactación ese motivo
desaparece, y las tareas largas (renombrar en un proyecto, arreglar una
batería de tests) pasan de 25.

- **Propuesta: 50**, confirmado con las tareas largas de §5 (cuántos pasos
  usan de verdad). Se puede cambiar en `[limits] max_steps`, como hoy.
- Los demás topes (coste, tokens, tiempo) no cambian.

### 1.14 Trazas y eventos

- **Eventos nuevos del bucle** (`domain/agent_events.py`):
  - `ContextCompacting(kind, before)`: va a compactar (la terminal dice
    "compacting…");
  - `ContextCompacted(kind, before, after, replaced)`: ya está.

  El hito 18 (hooks) los usará.
- **La traza** los apunta, con el coste del resumen en su
  `ModelCallFinished`.
- **`/trace`** enseña cada compactación en su sitio.

### 1.15 `-p` y la salida JSON

- En `maha -p` compacta solo, igual que en la sesión interactiva.
- La salida JSON (spec 8) gana `compactions`: cuántas hubo en el turno.

## 2. En la industria

| Enfoque | Qué hace | Cuándo se elegiría |
|---|---|---|
| **Resumen** (Claude Code `/compact` y automático, OpenCode, Codex) | El modelo resume y la conversación sigue desde el resumen | Agentes de conversación larga: es lo de `maha` |
| **Poda de resultados** (OpenCode V1 `prune`; Claude Code) | Borra salidas viejas de herramientas, sin llamar al modelo | Primer nivel, barato; es lo de `maha` |
| **Ventana deslizante** (LangChain `ConversationBufferWindowMemory`, `trim_messages`) | Quita los mensajes más viejos | Chats sin herramientas; en un agente rompe los pares llamada-resultado |
| **Edición y compactación del proveedor** (Anthropic *context editing*, *compaction*) | La API hace la poda o el resumen | Si solo se usa ese proveedor |
| **Memoria externa** (MemGPT/Letta, RAG) | Lo viejo va a una base y se busca | Memoria entre sesiones: hito 14 |
| **Tokenizador local** (`tiktoken`, `tokenizers` de Hugging Face) | Cuenta exacto antes de llamar | Con un solo proveedor y tokenizador público |

## 3. Diseño de detalle

### 3.1 Ficheros

| Fichero | Capa | Qué |
|---|---|---|
| `domain/context.py` (nuevo) | domain | `estimate()`, `ContextSize`, `ContextPolicy` (ventana, reserva, umbral, objetivo de la poda), `prune()` y `tail()` (qué se poda y cuál es la cola), puras y sin E/S |
| `domain/errors.py` | domain | `ContextOverflowError` |
| `domain/session.py` | domain | `CompactionEntry`, `SessionTooNew`, `replay()` con compactaciones |
| `domain/agent_events.py` | domain | `ContextCompacting`, `ContextCompacted` |
| `domain/trace.py` | domain | Los registros de compactación |
| `ports/tools.py` | ports | `touched(params)` |
| `ports/project.py` | ports | `nested(path)` |
| `application/context.py` (nuevo) | application | `Compactor`: decide, poda o resume, y construye la parte del código (§1.6) |
| `application/agent.py` | application | Comprobar antes de cada llamada; repetir una vez tras `ContextOverflowError`; `max_tokens` (§1.3); `AGENTS.md` de subcarpetas |
| `application/sessions.py` | application | Guardar `CompactionEntry`; `/compact`; los datos de `/context` |
| `adapters/models/openai_chat.py`, `anthropic.py` | adapters | Traducir el error de contexto excedido |
| `adapters/project/local.py` | adapters | `nested()` |
| `adapters/tools/files.py` | adapters | `touched()`; `grep` con `context` y `output` |
| `adapters/cli/commands.py`, `conversation.py`, `headless.py`, `export.py` | adapters | `/compact`, `/context`, la línea al compactar, `compactions` en JSON, la marca en la exportación |
| `adapters/evals/toml_suite.py`, `domain/evals.py` | adapters, domain | `history` y `context_window` en una tarea (§5) |
| `src/mharness/prompts/compact.md` (nuevo) | — (datos) | El prompt del resumen |
| `config.py` | — | `[context]` |
| `bootstrap.py` | — | El cableado |
| `domain/limits.py` | domain | `MAX_STEPS = 50` (§1.13) |

### 3.2 Configuración nueva

```toml
[context]
auto_compact = true        # §1.2
window = 200_000           # §1.2; opcional
compact_model = "…"        # §1.5; opcional, por defecto el de la sesión
```

Comandos: `/compact [instrucciones]` y `/context`.

## 4. Plan de tests

Con fakes; ninguna llamada real.

1. `estimate()`: vacío, ASCII, multibyte; redondea hacia arriba.
2. `ContextPolicy`: umbral con y sin `window`; reserva del 15 % con mínimo de 16.000,
   también con `max_output == context`; ventana desconocida, sin compactación
   automática.
3. `max_tokens` por llamada: nunca más que lo que queda; nunca menos que la
   reserva.
4. `prune()`: de atrás hacia delante; protege los últimos 40.000; no toca
   errores, `todo_write`, `ask_user`, razonamiento ni texto; cada llamada
   conserva su resultado; no poda si libera menos de 20.000.
5. `tail()`: turnos enteros; como mínimo el último mensaje de la persona;
   nunca una llamada sin resultado.
6. Compactor con `FakeModelClient`: el resumen va delimitado, con la parte
   del código (lista de tareas, ficheros cambiados) delante; la llamada de
   resumen no lleva herramientas; las instrucciones de `/compact` llegan
   al prompt.
7. Atomicidad: Ctrl+C y error del proveedor durante el resumen dejan la
   conversación igual.
8. En el bucle: compacta antes de la primera llamada si el mensaje nuevo
   no cabe; a mitad de turno; una vez como mucho por paso;
   `ContextOverflowError` → compacta y repite una vez; la segunda vez,
   `context_full`.
9. Coste: el resumen cuenta en el turno, en la sesión y en los topes.
10. Sesión: `CompactionEntry` se guarda y `replay()` la aplica; retomar da
    la conversación compactada; `check_history` pasa; `/export` da todo
    con la marca.
11. Formato: una entrada de un tipo inventado da `SessionTooNew` con la
    versión; una línea rota sigue siendo `SessionCorrupt`.
12. `AGENTS.md` de subcarpetas: se añade al resultado una vez; no los del
    system prompt; tras compactar, otra vez; secretos, enlaces fuera y el
    tope de 64 KiB.
13. `grep`: `context` (solapes, principio y fin de fichero), `output`
    `files` y `count`; los valores fuera de rango vuelven como error al
    modelo.
14. Los adaptadores traducen el error de contexto excedido de cada API
    (con respx y el cuerpo real documentado, §1.0).
15. `/context` con un prompt y unas herramientas conocidas; `/compact`
    dice antes y después.
16. `-p`: compacta solo y el JSON lleva `compactions`.
17. Evals: una tarea con `history` empieza con esa conversación; una con
    `context_window` usa esa ventana.
18. Arquitectura: import-linter en verde; `domain/context.py` sin E/S.

## 5. Evals

El hito toca el bucle, el contexto y un prompt nuevo: la batería entera.

- **Tareas nuevas** (fixtures inventados):
  - `25-historial-previo` (train): empieza con una conversación anterior
    (fichero `history.jsonl` en la tarea) donde la persona ya pidió algo
    y el agente lo hizo a medias; la instrucción dice "sigue". Mide que el
    agente usa lo que hay en el historial.
  - `26-interrumpido` (train): el historial acaba en una respuesta
    cortada con `[interrupted by the user]` (spec 6, §5) y la persona
    corrige el rumbo. Mide que no sigue lo que estaba haciendo.
  - `27-compactar-largo` (train): una tarea de muchos pasos con
    `context_window = 30_000`: compacta al menos una vez. Mide que acaba
    bien después de compactar.
  - `28-compactar-tareas` (validation): igual, con una lista de tareas
    larga: mide que la lista sobrevive y que se vuelve a medir el uso de
    `todo_write` (pendiente de spec 10).
  - `29-grep-contexto` (train): encontrar y arreglar algo en un proyecto
    con ficheros grandes, donde `grep` con contexto ahorra lecturas.
  Con ellas, 29 tareas; la validación, 6 de 29 (21 %).
- **Dos pasadas:** tras el PR de la compactación y tras el de las
  herramientas (§6). Tres modelos (`glm-5.3-flash`, `kimi-k2.7-code`,
  `claude-haiku-5-5`), 5 repeticiones, contra las líneas base del
  2026-11-10.
- **Aceptación:**
  - sin ⚠ en las 24 tareas de antes (en ellas no debe compactar nunca: lo
    fija la traza);
  - las tareas nuevas, al menos 4/5 en cada modelo;
  - en 27 y 28, la compactación ocurre en todas las ejecuciones (si no,
    la tarea no mide nada);
  - los pasos de las tareas largas, anotados, para el tope de §1.13.
- **El conjunto de validación no se mira al escribir `compact.md`.**
- **Líneas base nuevas** al final del hito, con la batería de 29.

El resultado se anota aquí al implementar.

## 6. Orden de piezas para el implementador

Cada punto, un commit pequeño, con tests y lint en verde.

**PR 1 — contar y ver** (`feature/hito-11-contar`)
1. `domain/context.py`: `estimate`, `ContextSize`, `ContextPolicy`.
   *Commit:* "Estimar el tamaño del contexto en el dominio"
2. `[context]` en la configuración. *Commit:* "Añadir la sección context a
   la configuración"
3. `max_tokens` por llamada (§1.3). *Commit:* "Limitar max_tokens a lo que
   queda de ventana"
4. El tamaño de cada llamada en el agente. *Commit:* "Llevar en el agente
   el tamaño de la última llamada"
5. `/context`. *Commit:* "Añadir /context"

**PR 2 — compactar** (`feature/hito-11-compactar`)
1. `prune()` y `tail()`. *Commit:* "Elegir qué se poda y qué cola se
   conserva"
2. `prompts/compact.md` y el `Compactor`. *Commit:* "Resumir la
   conversación con el modelo"
3. Compactar en el bucle (§1.8). *Commit:* "Compactar antes de cada llamada
   si no cabe"
4. `ContextOverflowError` en los dos adaptadores y la repetición.
   *Commit:* "Compactar y repetir cuando el proveedor dice que no cabe"
5. `CompactionEntry`, `replay()` y `SessionTooNew`. *Commit:* "Guardar las
   compactaciones en la sesión"
6. `/compact`, la línea al compactar, `-p` y `/export`. *Commit:*
   "Añadir /compact"
7. Eventos y traza. *Commit:* "Apuntar las compactaciones en la traza"
8. Evals: `history` y `context_window` en las tareas; tareas 25 a 28.
   *Commit:* "Añadir a las evals tareas con historial y con compactación"
9. Evals (§5), anotadas aquí. *Commit:* "Anotar las evals de la
   compactación"

**PR 3 — instrucciones y herramientas** (`feature/hito-11-herramientas`)
1. `nested()` y `touched()`. *Commit:* "Cargar los AGENTS.md de subcarpetas
   al leer allí"
2. `grep` con `context` y `output`. *Commit:* "Dar a grep líneas de
   contexto y modo solo ficheros"
3. El tope de pasos (§1.13) con los números de §5. *Commit:* "Subir el
   tope de pasos a 50"
4. La tarea 29, la pasada de evals y las líneas base nuevas. *Commit:*
   "Anotar las evals y las líneas base del hito 11"

**Cierre** (`docs/cierre-hito-11`): spec IMPLEMENTADA, nota 11 de la
guía, los dos README, `PROYECTO.md`, `MAPA.md`, `HISTORIAL_DESARROLLO.md`
y ESTADO.

## 7. Verificación a mano

En un directorio desechable, con OpenCode Go:
1. `/context` en una sesión nueva: cifras razonables (system prompt,
   herramientas).
2. Con `[context] window = 30_000`: leer varios ficheros grandes hasta que
   compacte solo; la línea lo dice; el agente sigue la tarea.
3. `/compact céntrate en X`: antes y después; el resumen respeta la
   instrucción.
4. Ctrl+C mientras compacta: la conversación sigue como estaba.
5. Salir y `/resume`: la conversación vuelve compactada; `/export` la da
   entera.
6. Un `AGENTS.md` en una subcarpeta: al leer un fichero de allí, el
   resultado lo trae; la segunda vez, no.
7. `maha -p` con `window` pequeña: compacta y el JSON lo cuenta.
8. Con `kimi-k2.7-code`: una sesión larga no falla por `max_tokens`.

## 8. Lo que no viaja por git y lo que necesita la release

- Nada en `.env`. `[context]` es opcional.
- Notas de la release: una sesión compactada no la abre un `maha` anterior
  a esta versión (§1.10).
- `docs/MAPA.md`: `domain/context.py`, `application/context.py`,
  `prompts/compact.md` y las tareas nuevas.

## 9. Guía

`docs/guia/11-ventana-de-contexto.md`: la ventana de contexto.
1. Qué es la ventana y por qué se llena (el modelo no recuerda: se le
   manda todo, nota 2).
2. Contar tokens: lo que da el proveedor y lo que se estima.
3. Podar y resumir: qué se pierde y qué sobrevive, y por qué el código
   guarda una parte.
4. En la industria: resumen, poda, ventana deslizante, la del proveedor.

## 10. Riesgos

- **Un resumen malo** hace que el agente olvide algo y repita o deshaga
  trabajo. Mitigación: estructura fija, parte del código exacta, cola
  intacta y tareas 27 y 28.
- **La estimación se queda corta** (código, idiomas con muchos tokens por
  carácter): la reserva de §1.2 y la repetición tras `ContextOverflowError`
  lo cubren.
- **Romper la caché** en cada compactación: solo al pasar el umbral, y la
  poda solo si libera 20.000 o más.
- **Inyección por el resumen:** un fichero leído con "ignora lo anterior"
  acaba resumido. Mitigación: delimitado y marcado como no confiable en
  `compact.md`; el resumen nunca cambia herramientas ni permisos.
- **Sesiones que el `maha` anterior no abre:** §1.10 y las notas de la
  release.

## 11. Decisiones

Propuestas del agente, para el mantenedor:
1. **Contar con el uso del proveedor y estimar lo nuevo** con caracteres /
   4, sin tokenizador (§1.1).
2. **`window` sin límite por defecto**, y medir en las evals si conviene
   uno (por coste, en modelos con tramo de precio como `claude-haiku-5-5`).
   La alternativa es fijar 200.000 por defecto desde ya.
3. **Dos niveles:** poda y, si no basta, resumen (§1.4, §1.5). Números de
   partida: proteger 40.000, podar solo si libera 20.000, objetivo 60 %,
   cola de 20.000; se ajustan con evals. OpenCode V2 quitó la poda: si en
   las evals no gana al resumen solo, se quita (§1.4).
4. **Resume el modelo de la sesión**, no el pequeño (§1.5).
5. **Parte del código en el resumen**: lista de tareas y ficheros
   cambiados (§1.6).
6. **El error de contexto excedido compacta y repite una vez** (§1.8).
7. **`CompactionEntry` en la sesión**, sin reescribir el fichero, y la
   **política de versiones: el formato solo crece, y un tipo desconocido
   pide actualizar** (§1.10).
8. **`AGENTS.md` de subcarpetas al final del resultado de la herramienta**,
   no en el system prompt (§1.11).
9. **`grep` con `context` y `output`** (§1.12); las descripciones de las
   herramientas no se recortan sin evals.
10. **Tope de pasos a 50** (§1.13), confirmado con las evals.
11. **Sin la compactación del proveedor** (§0).

## 12. Aprendido al implementar

Se añade al implementar.
