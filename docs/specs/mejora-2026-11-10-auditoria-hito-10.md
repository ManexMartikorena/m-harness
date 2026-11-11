Estado: EN CURSO (2026-11-11). Hechos: B, S, H, I, M y P, salvo M4, que
espera una decisión del mantenedor. Faltan la revisión independiente de
los arreglos, las evals y `v0.10.1`.

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
  acabar en `refused`. ARREGLADO (`5f3ed87`).
- **B2.** Lo gastado en un paso cortado (Ctrl+C, tiempo límite, fallo a
  mitad de stream) no se cuenta: el uso solo llega con `MessageEnd`.
  Anthropic manda la entrada ya en `message_start`. ARREGLADO (`5b2896f`).
- **B3.** El nombre de una llamada se concatena trozo a trozo: un servidor
  que lo repite da `read_fileread_file`. ARREGLADO (`4b3404e`).
- **B4.** `KeyboardInterrupt` es corte del usuario en `Conversation` y
  error interno en `Agent`; un comentario de `sessions.py` habla de un
  tiempo límite que nunca llega ahí. ARREGLADO (`5b2896f`).
- **B5.** El modelo de respaldo recibe el system prompt con la capa de
  familia del principal. ARREGLADO (`e40ed08`).
- **B6.** Deuda: la pausa del reloj repetida en `_decide` y
  `_wait_for_user`; el parseo de argumentos repetido; `NO_RETRIES` solo lo
  usan los tests. ARREGLADO (`dbdc44c`).

## Sesiones y trazas (S)

- **S1.** Carrera entre el título y el turno: lo que entra en `_pending`
  durante el `await` del guardado se borra al vaciarla. Hoy no ocurre
  porque el adaptador JSONL no cede, pero el puerto es asíncrono.
  ARREGLADO (`8d3a4f9`).
- **S2.** `-c` y `/resume` sin id saltan en silencio una sesión ilegible y
  retoman otra más antigua; `/sessions` no la enseña. ARREGLADO (`c93f049`).
- **S3.** El coste de la sesión y `/trace` dan "sin precio" al turno entero
  si una de sus llamadas no tiene precio; `maha stats` suma por llamada.
  ARREGLADO (`c73d447`).
- **S4.** `close()` se corta si la tarea del título acabó con una
  excepción que no es `CancelledError`. ARREGLADO (`687bb09`).
- **S5.** Si el primer turno no se pudo guardar, la sesión no recibe
  título nunca. ARREGLADO (`687bb09`).
- **S6.** `/delete` de una sesión que no existe, con una traza ilegible,
  dice que se borró. ARREGLADO (`3de7cd4`).
- **S7.** El título cancelado al salir se paga y no queda registrado.
  DECISIÓN 3. ARREGLADO (`687bb09`).
- **S8.** `Conversation.titled()` solo lo usan los tests. Con la decisión
  3 lo usa `close()`. ARREGLADO (`687bb09`).

## Modelos y configuración (M)

- **M1.** Un patrón absoluto en `instructions` del usuario
  (`"/home/yo/notas/*.md"`) tira `maha` al arrancar (`ValueError` en
  `relative_to`). ARREGLADO (`2155f8b`).
- **M2.** Un `AGENTS.md` grande se recorta dos veces, y el aviso dice mal
  cuánto (30 bytes en lugar de 34.464). ARREGLADO (`a366176`).
- **M3.** OpenAI: un `"delta": null` en un trozo tira la respuesta entera.
  ARREGLADO (`65630f2`).
- **M4.** A los modelos Claude de OpenCode Go y Zen les falta
  `cache_write_1h`. Hay que comprobar el precio en la documentación de
  OpenCode. DECISIÓN pendiente: la documentación de OpenCode (2026-11-11) no da precio de escritura en caché de 1 h para ningún Claude, así que no se puede añadir; hoy esas escrituras se cuentan al precio de 5 min (spec 9, decisión 9).
- **M5.** Deuda: `_int` en los dos adaptadores (ya hay `count` en
  `http.py`), `CacheTtl` y la versión de Anthropic escritos dos veces. ARREGLADO (`b75aa5e`).
- **M6.** `opencode-zen/jev-1.13`: entrada de pago y salida gratis, sin
  `context` ni `max_output`. Por comprobar en la documentación de Zen. COMPROBADO (documentación de Zen, 2026-11-11): entrada 0,042 $, salida gratis, sin caché, sin contexto ni salida máxima publicados; es un modelo «System One» que no habla los formatos de `maha`. NO ES FALLO.
