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
  la persona puede mandarlos. ARREGLADO (`2f8bbe6`).
- **M3.** Texto solo de espacios mandado a Anthropic. ARREGLADO (`11fd3eb`).
- **M4.** Un `.maha/config.toml` puede subir el coste: `effort`,
  `cache_ttl` y `fallback_model`. DECISIÓN del mantenedor (2026-11-03):
  se mantiene lo que el proyecto puede elegir, pero `maha` lo dice al
  arrancar. POR ARREGLAR.
- **M5.** OpenAI: un contador raro en el uso (`10.5`, `choices: null`)
  pierde la respuesta entera. ARREGLADO (`4c22614`).
- **M6.** OpenAI: un `rate_limit_error` a mitad de stream sale como "no
  disponible". ARREGLADO (`4c22614`).
- **M7.** Una clave con caracteres no ASCII acaba con una traza de Python.
  ARREGLADO (`ef41778`).
- **M8.** HTTP 408 no se reintenta. ARREGLADO (`ee35652`).
- **M9.** Datos del catálogo. NO ES FALLO: Sonnet 4.6 tiene 128K de
  salida en la documentación oficial; los precios y formatos de Zen son
  los de OpenCode (`qwen3.8-max` y `minimax-m3` van por OpenAI en Zen).
- **M10.** Menores: un booleano aceptado como número en el TOML; un
  `endpoints` para el propio formato, ignorado sin aviso; el docstring de
  `config.py` sin `cache_ttl`; envoltorios sobrantes en `openai_chat.py`;
  `complete()` de Anthropic puede guardar una firma vacía; ningún test de
  `anthropic_version` de punta a punta. ARREGLADO (`1dd9df1`, `1f287b8`),
  salvo el test de punta a punta, POR ARREGLAR.

## Bucle y núcleo (B)

- **B1.** El bucle no mira el motivo de parada: una respuesta cortada por
  la salida máxima acaba como `end_turn`, y una llamada cortada se repite
  hasta `max_steps`. POR ARREGLAR.
- **B2.** Cortar el turno justo en `ModelCallFinished` pierde una
  respuesta que la persona ya vio. ARREGLADO (`cabd2d8`), con un fallo que
  el propio arreglo traía (las llamadas nuevas heredaban los resultados del
  paso anterior), encontrado con su test.
- **B3.** El acumulador junta dos llamadas distintas que comparten índice.
  POR ARREGLAR.
- **B4.** El tiempo límite del turno cuenta lo que la persona tarda en
  leer una petición de permiso. DECISIÓN del mantenedor (2026-11-03): no
  se cuenta la espera a la persona. POR ARREGLAR.
- **B5.** El escape del delimitador `<stdin>` es una lista negra con
  huecos. POR ARREGLAR (delimitador con un valor al azar por ejecución).
- **B6.** Un `ApprovalGate` que lanza una excepción, sin test. POR ARREGLAR.
- **B7.** `ModelClient.complete()` no tiene quien la llame en `src`.
  NO ES FALLO: el mantenedor decidió conservarla (spec 3, §1.2).
- **B8.** Deuda: `Agent.run()` es una función de unas 230 líneas con siete
  marcas; `Accumulator.text` une bloques sin separador; el docstring de
  `events.py`; los nombres de herramienta no se comprueban contra las
  reglas de los proveedores. POR ARREGLAR, también la refactorización de
  `Agent.run()`: el agente la hace al final de la auditoría, protegida por
  los tests y con evals antes del merge.

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

- **H1.** Un patrón de `glob` o una regla de `.gitignore` con muchos `*`
  tarda un tiempo exponencial en el proceso principal y congela `maha`
  (37 s con 8 estrellas y 60 caracteres); Ctrl+C no lo para. Un repositorio
  clonado puede traer la regla. ARREGLADO: `domain/wildcard.py`, comodines
  en tiempo lineal para `glob` y `.gitignore`.
- **H2.** Un nombre de fichero que no es UTF-8 llega al resultado con
  sustitutos y rompe la petición al modelo, y la sesión ya no avanza. POR
  ARREGLAR.
