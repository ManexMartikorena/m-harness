# 11. El contexto virtual: ventana fija, archivo y `recall`

Hito 11 (`v0.11.0`). Spec: `docs/specs/hito-11-contexto.md`.
Diseño: `docs/DESIGN.md` §4 (pieza 7) y §14.

## El problema

Un modelo no recuerda nada entre llamadas (guía 02): en cada paso, el
agente le reenvía la conversación entera. En un agente eso pesa el doble:

- **Lo que entra una vez se paga en todos los pasos siguientes.** Leer un
  fichero de 16.000 caracteres son unos 4.000 tokens en esa llamada, y otra
  vez en cada una de las que vienen.
- **El modelo trabaja peor** con mucho texto viejo delante.
- **Al final no cabe.** El proveedor rechaza la llamada, o la corta en
  silencio, y la sesión ya no sirve.

## Cómo lo resuelve M-Harness

### 1. Contar tokens

- *Token:* el trozo de texto con el que cuenta un modelo, unos 4
  caracteres en inglés.
- **Lo exacto lo da el proveedor:** cada respuesta dice cuántos tokens tuvo
  su petición. Lo nuevo desde entonces, `maha` lo estima con caracteres
  / 4, sin tokenizador: cada familia de modelos cuenta a su manera.
- `/context` lo enseña, por partes:

```
> /context
  budget 20,000 · window 1,000,000 · archives at 20,000
  system prompt       909   (base 819 · environment 90)
  tools             2,191   (10 tools)
  archive index       804   (11 messages archived)
  messages         25,344   (tool results 24,622)
  total            28,488   (142.4 % of 20,000 · last call 28,283)
  cache         last call 3,520 of 28,283 read from cache (12.4 %)
```

### 2. Una ventana de tamaño fijo

- *Ventana de contexto:* cuántos tokens caben en una llamada. Sale del
  catálogo de modelos.
- *Presupuesto de trabajo:* lo máximo que `maha` manda en una llamada.
  **100.000 tokens por defecto, igual para todos los modelos**, salvo que
  la ventana del modelo sea menor (`[context] budget` lo cambia, y un
  proyecto solo puede bajarlo).
- Así cada llamada cuesta casi lo mismo, aunque la sesión tenga un millón
  de tokens.

### 3. Archivar en vez de borrar

Cuando lo siguiente no cabe, los pasos más viejos salen de la ventana. No
se pierden: van al **archivo de la sesión**.

- *Archivo:* una base SQLite por sesión, con FTS5 (la búsqueda por texto
  de SQLite, de la biblioteca estándar de Python).
- *Archivero:* un modelo barato que resume lo que sale y mantiene un
  **índice**, siempre visible para el modelo bueno.
- **Se archiva por pasos enteros:** una llamada nunca queda sin su
  resultado. También a mitad de turno.

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

En la terminal se ve así:

```
  [archiving 28,522 tokens of earlier steps…]
  [archived: 28,522 → 4,535 tokens; $0.0033]
```

Es como la **memoria virtual** de un sistema operativo. La ventana es la
memoria de trabajo. El archivo es el disco, de donde se trae una página
cuando hace falta.

### 4. `recall`: traer del archivo lo que hace falta

Una herramienta de lectura, sin aprobación: buscar con FTS5 o leer un
elemento por líneas.

```json
{"query": "cocina cámara de frío"}
{"id": "msg-13", "offset": 1, "limit": 120}
```

Visto en la verificación del hito, con todo el principio ya archivado:

```
> Sin volver a leer ningún fichero: ¿qué código de lote tenía estado.txt…?
  → recall(query="cocina cámara de frío informe lo más urgente")
  ✓ 5 found
  → recall(id="msg-13", offset=1, limit=120)
  ✓ read
- estado.txt — código de lote: KX-4471-Q.
```

Tres cosas aprendidas al medirlo:

- **El índice tiene que ser honesto.** El archivero solo lee el principio
  y el final de cada bloque largo. Si escribe "solo había INFO y AVISO",
  el modelo le cree y no busca. Ahora tiene prohibido afirmar lo que no
  vio, y decir que algo se perdió.
- **El fragmento de cada resultado lo calcula `maha`.** El `snippet()` de
  FTS5 crece con el cuadrado de las coincidencias: en una salida de
  400.000 líneas tardaba más de dos minutos. El de `maha`, 0,16 s.
- **Una tarea de evals lo mide (la 30).** El dato solo está en lo
  archivado y no en el índice, así que solo `recall` lo encuentra. Lo usa
  en las 15 ejecuciones, con los tres modelos.

### 5. Las salidas grandes, al archivo desde el principio

- Un resultado de más de 40.000 caracteres va entero al archivo. El modelo
  recibe el principio, el final y el id para leer el resto:

  ```
  … [output cut: 7,849,209 of 7,888,908 characters left out; the whole output
  is archived as out-7; read it with recall(id="out-7", offset=…)]
  ```
- **Un paso que no cabe entero** (seis lecturas grandes en una sola
  respuesta) se recorta antes de que lo vea el modelo, a partes iguales y
  con lo entero en el archivo. Un paso no se parte, y el último no se
  archiva: sin esto, la llamada salía al 142 % del presupuesto.

### 6. La caché del prompt

- *Caché del prompt:* el proveedor cobra a un 10 % la parte del principio
  de la petición que ya vio, byte a byte.
- Por eso **nada de lo ya enviado se reescribe**: ni el system prompt ni
  los resultados viejos. Archivar sí cambia el principio, y esa llamada
  paga entera; las siguientes vuelven a leer de la caché.
- En las evals del cierre, del 60 % (Haiku) al 81 % (Kimi) de la entrada
  se lee de la caché.

### 7. Instrucciones de subcarpetas y `grep` con contexto

- **`AGENTS.md` de subcarpetas:** al leer o cambiar un fichero de
  `api/`, su `api/AGENTS.md` llega al final de ese resultado, una vez. No
  en el system prompt, que rompería la caché.

  ```
  <instructions source="api/AGENTS.md">
  Los tests de este paquete se lanzan con `make test`.
  </instructions>
  ```
- **`grep` con `context`:** enseña las líneas de alrededor sin leer el
  fichero entero. `"output": "files"` da solo las rutas, y `"count"`
  cuántas coincidencias hay. Esos dos no dicen qué coincidió, y la guía
  del prompt lo avisa: GLM llegó a una conclusión falsa con `count`.
- **El tope de pasos sube de 25 a 50:** con la ventana fija, cada paso
  tiene un coste acotado.

## En la industria

- **Compactar por resumen** (Claude Code, OpenCode, Codex): el modelo
  resume todo y se sigue desde el resumen. Es lo más probado, pero lo
  viejo se pierde para el modelo.
- **Contexto virtual** (MemGPT/Letta, Hermes Agent): una ventana fija, lo
  viejo en un almacén con búsqueda y una herramienta para recuperarlo. Es
  lo que hace `maha`.
- **Poda de resultados** (OpenCode, Claude Code): borra salidas viejas, sin
  modelo. Es barata, pero rompe la caché.
- **Del proveedor** (Anthropic *context editing* y *compaction*): la API
  poda o resume. Es de un solo formato, y saca una pieza del agente fuera
  de `maha` (DESIGN §7.1).
