Estado: EN CURSO (2026-11-03, rama `fix/auditoria-hito-9`)

# Auditoría profunda tras el hito 9

Pedida por el mantenedor antes de la spec del hito 10: "una auditoría
profunda para asegurarnos que no dejamos deuda técnica". Alcance: todo lo
acumulado (recomendación del agente, aceptada).

Método: cinco revisores independientes, que solo ven el código y AGENTS.md
(bucle y núcleo; sesiones y trazas; modelos y configuración; herramientas y
seguridad; interfaz y evals). Cada hallazgo se comprueba en el código antes
de tocarlo; cada fallo, con su test primero. Después, una revisión
independiente de los arreglos.

Estados: **ARREGLADO** (commit), **POR ARREGLAR**, **DECISIÓN** (del
mantenedor), **NO ES FALLO** (comprobado, con el motivo).

## Modelos y configuración (M)

- **M1.** Un `null` en el uso final de Anthropic borraba los tokens de
  entrada (y con ellos coste y topes). ARREGLADO (`3af1722`).
- **M2.** Ids de llamada que Anthropic rechaza (`^[a-zA-Z0-9_-]+$`) tras
  un `/model` desde otro formato. En las 6.498 llamadas de las evals no
  aparece ninguno (OpenCode los normaliza), pero un servidor declarado por
  la persona puede mandarlos. POR ARREGLAR.
- **M3.** Texto solo de espacios mandado a Anthropic. POR ARREGLAR.
- **M4.** Un `.maha/config.toml` puede subir el coste: `effort`,
  `cache_ttl` y `fallback_model`. DECISIÓN.
- **M5.** OpenAI: un contador raro en el uso (`10.5`, `choices: null`)
  pierde la respuesta entera. POR ARREGLAR.
- **M6.** OpenAI: un `rate_limit_error` a mitad de stream sale como "no
  disponible". POR ARREGLAR.
- **M7.** Una clave con caracteres no ASCII acaba con una traza de Python.
  POR ARREGLAR.
- **M8.** HTTP 408 no se reintenta. POR ARREGLAR.
- **M9.** Datos del catálogo. NO ES FALLO: Sonnet 4.6 tiene 128K de
  salida en la documentación oficial; los precios y formatos de Zen son
  los de OpenCode (`qwen3.8-max` y `minimax-m3` van por OpenAI en Zen).
- **M10.** Menores: un booleano aceptado como número en el TOML; un
  `endpoints` para el propio formato, ignorado sin aviso; el docstring de
  `config.py` sin `cache_ttl`; envoltorios sobrantes en `openai_chat.py`;
  `complete()` de Anthropic puede guardar una firma vacía; ningún test de
  `anthropic_version` de punta a punta. POR ARREGLAR.

## Bucle y núcleo (B)

- **B1.** El bucle no mira el motivo de parada: una respuesta cortada por
  la salida máxima acaba como `end_turn`, y una llamada cortada se repite
  hasta `max_steps`. POR ARREGLAR.
- **B2.** Cortar el turno justo en `ModelCallFinished` pierde una
  respuesta que la persona ya vio. POR ARREGLAR.
- **B3.** El acumulador junta dos llamadas distintas que comparten índice.
  POR ARREGLAR.
- **B4.** El tiempo límite del turno cuenta lo que la persona tarda en
  leer una petición de permiso. DECISIÓN.
- **B5.** El escape del delimitador `<stdin>` es una lista negra con
  huecos. POR ARREGLAR (delimitador con un valor al azar por ejecución).
- **B6.** Un `ApprovalGate` que lanza una excepción, sin test. POR ARREGLAR.
- **B7.** `ModelClient.complete()` no tiene quien la llame en `src`.
  NO ES FALLO: el mantenedor decidió conservarla (spec 3, §1.2).
- **B8.** Deuda: `Agent.run()` es una función de unas 230 líneas con siete
  marcas; `Accumulator.text` une bloques sin separador; el docstring de
  `events.py`; los nombres de herramienta no se comprueban contra las
  reglas de los proveedores. DECISIÓN (la refactorización) y POR ARREGLAR
  (el resto).

## Sesiones y trazas (S)

- **S1.** Un corte a mitad de guardar un turno puede dejar la sesión sin
  poder retomarse. POR ARREGLAR.
- **S2.** Retomar una sesión de otro proveedor con `-m` o `/model` apunta
  el modelo ajeno en el fichero del proveedor original. POR ARREGLAR.
- **S3.** Borrar desde otro `maha` una sesión en su primer turno borra su
  traza sin avisar. POR ARREGLAR.
- **S4.** `maha import` acepta costes con exponentes enormes. POR ARREGLAR.
- **S5.** `maha export --format json` saca caracteres de control (DEL, C1,
  bidi) tal cual a la terminal. POR ARREGLAR.
- **S6.** Una carpeta de trazas ilegible no da error (Python 3.14 calla el
  error de `glob`). POR ARREGLAR.
- **S7.** `JsonlTraceSink.read()` sigue enlaces simbólicos. POR ARREGLAR.
- **S8.** Deuda: un comentario desplazado; ningún test de ida y vuelta
  export → import con el almacén real. POR ARREGLAR.

## Herramientas y seguridad (H)

(Pendiente del revisor.)

## Interfaz y evals (I)

(Pendiente del revisor.) Ya conocido: la puerta de las evals marca ⚠ con
un solo fallo en 5 repeticiones (spec 9, §12.18).

## Otros

- `pulse-alpha-free` en el catálogo de Zen. ARREGLADO (`25f1157`).
