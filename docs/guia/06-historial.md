# 06. Historial y sesiones: el modelo no recuerda, el disco sí

Hito 6 (`v0.6.0`). Spec: `docs/specs/hito-6-sesiones.md`. Diseño:
`docs/DESIGN.md` §5, §6, §7 y §10.

## El problema

El modelo no recuerda nada entre llamadas (nota 02): el arnés le manda la
conversación entera cada vez. Hasta el hito 5 esa conversación vivía en
memoria, así que al salir de `maha` se perdía. Y una respuesta cortada con
Ctrl+C quedaba en pantalla, pero el modelo no sabía que la había empezado.

## Cómo lo resuelve M-Harness

### 1. El historial es la memoria del modelo

Retomar una sesión es volver a mandar sus mensajes. Nada más:

```
> /resume
  [resumed 20261026-141616-2ec4 · 4 messages · glm-5.3-flash]
> ¿Cómo me llamo? Responde con una palabra.
Ana
```

El `Agent` no sabe nada del disco. Empieza con un historial
(`history=`) y una `Conversation` (en `application`) guarda, al terminar
cada turno, lo que el `Agent` conservó: también tras Ctrl+C o un fallo del
modelo.

### 2. Un JSONL que solo crece

Un fichero por sesión en `~/.local/share/maha/sessions/`: una cabecera y
una línea por entrada.

- *JSONL:* un objeto JSON por línea.

```json
{"type": "session", "version": 1, "id": "20261026-141616-2ec4", "cwd": "/home/ana/proyecto", ...}
{"type": "message", "message": {"role": "user", "blocks": [{"type": "text", "text": "Me llamo Ana."}]}}
{"type": "usage", "usage": {"input_tokens": 1255, "output_tokens": 3, ...}}
{"type": "model", "model": "kimi-k3"}
```

- **Solo se añade.** Un turno es una sola escritura y después `fsync`. Si
  `maha` muere a mitad, como mucho queda rota la **última** línea: sin su
  salto de línea, se sabe que está cortada. Al abrir se ignora y se recorta.
  Una línea rota en medio, o una versión desconocida, es una sesión corrupta.
- **Solo la lee el usuario** (`0600`). Guarda todo lo que leyó el agente,
  también un secreto que aprobaste leer. Fuera del repositorio siempre.
- **Bloqueada mientras está abierta** (`flock`): dos `maha` no mezclan sus
  turnos en el mismo fichero.

  ```
  > /resume 20261026-141706-9fca
  error: session 20261026-141706-9fca is open in another maha
  ```

  - *`flock`:* un candado sobre un fichero abierto; se suelta al cerrarlo o
    al morir el proceso.
- **El id llega al disco solo si tiene su forma** (fecha UTC y 4 hex):
  `/resume ../../etc/passwd` no abre nada.

### 3. Un historial que se puede mandar

La API rechaza (error 400) un historial donde una llamada a herramienta no
tiene su resultado justo detrás. `check_history()` lo comprueba al retomar:
mejor saberlo antes que en la primera llamada. El bucle ya lo garantiza al
guardar (nota 05, "lo ejecutado consta").

### 4. La respuesta cortada, guardada y marcada

Si Ctrl+C llega mientras el modelo escribe, el texto que ya viste se guarda
como un mensaje del asistente con `interrupted=True`. El adaptador de OpenAI
lo cuenta al final del texto: `[interrupted by the user]`. En la
verificación:

```
> ¿Terminaste tu respuesta anterior o te corté?
Me cortaste, así que el texto quedó inacabado justo cuando llegaba al siglo
XVI; si quieres, puedo continuarlo.
```

- **Una marca en el dominio, no un texto:** si fuera texto del asistente, el
  modelo aprendería a escribirla. Cada adaptador la cuenta a su manera.
- **Una llamada a medio llegar se descarta:** nunca se ejecutó.
- **Un fallo del modelo a mitad no guarda nada:** el texto puede estar roto,
  y el turno se repite.

### 5. Todas las sesiones, desde cualquier directorio

`/sessions` enseña las de todos los directorios; las de este, con `*`:

```
  * 20261026-141706-9fca  2026-10-26 15:17  8 messages  ~/proyecto  Crea el fichero uno.txt…
    20261025-174233-b01c  2026-10-25 17:42  4 messages  ~/web       explícame el router
```

Se retoma cualquiera, pero **las herramientas no se mudan**: siguen sobre el
directorio donde abriste `maha`, y te lo dice:

```
  [this session was in ~/proyecto; tools work in ~/web]
```

Cambiar el perímetro a mitad de conversación, sin preguntar, sería un
permiso que nadie dio. `/resume` sin id toma la más reciente **de este
directorio** que no sea la actual ni esté abierta en otro `maha`.

### 6. Lo que no se recupera: las aprobaciones

Retomar crea un `Agent` nuevo, con su "toda la sesión" vacío. Un "siempre"
de ayer para `rm -rf build` es autonomía que nadie dio hoy. En la
verificación, una escritura aprobada con `a` volvió a preguntar tras
`/resume`.

### 7. El disco detrás de un puerto

`SessionStore` (ports) tiene dos implementaciones: `JsonlSessionStore`
(adapters) y `MemorySessionStore` (tests). `Sessions` y `Conversation`
(application) no saben cuál hay, y tampoco qué cliente ni qué herramientas
tiene el `Agent`: lo crea una fábrica que les da `bootstrap`. Un fallo del
disco no corta la conversación: se avisa y se reintenta en el turno
siguiente. Para que el reintento no duplique nada, una escritura que falla
se deshace: se recorta el fichero al tamaño que tenía antes.

```
warning: session not saved: cannot save session 20261026-…: No space left on device
```

## En la industria

| Pieza | M-Harness | Alternativas | Cuándo se elegirían |
|---|---|---|---|
| Formato | JSONL por sesión, solo se añade | JSON entero por sesión; SQLite (Sessions del OpenAI Agents SDK); checkpointers de LangGraph (estado del grafo en cada paso) | Consultas entre sesiones; muchas sesiones o muy largas |
| Dónde | `~/.local/share/maha/sessions/` (XDG), todas juntas | Una carpeta por proyecto (Claude Code: `~/.claude/projects/<carpeta>/`); en la nube | Sincronizar entre máquinas |
| Retomar | `/resume` dentro, de cualquier directorio | Opciones al arrancar (`--continue`, `--resume`); bifurcar una sesión | Scripts (hito 8); probar dos caminos desde un punto |
| Respuesta cortada | Campo del mensaje, marca en el adaptador | Mensaje del usuario "[interrupted]"; no guardarla | Formatos que no admiten metadatos |
| Dos procesos | `flock` sobre el fichero abierto | Un servidor que posee las sesiones; bases de datos con transacciones | Varios usuarios |

*Lo de Claude Code es lo observado en el puesto del agente (spec 6, §1.1).*
