Estado: EN CURSO (2026-11-10)

# Auditoría tras el hito 10

Pedida por el mantenedor al cerrar el hito 10: "auditar para asegurarnos
al 100 % que el proyecto está con 0 errores y que empezamos el hito 11 con
0 deuda técnica, teniendo en cuenta que el objetivo es tener un producto
competitivo y muy bueno". Alcance: todo el código, no solo el del hito 10.

Método, el de la auditoría tras el hito 9:
- **Cinco revisores independientes**, que solo ven el código, AGENTS.md y
  DESIGN: bucle y núcleo (B); sesiones y trazas (S); modelos y
  configuración (M); herramientas y seguridad (H); interfaz y evals (I).
- **Las mejoras de producto** que propusieron (no son fallos) las evalúan
  tres agentes Opus independientes, al máximo esfuerzo; se hacen las que
  vean buenas (decisión del mantenedor, 2026-11-10). Ver "Producto (P)".
- Cada hallazgo se comprueba en el código antes de tocarlo; cada fallo,
  con su test primero. Después, una revisión independiente de los
  arreglos, y las evals contra las líneas base del 2026-11-10.

Estados: **ARREGLADO** (commit), **POR ARREGLAR**, **DECISIÓN** (del
mantenedor), **NO ES FALLO** (comprobado, con el motivo).

## Decisiones del mantenedor (2026-11-10)

1. **`/init` en una subcarpeta** (I3): mira y escribe el `AGENTS.md` de esa
   carpeta, que `maha` ya carga de la raíz hacia abajo, y lo dice. Desde la
   raíz, como hasta ahora.
2. **Pegar texto de varias líneas** (I4): *bracketed paste* ahora, con un
   respaldo que une las líneas que llegan juntas.
3. **El título al salir** (S7): esperar siempre al título. Si tarda, `maha`
   dice que espera y Ctrl+C lo salta; al retomar una sesión sin título, se
   pide.
4. **Las mejoras de producto:** las que tres agentes Opus, al máximo
   esfuerzo, vean buenas.

## Bucle y núcleo (B)

- **B1.** Una llamada cortada por un rechazo del proveedor
  (`content_filter`) llega con argumentos `""` y, si la herramienta no
  tiene parámetros obligatorios, se ejecuta; el turno sigue en vez de
  acabar en `refused`. POR ARREGLAR.
- **B2.** Lo gastado en un paso cortado (Ctrl+C, tiempo límite, fallo a
  mitad de stream) no se cuenta: el uso solo llega con `MessageEnd`.
  Anthropic manda la entrada ya en `message_start`. POR ARREGLAR.
- **B3.** El nombre de una llamada se concatena trozo a trozo: un servidor
  que lo repite da `read_fileread_file`. POR ARREGLAR.
- **B4.** `KeyboardInterrupt` es corte del usuario en `Conversation` y
  error interno en `Agent`; un comentario de `sessions.py` habla de un
  tiempo límite que nunca llega ahí. POR ARREGLAR.
- **B5.** El modelo de respaldo recibe el system prompt con la capa de
  familia del principal. POR ARREGLAR.
- **B6.** Deuda: la pausa del reloj repetida en `_decide` y
  `_wait_for_user`; el parseo de argumentos repetido; `NO_RETRIES` solo lo
  usan los tests. POR ARREGLAR.

## Sesiones y trazas (S)

- **S1.** Carrera entre el título y el turno: lo que entra en `_pending`
  durante el `await` del guardado se borra al vaciarla. Hoy no ocurre
  porque el adaptador JSONL no cede, pero el puerto es asíncrono. POR
  ARREGLAR.
- **S2.** `-c` y `/resume` sin id saltan en silencio una sesión ilegible y
  retoman otra más antigua; `/sessions` no la enseña. POR ARREGLAR.
- **S3.** El coste de la sesión y `/trace` dan "sin precio" al turno entero
  si una de sus llamadas no tiene precio; `maha stats` suma por llamada.
  POR ARREGLAR.
- **S4.** `close()` se corta si la tarea del título acabó con una
  excepción que no es `CancelledError`. POR ARREGLAR.
- **S5.** Si el primer turno no se pudo guardar, la sesión no recibe
  título nunca. POR ARREGLAR.
- **S6.** `/delete` de una sesión que no existe, con una traza ilegible,
  dice que se borró. POR ARREGLAR.
- **S7.** El título cancelado al salir se paga y no queda registrado.
  DECISIÓN 3. POR ARREGLAR.
- **S8.** `Conversation.titled()` solo lo usan los tests. Con la decisión
  3 lo usa `close()`. POR ARREGLAR.

## Modelos y configuración (M)

- **M1.** Un patrón absoluto en `instructions` del usuario
  (`"/home/yo/notas/*.md"`) tira `maha` al arrancar (`ValueError` en
  `relative_to`). POR ARREGLAR.
- **M2.** Un `AGENTS.md` grande se recorta dos veces, y el aviso dice mal
  cuánto (30 bytes en lugar de 34.464). POR ARREGLAR.
- **M3.** OpenAI: un `"delta": null` en un trozo tira la respuesta entera.
  POR ARREGLAR.
- **M4.** A los modelos Claude de OpenCode Go y Zen les falta
  `cache_write_1h`. Hay que comprobar el precio en la documentación de
  OpenCode. POR ARREGLAR.