- **H3.** "Siempre en esta sesión" para `write_file` cubre ficheros que
  ejecutan código solos: `.venv/…/x.pth` (Python lo ejecuta al arrancar,
  también el proceso de búsqueda de `maha`, con la clave en el entorno),
  `node_modules`, `.mcp.json`, `.cursor/`, `.zed/`, `.nvim.lua`, `.exrc`,
  `.cargo/config.toml`… POR ARREGLAR.
- **H4.** Si el shell del comando pasa a ser de root (`sudo -n` sin
  contraseña), el tiempo límite no se cumple: la espera tras matar no tiene
  tope. POR ARREGLAR.
- **H5.** Menores: con el directorio de trabajo dentro de una carpeta de
  secretos (`~/.aws`, `~/.ssh`), sus ficheros se leen sin preguntar; el
  tamaño de un secreto se dice antes de preguntar; un enlace duro hacia
  `.git/hooks` se escribe en el sitio; un NUL en un comando sale como error
  interno; el recorrido solo cuenta ficheros, no carpetas. POR ARREGLAR.

## Interfaz y evals (I)

- **I1.** Las comprobaciones de las tareas 06, 08, 12, 14, 15, 19 y 20
  ejecutan los tests de la copia del agente, también los que él añade o
  cambia: suspenden código correcto (el "105.0 en vez de 99.0" de GLM en la
  spec 9, §5, era correcto: el test que fallaba lo había escrito el modelo)
  y aprueban trampas (un `return 80` con el otro assert cambiado por
  `pass`). POR ARREGLAR.
- **I2.** Todo `ModelError` cuenta como "error del proveedor" y sale del
  éxito, también un 4xx por una petición rota de `maha` o una respuesta que
  no se entiende: una regresión de `maha` se esconde. POR ARREGLAR.
- **I3.** El modelo de una sesión retomada sale sin escapar en la cabecera
  de la conversación (inyección de escapes de terminal con `maha import`).
  POR ARREGLAR.
- **I4.** La puerta de las evals es sobre todo ruido: con 17-20 tareas a
  5/5, la probabilidad de al menos un ⚠ sin cambiar nada es del 57-95 %, y
  el total marca cualquier bajada. DECISIÓN del mantenedor (2026-11-03):
  prueba estadística (Fisher exacto por tarea, dos proporciones en el
  total, p < 0,05; coste y pasos con un +20 % sobre el límite bajo de su
  intervalo), con la p en el informe y sin repeticiones automáticas. POR
  ARREGLAR.
- **I5.** Las comprobaciones ejecutan en el puesto, sin aislar, código que
  escribió el modelo. DECISIÓN del mantenedor (2026-11-03): mitigar ya (un
  HOME temporal vacío, sin XDG ni credenciales) y aislar del todo con el
  sandbox del hito 15. POR ARREGLAR.
- **I6.** `maha eval` no trata SIGTERM ni SIGHUP, y `maha eval | head`
  pierde `runs.json`. POR ARREGLAR.
- **I7.** Con `--effort` se compara con una línea base de otro effort. POR
  ARREGLAR.
- **I8.** "in all" no cuenta lo pagado por las ejecuciones con error. POR
  ARREGLAR.
- **I9.** Mensajes que engañan: "the check exited with None" (un
  comprobador matado), la línea de una ejecución sin el porqué,
  "provider errors" que incluye los internos, `--keep` sin decir dónde.
  POR ARREGLAR.
- **I10.** Comprobaciones flojas en las tareas 03, 09 y 13. POR ARREGLAR.
- **I11.** Si una llamada falla a mitad de turno, `-p` da como respuesta
  el texto del paso anterior. POR ARREGLAR.
- **I12.** Con denegaciones mezcladas, `-p` da la pista equivocada. POR
  ARREGLAR.
- **I13.** Deuda: una tarea nueva tras la línea base queda fuera sin aviso;
  `--save` acepta errores y `--repeat 1`. POR ARREGLAR.

## Otros

- `pulse-alpha-free` en el catálogo de Zen. ARREGLADO (`25f1157`).