- **M7.** El precio de `claude-haiku-5-5` en OpenCode (pendiente de
  ESTADO): las cuentas encajan con 0,50/2,50 $ por millón sin descuento de
  caché. Por comprobar en la documentación de OpenCode Go. COMPROBADO (documentación de Go, 2026-11-11): 0,10/0,50 $ hasta 100K y 0,50/2,50 $ por encima, como el catálogo; la diferencia es de lo que cobra OpenCode, no del catálogo. Con Go vale el coste del proveedor. Al repasar la documentación, el catálogo de Go y Zen estaba desfasado (nueve modelos, precios y descuentos): puesto al día (`7dd8e25`).

## Herramientas y seguridad (H)

- **H1.** `[a] always this session` no dice qué cubre: en una edición,
  todas las ediciones del directorio. ARREGLADO (`344c76d`).
- **H2.** `edit_file`: la búsqueda flexible de un `old_string` de varias
  líneas es O(líneas × líneas) y corre antes de preguntar; 800 KB bloquean
  `maha` 19 s sin atender a Ctrl+C. ARREGLADO (`a2997a2`).
- **H3.** `grep` lanza un Python por cada lote de 500 ficheros (0,26 s cada
  uno): 10.000 ficheros, 5 s; en WSL puede pasar su tiempo límite. ARREGLADO (`0fc152e`).
- **H4.** De la salida de un comando solo se guarda el principio: el
  resumen de fallos de un `pytest` largo nunca llega al modelo. ARREGLADO (`e37e115`).
- **H5.** `grep` con `a{99999999999}` o un anidamiento enorme sale como
  error interno (`OverflowError`, `RecursionError`). ARREGLADO (`0fc152e`).
- **H6.** El ámbito "always" de `run_command` no incluye el tiempo límite
  que la pregunta enseña. ARREGLADO (`344c76d`).
- **H7.** Faltan en la lista de lo que ejecuta código: `.hg/hgrc`,
  `Jenkinsfile`, `.travis.yml`, `azure-pipelines.yml`,
  `bitbucket-pipelines.yml`, `.buildkite/`, `.drone.yml`, `.woodpecker*`,
  `.nvimrc`, `.vimrc`, `.gvimrc` y `lefthook.yml`. ARREGLADO (`6c52678`).
- **H8.** `XDG_RUNTIME_DIR` llega a los comandos y abre el bus de sesión
  (llavero, agente SSH). ARREGLADO (`2b838b0`).
- **H9.** El proceso de búsqueda hereda el entorno completo de `maha`,
  clave incluida. ARREGLADO (`0fc152e`).
- **H10.** Una línea enorme (un JS minificado) llena la pregunta de
  aprobación de `write_file`. ARREGLADO (`309f248`).
- **H11.** Una ruta en un bucle de enlaces o con un nombre demasiado largo
  se pregunta y falla después. ARREGLADO (`caf2abb`).
- **H12.** El comentario de `ApprovalRequest.title` dice que se corta, y no
  se corta (A3). ARREGLADO (`344c76d`).
- **H13.** `_check_grep` devuelve una regex que nadie usa. ARREGLADO (`0fc152e`).

## Interfaz y evals (I)

- **I1.** `maha prompt` saca sin limpiar el texto de los `AGENTS.md` a la
  terminal: uno de un repo ajeno puede borrar la pantalla o escribir en el
  portapapeles (OSC 52). ARREGLADO (`37b42f9`).
- **I2.** Ctrl+C en `maha sessions`, `trace`, `stats`, `export`, `import`
  o `prompt`, o al arrancar la conversación, da un traceback. ARREGLADO (`323d096`).
- **I3.** `/init` en una subcarpeta apunta a la raíz git, fuera del
  directorio de trabajo. DECISIÓN 1. ARREGLADO (`bf33378`).
- **I4.** Un texto de varias líneas pegado se manda como un turno por
  línea. DECISIÓN 2. ARREGLADO (`a438f8c`).