- **M5.** Deuda: `_int` en los dos adaptadores (ya hay `count` en
  `http.py`), `CacheTtl` y la versión de Anthropic escritos dos veces. POR
  ARREGLAR.
- **M6.** `opencode-zen/jev-1.13`: entrada de pago y salida gratis, sin
  `context` ni `max_output`. Por comprobar en la documentación de Zen. POR
  ARREGLAR.
- **M7.** El precio de `claude-haiku-5-5` en OpenCode (pendiente de
  ESTADO): las cuentas encajan con 0,50/2,50 $ por millón sin descuento de
  caché. Por comprobar en la documentación de OpenCode Go. POR ARREGLAR.

## Herramientas y seguridad (H)

- **H1.** `[a] always this session` no dice qué cubre: en una edición,
  todas las ediciones del directorio. POR ARREGLAR.
- **H2.** `edit_file`: la búsqueda flexible de un `old_string` de varias
  líneas es O(líneas × líneas) y corre antes de preguntar; 800 KB bloquean
  `maha` 19 s sin atender a Ctrl+C. POR ARREGLAR.
- **H3.** `grep` lanza un Python por cada lote de 500 ficheros (0,26 s cada
  uno): 10.000 ficheros, 5 s; en WSL puede pasar su tiempo límite. POR
  ARREGLAR.
- **H4.** De la salida de un comando solo se guarda el principio: el
  resumen de fallos de un `pytest` largo nunca llega al modelo. POR
  ARREGLAR.
- **H5.** `grep` con `a{99999999999}` o un anidamiento enorme sale como
  error interno (`OverflowError`, `RecursionError`). POR ARREGLAR.
- **H6.** El ámbito "always" de `run_command` no incluye el tiempo límite
  que la pregunta enseña. POR ARREGLAR.
- **H7.** Faltan en la lista de lo que ejecuta código: `.hg/hgrc`,
  `Jenkinsfile`, `.travis.yml`, `azure-pipelines.yml`,
  `bitbucket-pipelines.yml`, `.buildkite/`, `.drone.yml`, `.woodpecker*`,
  `.nvimrc`, `.vimrc`, `.gvimrc` y `lefthook.yml`. POR ARREGLAR.
- **H8.** `XDG_RUNTIME_DIR` llega a los comandos y abre el bus de sesión
  (llavero, agente SSH). POR ARREGLAR.
- **H9.** El proceso de búsqueda hereda el entorno completo de `maha`,
  clave incluida. POR ARREGLAR.
- **H10.** Una línea enorme (un JS minificado) llena la pregunta de
  aprobación de `write_file`. POR ARREGLAR.
- **H11.** Una ruta en un bucle de enlaces o con un nombre demasiado largo
  se pregunta y falla después. POR ARREGLAR.
- **H12.** El comentario de `ApprovalRequest.title` dice que se corta, y no
  se corta (A3). POR ARREGLAR.
- **H13.** `_check_grep` devuelve una regex que nadie usa. POR ARREGLAR.

## Interfaz y evals (I)

- **I1.** `maha prompt` saca sin limpiar el texto de los `AGENTS.md` a la
  terminal: uno de un repo ajeno puede borrar la pantalla o escribir en el
  portapapeles (OSC 52). POR ARREGLAR.
- **I2.** Ctrl+C en `maha sessions`, `trace`, `stats`, `export`, `import`
  o `prompt`, o al arrancar la conversación, da un traceback. POR
  ARREGLAR.
- **I3.** `/init` en una subcarpeta apunta a la raíz git, fuera del
  directorio de trabajo. DECISIÓN 1. POR ARREGLAR.
- **I4.** Un texto de varias líneas pegado se manda como un turno por
  línea. DECISIÓN 2. POR ARREGLAR.
- **I5.** `ask_user`: `"²"` pasa `isdigit()` y rompe la herramienta. POR
  ARREGLAR.
- **I6.** `ask_user`: con opciones `2` y `4`, teclear `2` elige `4`. POR
  ARREGLAR.
- **I7.** `/export` y `maha export` titulan el Markdown con la primera
  línea, no con el título de la sesión. POR ARREGLAR.
- **I8.** Ctrl+C durante un comando (`/delete` pidiendo confirmación,
  `/trace`) cierra `maha`. POR ARREGLAR.
- **I9.** `maha -p "/init"` manda el texto literal; las evals sí lo
  expanden. POR ARREGLAR.
- **I10.** `clean()` escapa el `\r` de un `\r\n`: cada línea de un texto
  CRLF se ve con `\x0d`. POR ARREGLAR.
- **I11.** La pregunta de aprobación pinta en color sin mirar si es una
  terminal. POR ARREGLAR.
- **I12.** Evals: la copia del fixture se lleva lo que git no sigue
  (`__pycache__`); la comprobación de la tarea 24 exige la palabra
  `español`. POR ARREGLAR.
- **I13.** La ayuda de `--allow` se lee como si los secretos de dentro se
  permitieran; `maha prompt -h` no explica sus opciones. POR ARREGLAR.
- **I14.** `Evaluator.check()` solo lo usan los tests. POR ARREGLAR.
- **I15.** `maha import` lee el fichero entero sin tope. POR ARREGLAR.

## Producto (P)

Las propuestas de los revisores, evaluadas por tres agentes Opus
independientes. *Se anota al recibir su veredicto.*

## Aprendido al implementar

*Se añade al implementar.*