- **I5.** `ask_user`: `"²"` pasa `isdigit()` y rompe la herramienta. ARREGLADO (`ccfdbfb`).
- **I6.** `ask_user`: con opciones `2` y `4`, teclear `2` elige `4`. ARREGLADO (`ccfdbfb`).
- **I7.** `/export` y `maha export` titulan el Markdown con la primera
  línea, no con el título de la sesión. ARREGLADO (`3237373`).
- **I8.** Ctrl+C durante un comando (`/delete` pidiendo confirmación,
  `/trace`) cierra `maha`. ARREGLADO (`579cf52`).
- **I9.** `maha -p "/init"` manda el texto literal; las evals sí lo
  expanden. ARREGLADO (`bf33378`).
- **I10.** `clean()` escapa el `\r` de un `\r\n`: cada línea de un texto
  CRLF se ve con `\x0d`. ARREGLADO (`86b83d7`).
- **I11.** La pregunta de aprobación pinta en color sin mirar si es una
  terminal. ARREGLADO (`ef6a7ff`).
- **I12.** Evals: la copia del fixture se lleva lo que git no sigue
  (`__pycache__`); la comprobación de la tarea 24 exige la palabra
  `español`. ARREGLADO (`275972b`).
- **I13.** La ayuda de `--allow` se lee como si los secretos de dentro se
  permitieran; `maha prompt -h` no explica sus opciones. ARREGLADO (`11ff101`).
- **I14.** `Evaluator.check()` solo lo usan los tests. ARREGLADO (`e0fc131`).
- **I15.** `maha import` lee el fichero entero sin tope. ARREGLADO (`36b2c24`).

## Producto (P)

Las propuestas de los revisores, evaluadas por tres agentes Opus
independientes, al máximo esfuerzo (2026-11-10). Entra lo que ven bueno
al menos dos de los tres; lo demás va a su hito o se descarta, con el
motivo de la mayoría.

**Ahora, en esta auditoría:**
- **P1.** Ctrl+C en el prompt: el primero limpia la línea y avisa; el
  segundo sale (2 de 3; el tercero lo dejaba para el hito 21). Cambia lo
  que fijó la spec 3, §1.10. HECHO (`579cf52`).
- **P2.** `-p`: el id de la sesión en stderr al terminar; `stream-json`,
  un evento inicial con el id, el modelo y las herramientas, cuando el id
  ya es suyo (2 de 3). HECHO (`2d1eb35`).
- **P3.** `run_command` con bash si lo hay, y si no `/bin/sh` (3 de 3):
  `/bin/sh` es dash en Debian y Ubuntu, y `source` o `[[` fallan. Bash, no
  `$SHELL` (zsh o fish cambian la sintaxis). El `cd` que dura entre
  comandos, al hito 15. HECHO (`f760beb`).
- **P4.** Enseñar el diff de una edición que pasa sin preguntar por un
  "always" (3 de 3). HECHO (`344c76d`).
- **P5.** Una lista de variables de entorno para los comandos, solo en la
  configuración del usuario (proxy, `JAVA_HOME`…), sin las que tienen
  forma de credencial (2 de 3; el tercero, al hito 15). HECHO (`87cac93`).
- **P6.** `maha sessions --all` y `/sessions all`: hoy solo se ven 20 (3
  de 3). HECHO (`9050201`).
- **P7.** Buscar `.maha/config.toml` de la carpeta actual a la raíz git
  (3 de 3): desde una subcarpeta, la configuración del proyecto, límites
  incluidos, se ignoraba sin avisar. HECHO (`a245c18`).
- **P8.** Si Kimi o GLM exigen que se les devuelva su `reasoning_content`
  en un bucle con herramientas, es un fallo del adaptador de OpenAI (los
  tres piden comprobarlo en la documentación oficial antes). COMPROBADO: la documentación de Kimi (2026-11-10) dice, para `kimi-k2.7-code`, "you must therefore (not optionally) keep the `reasoning_content` of historical assistant messages", y OpenCode Go lo manda. ARREGLADO (`69f16ec`).

**A su hito:** el análisis de comandos peligrosos, las reglas por patrón,
el `cd` que dura, la lista de variables como parte del sandbox y qué ve el
modelo tras una negativa en `-p`, al hito 15; `grep` con contexto o solo
ficheros, la política de versiones del formato de sesión y subir el tope
de pasos, al hito 11 (se miden con la batería larga y la compactación);
el indicador de una herramienta larga, distinguir a la vista el texto del
modelo, `maha "texto"`, el selector de `-r`, ver el razonamiento y
explicar un `effort` no admitido, al hito 21; la limpieza de sesiones
antiguas, al hito 23.

**Descartadas:** ripgrep (el recorrido, con su perímetro y sus secretos,
lo hace `maha`; otro dialecto de regex según la máquina); editar ficheros
que no son UTF-8 (adivinar la codificación puede corromperlos); un tope
de gasto por sesión (el coste de la sesión se ve en cada turno, y en `-p`
el tope del turno ya acota la ejecución); pedir `thinking` a Claude (los
modelos 5.x ya razonan sin pedirlo; solo los 4.x del catálogo, mejora
menor con documentación y evals); `retry-after-ms` (no consta que un
proveedor lo mande); Windows nativo (DESIGN §7 fija Linux y WSL2).

## Revisión independiente de los arreglos (2026-11-11)

Tres agentes nuevos, uno por área (herramientas y seguridad; interfaz;
núcleo, sesiones y modelos), que solo vieron el código, AGENTS.md, DESIGN
y esta spec. Cada hallazgo, comprobado y con su test primero:

- **R1.** Ctrl+C mientras `/new` o `/resume` esperan el título dejaba
  `maha` en la sesión cerrada (lo vieron dos revisores). ARREGLADO
  (`500a6b8`): quien cambia de sesión lo hace antes de cerrar la vieja.
- **R2.** Ctrl+C mientras la salida espera el título llegaba sin nuestro
  manejador: `/exit` salía con 130 y no se avisaba de lo no guardado.
  ARREGLADO (`9fc2a77`).
- **R3.** Las `instructions` de un `.maha/config.toml` encontrado más
  arriba (P7) se buscaban desde la carpeta actual. ARREGLADO (`8bfef94`).
- **R4.** El razonamiento de un modelo iba a otro tras `/model` o un
  respaldo (P8). ARREGLADO (`72f7ace`): cada modelo recibe solo el suyo;
  DeepSeek, GLM, Kimi y MiniMax lo piden (documentación, 2026-11-11).
- **R5.** Un motivo de parada desconocido rechazaba siempre la última
  llamada, aunque llegara entera (B1). ARREGLADO (`1b39619`).
- **R6.** `-c` saltaba sin avisar una sesión ilegible de carpeta
  desconocida (S2). ARREGLADO (`2ce59be`).
- **R7.** Sin traza, `stream-json` no daba `init` (P2). ARREGLADO
  (`6f18655`).
- **R8.** Un `\r\n` partido entre dos trozos del stream se veía con
  `\x0d` (I10), y un Ctrl+D justo tras una línea no cerraba `maha` (I4).
  ARREGLADO (`68b9f37`).
- **R9.** El aviso de `/init` en una subcarpeta sacaba la ruta sin
  limpiar. ARREGLADO (`64473cf`). Y en las evals, con `TMPDIR` dentro de
  un repo, la tarea 24 recibía el texto de subcarpeta. ARREGLADO
  (`f631689`).
- **R10.** Con una entrada vacía en `PATH`, `which("bash")` podía dar el
  `./bash` del proyecto (P3); y los bytes dejados fuera de una salida
  cortada se contaban mal sin UTF-8 (H4). ARREGLADO (`7013aae`).
- **R11.** Un nombre largo bajo una carpeta nueva se preguntaba y fallaba
  después (H11); el hijo de `grep` sin locale (H9). ARREGLADO
  (`3fa6f7b`).
- **R12.** lefthook en TOML o JSON (H7). ARREGLADO (`7339fe2`).
- **R13.** `command_env` solo miraba el final del nombre (P5). ARREGLADO
  (`54a15be`); es una guarda, no una garantía (PUESTA_EN_MARCHA §3.1).
- **R14.** Un test del tiempo límite del turno fallaba con la máquina
  cargada. ARREGLADO (`a9dd73a`).
- **R15.** Con la decisión 2, las líneas tecleadas por adelantado durante
  una respuesta llegan juntas a la terminal y se unen en un turno
  (`hola⏎/exit⏎`). DECISIÓN pendiente del mantenedor.
- **R16.** Una señal de cierre (SIGTERM) mientras la salida espera el
  título termina con el código de la salida normal, no con 128 + la
  señal. Lo demás se guarda. ARREGLADO (este commit).

## Aprendido al implementar

*Se añade al implementar.*
