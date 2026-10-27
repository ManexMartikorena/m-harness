# Mapa del repositorio

Dónde está cada cosa. Se actualiza en el mismo PR que crea, mueve o borra
ficheros.

Última actualización: 2026-10-26 (hito 6 cerrado, `v0.6.0`).

## Raíz

| Fichero | Qué es |
|---|---|
| `README.md` | Presentación pública del proyecto y hoja de ruta |
| `LICENSE` | Licencia MIT |
| `AGENTS.md` | Reglas para cualquier agente de código: la única fuente de reglas |
| `CLAUDE.md` | Importa `AGENTS.md` para Claude Code |
| `.gitignore` | Lo que nunca entra en git |
| `.env.example` | Variables de entorno de desarrollo, vacías: se copia a `.env` (`PUESTA_EN_MARCHA` §2) |
| `.gitattributes` | Finales de línea LF en todas las máquinas |
| `pyproject.toml` | Metadatos, dependencias (pydantic y httpx; respx y las herramientas en `dev`) y configuración de ruff, mypy, pytest e import-linter |
| `uv.lock` | Versiones exactas de las dependencias (lo genera uv) |
| `.python-version` | Python de desarrollo: 3.14 |
| `.pre-commit-config.yaml` | Hooks antes de cada commit: ruff, gitleaks, YAML, TOML y ficheros grandes |
| `.github/pull_request_template.md` | Plantilla de PR: qué hace cada fichero y por qué |
| `.github/workflows/ci.yml` | CI: checks con Python 3.14 y 3.15, y gitleaks (commits del PR; historial entero si se lanza a mano). Los pushes a `main` no se cancelan |
| `.github/workflows/release.yml` | Al hacer push de un tag `v*`: comprueba la versión y crea la GitHub Release |

## `docs/`

| Fichero | Qué es |
|---|---|
| `ANALISIS.md` | Fase 1: problema, alcance, requisitos, riesgos y criterios de éxito |
| `DESIGN.md` | Fase 2: arquitectura, contrato de datos, stack y plan de hitos |
| `ESTADO.md` | Tablero: fase, hecho, siguiente paso, pendientes y versiones |
| `PUESTA_EN_MARCHA.md` | Lo que no viaja por git: entorno, `.env` y ajustes de GitHub |
| `MAPA.md` | Este fichero |
| `guia/README.md` | Índice de la guía de conceptos (una nota por hito) |
| `guia/01-arquitectura-hexagonal.md` | Nota del hito 1: capas, raíz de composición y la base que lo vigila |
| `guia/02-llamada-a-un-llm.md` | Nota del hito 2: la llamada HTTP, por qué el modelo no recuerda, el adaptador y lo que puede salir mal |
| `guia/06-historial.md` | Nota del hito 6: el historial es la memoria del modelo, el JSONL que solo crece (y su bloqueo), un historial que se puede mandar, la respuesta cortada marcada, todas las sesiones desde cualquier directorio, las aprobaciones que no vuelven y el disco detrás de un puerto |
| `guia/05-permisos.md` | Nota del hito 5 (con `v0.5.1` y `v0.5.2`): leer frente a efecto, la pregunta (lo tecleado antes se descarta, nada se corta) y sus ámbitos, lo que nunca es para la sesión, escribir sin romper nada, ejecutar comandos (y lo que no protege), lo ejecutado consta y las reglas en el dominio |
| `guia/04-tool-calling.md` | Nota del hito 4: herramientas con JSON Schema, el viaje de una llamada, el bucle y su límite, errores devueltos al modelo, perímetro y secretos |
| `guia/03-streaming.md` | Nota del hito 3: SSE, eventos propios, fallos a mitad, cancelar con Ctrl+C, tokens de razonamiento y el spinner |
| `specs/PLANTILLA.md` | Formato de las specs de hito y de mejora |
| `specs/hito-1-esqueleto.md` | Spec del hito 1 (IMPLEMENTADA): paquete, capas, calidad, CI y release |
| `specs/hito-2-primera-conversacion.md` | Spec del hito 2 (IMPLEMENTADA): dominio, puerto `ModelClient`, adaptador de OpenAI, configuración y conversación en la terminal |
| `specs/hito-5-permisos.md` | Spec del hito 5 (IMPLEMENTADA): contrato de aprobación, ámbitos de sesión, `write_file`, `edit_file`, `run_command` con `CommandRunner`, lo ejecutado consta y `refusal` |
| `specs/hito-4-bucle-agentico.md` | Spec del hito 4 (IMPLEMENTADA): bloques de llamada y resultado, `ToolCallDelta`, puerto `Tool`, cuatro herramientas de solo lectura, el bucle `Agent` y la terminal con llamadas |
| `specs/mejora-2026-10-23-deuda-hito-5.md` | Mejora (IMPLEMENTADA): cero deuda antes de cerrar el hito 5 — fallos de la auditoría, arquitectura, escritura de ficheros, entorno de los comandos y `.gitignore` |
| `specs/mejora-2026-10-26-deuda-pre-hito-6.md` | Mejora (IMPLEMENTADA, `v0.5.2`): cero deuda antes del hito 6 — los fallos de dos auditorías del 2026-10-26: secretos tras un enlace, entrada adelantada, pregunta que corta, señales de cierre, listas de secretos y de código, y corrección |
| `specs/hito-3-streaming.md` | Spec del hito 3 (IMPLEMENTADA): eventos del modelo, `stream()` en el puerto junto a `complete()`, `collect()`, SSE a mano, spinner de espera y Ctrl+C por respuesta |
| `specs/hito-6-sesiones.md` | Spec del hito 6 (IMPLEMENTADA): sesiones en JSONL, puerto `SessionStore`, guardado por turno, respuesta cortada marcada y los comandos `/sessions` (de todos los directorios), `/resume`, `/delete`, `/model` y `/help` |
| `specs/hito-7-trazas-coste.md` | Spec del hito 7 (PROPUESTA): `Usage.reasoning_tokens`, catálogo de modelos en TOML (paquete y usuario), coste por llamada, turno y sesión, `TurnStarted`, trazas JSONL sin credenciales, `/trace`, avisos del catálogo y `maha.log` |

## Código: `src/mharness/`

Arquitectura hexagonal (DESIGN §3). Las reglas entre capas las comprueba
import-linter (`pyproject.toml`).

| Fichero | Capa | Qué es |
|---|---|---|
| `__init__.py` | paquete | `DISTRIBUTION` y `__version__`: el nombre y la versión de `maha`, en un solo sitio |
| `__main__.py` | entrada | `python -m mharness`: igual que `maha` |
| `bootstrap.py` | raíz de composición | `main()` del comando `maha`: lee la configuración, resuelve el directorio de arranque, crea el adaptador, las siete herramientas sobre ese directorio (`run_command` con `LocalCommandRunner` y el entorno de `command_env()`, sin la clave del proveedor), un solo `StdinLines` para la conversación y las preguntas, el gate (`TerminalApproval` en una terminal, `DenyAll` sin ella) y `Sessions` sobre `JsonlSessionStore` en `data_dir()/sessions`, con la fábrica del `Agent`; el único que conoce todas las piezas |
| `config.py` | configuración (hermana de `adapters`) | `load()`: proveedores predefinidos, del usuario y del proyecto (este, solo `provider` y `model`); la clave, del entorno. `data_dir()`: `$XDG_DATA_HOME/maha`, por defecto `~/.local/share/maha` |
| `domain/messages.py` | domain | `TextBlock`, `ToolCallBlock`, `ToolResultBlock` y `Message`: mensajes hechos de bloques, validados por `type`; `interrupted` marca una respuesta cortada con Ctrl+C |
| `domain/model.py` | domain | `ModelRequest` (con `tools`), `ToolSpec`, `ModelResponse`, `Usage` (se suma con `+`; `input_tokens` incluye la caché y `output_tokens` el razonamiento, `reasoning_tokens`) y `StopReason` |
| `domain/catalog.py` | domain | `Prices` (USD por millón, en `Decimal`, con la fecha `checked` y sus tramos, `Tier`, por tamaño del prompt), `ModelInfo` (precios, ventana de contexto, `trains_on_data`) y `cost(usage, prices)` (spec hito 7, §1.4 y §1.5) |
| `domain/session.py` | domain | La sesión guardada (spec hito 6, §1.2): `SessionHeader`, las líneas del fichero (`MessageEntry`, `UsageEntry`, `ModelEntry`, unidas por `type` en `SessionEntry`), `Session` y `SessionSummary`; `session_id()` e `is_session_id()` (fecha UTC y 4 hex; nada más llega al disco); `check_history()` (cada llamada con su resultado), `replay()` y `summarize()`; errores `SessionNotFound`, `SessionInUse` y `SessionCorrupt` |
| `domain/events.py` | domain | `TextDelta`, `ToolCallDelta`, `MessageEnd` y `ModelEvent`: lo que llega mientras el modelo responde |
| `domain/commands.py` | domain | `CommandResult` (`exit_code`, `output`, `truncated`, `timed_out`) y `OUTPUT_MAX_CHARS` (30 000) |
| `domain/environment.py` | domain | `command_env()`: las variables que recibe un comando, por lista de permitidas (spec `mejora-2026-10-23-deuda-hito-5`, E1) |
| `domain/tools.py` | domain | `Permission` (`read` o `effect`) y `ToolError`, el fallo esperado que se explica al modelo |
| `domain/approval.py` | domain | `Decision` (`once`, `session` o `deny`) y `ApprovalRequest` (`tool`, `title`, `detail`, `scope`, `warning`): la pregunta antes de ejecutar y la respuesta |
| `domain/agent_events.py` | domain | `ToolCallProposed`, `ApprovalRequested`, `ToolFinished` (con `decision`), `ModelCallFinished`, `TurnFinished` (`end_turn`, `max_steps` o `denied`) y `AgentEvent`: lo que el bucle cuenta a la terminal |
| `domain/gitignore.py` | domain | `GitIgnore`: las reglas de `.gitignore` (gitignore(5)) traducidas a mano a expresiones regulares, sin tocar el disco (spec `mejora-2026-10-23-deuda-hito-5`, E6); clases POSIX, escapes y patrones que no casan nada como git (spec `mejora-2026-10-26-deuda-pre-hito-6`, B7) |
| `domain/paths.py` | domain | `is_secret()` y `SKIPPED_DIRS`: qué ficheros no ve el modelo y qué carpetas no se recorren, sin tocar el disco. Las reglas de lo que pregunta una ruta ya resuelta, y también la pedida (`asked`: un `.env` que es un enlace): `is_inside()`, `is_secret_at()`, `read_warning()` y `change_warning()` (también `.git` y lo que ejecuta código: CI, hooks, editores, `.claude`, `.maha`, `.pre-commit-config.yaml`, `.envrc`), con los textos de los avisos |
| `domain/errors.py` | domain | `ModelError` y sus cinco tipos (autenticación, límite, petición, no disponible, respuesta) |
| `ports/commands.py` | ports | `CommandRunner`: `run(command, *, cwd, time_limit, env) -> CommandResult`; mata el comando al pasar el tiempo o al cancelar |
| `ports/tools.py` | ports | `Tool`: nombre, descripción, modelo Pydantic de parámetros, permiso, `approval()` asíncrono (qué preguntar antes, o `None`), `run()` y `summary()` |
| `ports/approval.py` | ports | `ApprovalGate`: `decide(request) -> Decision`; quien aprueba una llamada |
| `ports/model.py` | ports | `ModelClient`: `complete(request) -> response` y `stream(request) -> eventos` |
| `ports/catalog.py` | ports | `ModelCatalog`: `get(provider, model) -> ModelInfo \| None`, síncrono (se lee al arrancar) |
| `ports/sessions.py` | ports | `SessionStore` (`create`, `open`, `summaries`, `delete`) y `SessionLog` (`append`, `close`): una sesión abierta queda bloqueada hasta `close()` |
| `application/collect.py` | application | `Accumulator`: la respuesta entera a partir de los eventos, con las llamadas a herramientas juntadas por `index`; `text`, lo que llegó hasta ahora |
| `application/tools.py` | application | `ToolRegistry`: herramientas por nombre y sus `ToolSpec`; acepta las de efecto (el bucle pregunta antes) |
| `application/approvals.py` | application | `SessionApprovals`: los `scope` aprobados para toda la sesión, en memoria (`covers()` y `record()`); un `scope` `None` nunca se guarda |
| `application/agent.py` | application | `Agent`: el bucle agéntico (modelo → herramientas → resultados, hasta 25 pasos), con los errores devueltos al modelo. Pregunta al `gate` antes de ejecutar y solo ejecuta con una respuesta de `DECISIONS`; una negativa termina el turno; lo ejecutado consta aunque falle el modelo o se cancele, y el texto ya escrito de una respuesta cortada con Ctrl+C queda como mensaje `interrupted`. Empieza con un historial (`history=`) y `model` se puede cambiar entre turnos |
| `application/sessions.py` | application | `Sessions` (empezar, retomar de cualquier directorio, listar, `here()` y borrar; nunca la actual) y `Conversation` (envuelve al `Agent`; mensajes, tokens y cambios de modelo van a una cola ordenada que se escribe al terminar cada turno, en `/model` y al cerrar; crea la sesión con el primer turno; un fallo al guardar queda en `unsaved` y se reintenta entero); `Resumed`: lo que hay que contar al retomar (otro directorio, modelo de reserva, respuesta cortada, lo que la sesión dejada no pudo guardar). `/resume` sin id salta la actual y las abiertas en otro `maha`. El `Agent` lo crea una fábrica inyectada |
| `adapters/models/sse.py` | adapters | `parse_sse()`: el dato de cada evento SSE, con las líneas partidas solo en CRLF, LF o CR |
| `adapters/models/openai_chat.py` | adapters | `OpenAIChatClient`: la conversación en formato OpenAI Chat Completions, con httpx. `complete()` (respuesta entera) y `stream()` (eventos SSE); envía herramientas, llamadas y resultados; traduce respuesta, trozos (también `tool_calls`) y errores. `refusal` (con stream y sin él) llega como texto. Un mensaje `interrupted` lleva `[interrupted by the user]` al final |
| `adapters/tools/__init__.py` | adapters | Exporta `Workspace`, las cuatro de lectura, `WriteFile`, `EditFile` y `RunCommand` |
| `adapters/tools/search_worker.py` | adapters | El proceso hijo donde `grep` ejecuta la regex del modelo (`search_files()`), con tiempo límite y matado con Ctrl+C: una regex catastrófica no congela `maha` |
| `adapters/tools/files.py` | adapters | `Workspace` (perímetro del directorio de trabajo) y las herramientas de lectura `read_file`, `list_dir`, `glob` y `grep`, con topes y sin hilos: fuera del directorio o con un secreto, su `approval()` pregunta (`scope=None`) y `run()` solo lee la ruta resuelta que se preguntó. `run()` solo ejecuta la llamada exacta que se preguntó (`_Asked`, también con los bytes que mostró la pregunta). `WriteFile` (`write_file`: vista previa o diff) y `EditFile` (`edit_file`: texto exacto, diff, adaptación a CRLF), herramientas `effect`; con aviso (las reglas de `domain/paths.py`), nunca para la sesión, y los errores que dependen del contenido esperan a la aprobación. `CHANGE_MAX_FILE_BYTES` (2 MiB) para cambiar un fichero; `_reading`: un `OSError` al leer da `cannot read`; `_endings`: el aviso de cambio de saltos de línea en el diff. Escritura atómica compartida (`_as_shown` y `_write`): temporal `.maha-<hex>.tmp` en la misma carpeta con el propietario, el modo y los atributos extendidos del original, `fsync`, última comprobación, `os.replace` y `fsync` de la carpeta y de las carpetas nuevas; con enlaces duros o atributos que no se copian, escribe en el sitio y, si falla, devuelve los bytes viejos. Una escritura que falla borra las carpetas que creó. El diff recorta lo común y no se calcula por encima de `DIFF_MAX_WORK` líneas. `grep` recorre aquí y busca en `search_worker.py` por tandas de `GREP_BATCH_FILES` (`_search_apart`, `GREP_TIME_LIMIT` para toda la búsqueda). `glob` y `grep` saltan al recorrer lo que ignoran `.gitignore` y `.git/info/exclude` (`_add_rules`). `edit_file` cuenta las apariciones solapadas y acepta cualquier salto de línea en `old_string`. De la mejora del 2026-10-26: los parámetros prohíben campos de más (`extra="forbid"`); un fichero de solo lectura da error; si la carpeta no deja crear el temporal, escribe en el sitio; `read_file` para tras `READ_MAX_SCAN_CHARS` (64 MiB) recorridos y `list_dir` lee como mucho `LIST_MAX_SCAN` entradas. |
| `adapters/tools/shell.py` | adapters | `RunCommand` (`run_command`, `effect`): pregunta con el comando, el directorio y "with your permissions", `scope` del comando exacto; usa el puerto `CommandRunner`, nunca el adaptador local. |
| `adapters/commands/local.py` | adapters | `LocalCommandRunner`: `create_subprocess_shell` en un grupo de procesos propio, stdin cerrado, stderr con stdout, salida leída mientras corre y cortada a 30 000 caracteres, y `killpg(SIGKILL)` del grupo entero al pasar el tiempo, al cancelar y al terminar; como *subreaper*, mata también lo que el comando sacó de su grupo (`_kill_escaped`). Sin hilos |
| `adapters/storage/__init__.py` | adapters | Exporta `JsonlSessionStore` |
| `adapters/catalog/models.toml` | adapters | Los datos del catálogo: precios (USD por millón, de la documentación de cada proveedor), tramos y ventana de contexto (de models.dev) de los 30 modelos de OpenCode Go y los 83 de Zen, con la fecha en `[providers.<nombre>].checked` (2026-10-27) y los que entrenan con los datos |
| `adapters/catalog/toml_catalog.py` | adapters | `TomlCatalog.load(user_file)`: el catálogo del paquete y, encima, el `models.toml` del usuario, que manda modelo a modelo; `get()` y `models()`. `parse()` valida (campos de más, clave `proveedor/modelo`, entrada y salida juntas, fecha, tramos) y da `CatalogError` con el qué y el dónde |
| `adapters/storage/sessions.py` | adapters | `JsonlSessionStore` y `JsonlLog`: una sesión por fichero `<id>.jsonl` (cabecera con `version` y una línea por entrada), carpeta `0700` y ficheros `0600`; cada `append` es una escritura con `fsync`, y si falla se recorta al tamaño de antes; el texto que no es UTF-8 válido va escapado; `flock` mientras está abierta (`SessionInUse`), y comprobación de que el nombre sigue siendo ese fichero; una última línea cortada se ignora y se recorta; una rota en medio, una cabecera inválida (también anidada sin fin o con otro id) o una versión desconocida dan `SessionCorrupt`; la lista salta lo que no puede leer; el borrado bloquea antes de borrar |
| `adapters/cli/app.py` | adapters | Línea de comandos con argparse: `parse()` (`--version`, la ayuda) y `fail()` |
| `adapters/cli/conversation.py` | adapters | `converse()`: empieza una sesión (`Sessions.start()`), lee, separa los comandos (`parse_command`) del texto, envía el texto a la `Conversation` y muestra la respuesta según llega, cada llamada a herramienta (`→`, `✓`/`✗`), la negativa (`[denied: …]`) y la línea de tokens con las llamadas; avisa si la sesión no se guardó y la cierra al salir. `/exit`, Ctrl+D y Ctrl+C (a mitad de respuesta o de la pregunta, solo la corta); un error no previsto se enseña y vuelve al prompt; SIGHUP y SIGTERM cancelan y terminan `maha` con `128 + señal`. Todo texto no confiable pasa por `clean()` |
| `adapters/cli/commands.py` | adapters | `parse_command()` (`/` y minúsculas como primera palabra; `/etc/hosts …` es texto), `COMMANDS` y `Commands`: `/help`, `/sessions` (las 20 últimas de todos los directorios, `*` en las de este, `~` para el `HOME`), `/resume [ID]` (con los avisos de otro directorio, otro proveedor y respuesta cortada), `/delete ID` (nunca la actual; confirma `[y/N]` tras descartar lo tecleado) y `/model [ID]`; un comando desconocido no va al modelo; un fallo no previsto se enseña y vuelve al prompt; todo lo leído del disco pasa por `clean()` |
| `adapters/cli/approval.py` | adapters | `TerminalApproval`: descarta lo tecleado antes (`discard`), la pregunta (`┌`, `│`, `└ Allow?`), `y`/`a`/`n`, Ctrl+D deniega, aviso en amarillo; nada se corta (las líneas largas siguen con `↪`) y un detalle de más de 60 líneas ofrece `v`; saneado con `clean()`. `DenyAll`: sin terminal, deniega sin preguntar |
| `adapters/cli/input.py` | adapters | `StdinLines` (lectura de stdin sin hilos; `discard()` vacía su búfer y la cola de la terminal) y `ReadLine`: un solo lector para la conversación y las preguntas |
| `adapters/cli/text.py` | adapters | `clean()`: escapa los caracteres de control y bidi del texto no confiable antes de pintarlo (spec `mejora-2026-10-23-deuda-hito-5`, A2) |
| `adapters/cli/spinner.py` | adapters | `Spinner` y `frame()`: spinner braille con "maha" en colores ANSI mientras llega el primer token; solo en una terminal real, y `NO_COLOR` |

## Tests: `tests/`

| Fichero | Qué comprueba |
|---|---|
| `test_entry_point.py` | El script `maha` entra por `bootstrap.main`; `python -m mharness --version` |
| `conftest.py` | Para todos los tests: cada uno con su propio `XDG_DATA_HOME`, para que nada se escriba en el `HOME` real |
| `test_bootstrap.py` | `maha` de punta a punta con respx (streams SSE) y un pipe o una pseudoterminal como stdin: dos turnos, un segundo `maha` que retoma al primero, las sesiones en el `XDG_DATA_HOME` del test, un stream cortado, las siete herramientas, una llamada a `read_file` sobre un fichero real, sin terminal una escritura se deniega sin preguntar, en una terminal `run_command` pregunta (tras descartar lo tecleado antes) y su `env` no ve la clave; errores de configuración y `--version` |
| `adapters/test_cli.py` | `--version`, la ayuda, sin argumentos devuelve las opciones, el error de uso y `fail()` |
| `adapters/test_conversation.py` | Respuesta en directo y tokens, llamadas a herramientas (marcas, argumentos cortados, plural, límite de pasos, fallo interno, Ctrl+C durante una herramienta, que guarda el turno con la llamada cancelada), `/exit`, Ctrl+D, Ctrl+C en el prompt y a mitad de respuesta, errores a mitad, spinner, SIGHUP y SIGTERM (también durante un comando real, que no sobrevive) y `StdinLines` (también `discard()`, con una tubería y una pseudoterminal) |
| `adapters/test_commands.py` | Qué es un comando y qué va al modelo; `/help`, comando desconocido, `/sessions` (vacía, de todos los directorios, orden, marca), `/resume` (historial, otro directorio, respuesta cortada, errores), `/delete` (`n`, `y`, sin id, la actual, lo tecleado se descarta), `/model`, títulos escapados y aviso de sesión no guardada |
| `adapters/test_approval.py` | `TerminalApproval`: lo tecleado antes se descarta, la pregunta, cada respuesta, repetir, Ctrl+D, sin `scope` no hay `a`, aviso con y sin color, nada se corta y `v` enseña el resto, caracteres de control escapados; `DenyAll` |
| `adapters/test_spinner.py` | Fotogramas con y sin color, `NO_COLOR`, solo en terminal, borrado de la línea |
| `adapters/test_sse.py` | Analizador SSE: eventos, comentarios, saltos de línea, trozos partidos, U+2028 y el tope de 1 MiB |
| `adapters/test_local_runner.py` | `LocalCommandRunner` con comandos reales e inocuos: salida y código, stderr mezclado, directorio, stdin cerrado, corte sin bloquear, tiempo límite con salida parcial, Ctrl+C y fin normal matan el grupo, un hijo en segundo plano no hace esperar al límite, un proceso que sale del grupo (`setsid`) muere también con Ctrl+C y uno que no se puede matar no corta la limpieza, entorno exacto |
| `adapters/test_shell_tool.py` | `run_command` con `FakeRunner`: descripción, límites de `timeout`, la pregunta y su `scope`, el texto del resultado (código, corte, tiempo) y el resumen |
| `adapters/test_toml_catalog.py` | `TomlCatalog`: el catálogo del paquete (todos los modelos, fechas, un modelo tal cual, tramos, precio de punta, los que entrenan) y el del usuario (manda y añade, sin precios, ids con `/`, ilegible, cada error con su qué y dónde) |
| `adapters/test_session_store.py` | `JsonlSessionStore` en `tmp_path`: lo añadido vuelve, formato de las líneas, permisos con un umask abierto, ids de otra forma, `fsync` que falla, última línea cortada, línea rota en medio, versión, cabeceras inválidas, historial roto, bloqueo entre dos almacenes, borrada al abrir, lista (orden, título, lo ilegible) y borrado |
| `adapters/test_file_tools.py` | Las seis herramientas de ficheros en `tmp_path`. Lectura: resultados, topes, perímetro (`..`, rutas absolutas, enlaces), secretos, binarios y errores; dentro no pregunta; fuera o con un secreto pregunta, con los avisos, y los fallos baratos van antes; un enlace cambiado tras la pregunta no se lee. `write_file`: vista previa, diff, carpetas, `scope`, errores antes de preguntar, lo mostrado es lo escrito, escritura atómica (fallo sin temporal, modo, umask, `fsync` del fichero y de la carpeta). `edit_file`: diff, 0 o varias apariciones, `replace_all`, CRLF (se conserva y se adapta), UTF-8, errores antes de preguntar, lo mostrado es lo editado. De la revisión: con aviso, la pregunta va antes de los errores de contenido (detail de reserva); tamaño máximo; `cannot read` (y `grep` salta los ilegibles); `run()` rechaza otros parámetros que los preguntados; `.git` nunca para la sesión; aviso de cambio de saltos de línea. De la mejora y la auditoría final: escritura en el sitio, enlaces, atributos, carpetas nuevas, diff acotado, apariciones solapadas, saltos de línea mezclados, `.gitignore`, ReDoS con tiempo límite y Ctrl+C, y `grep` que para en cuanto tiene bastantes resultados |
| `adapters/test_openai_chat.py` | `complete()`: JSON y cabeceras enviados, herramientas e historial con llamadas y resultados, traducción de la respuesta (con `reasoning_tokens`) y de cada error, y que la clave nunca sale en un error (con respx) |
| `adapters/test_openai_chat_stream.py` | `stream()`: petición con `stream` y herramientas, traducción de los trozos medidos (también `tool_calls` y `reasoning_tokens`), errores antes y a mitad del stream, y cierre de la conexión al cancelar (con respx) |
| `fixtures/openai_chat/` | Respuestas de ejemplo de Chat Completions (JSON) y streams SSE (`.sse`), también con llamadas a herramientas, con la forma medida en OpenCode Go, con datos inventados |
| `unit/test_messages.py` | `Message.text` une los bloques de texto; bloques de llamada y resultado; validación por `type`; mensajes inmutables |
| `unit/test_session.py` | Ids de sesión (y lo que no es un id), líneas validadas por `type`, cabecera, errores, `check_history()` (válidos y rotos), `replay()` y `summarize()` |
| `unit/test_fake_sessions.py` | `MemorySessionStore` cumple el puerto, devuelve lo añadido, bloquea la sesión abierta y no encuentra ids desconocidos |
| `unit/test_catalog.py` | `cost()`: entrada, salida, caché leída y escrita (a su precio o al de entrada), razonamiento dentro de la salida, `Decimal` exacto, nunca negativo; tramos (umbral, el mayor que se pasa, caché del tramo, orden); `Prices` sin precios negativos; `ModelInfo` |
| `unit/test_fake_catalog.py` | `MemoryCatalog` cumple el puerto y distingue el proveedor |
| `unit/test_model.py` | `Usage` a 0 por defecto y su suma (también `reasoning_tokens`); petición sin `system` y sin herramientas; `ToolSpec`; `StopReason` válido |
| `unit/test_events.py` | Eventos inmutables (también `ToolCallDelta`), `type` por defecto y `StopReason` válido |
| `unit/test_collect.py` | `Accumulator` (por el `collect()` del fake) junta el texto y las llamadas (argumentos partidos, varios `index`), toma el final de `MessageEnd` y falla sin él |
| `unit/test_paths.py` | `is_secret()`: qué rutas son secretas y cuáles no (sin distinguir mayúsculas); `read_warning()` y `change_warning()`, también por la ruta pedida, sin disco |
| `unit/test_gitignore.py` | `GitIgnore`: los casos de gitignore(5), la última regla gana, `!`, ficheros más hondos, CRLF y una tabla de casos raros con la respuesta de `git check-ignore` |
| `unit/test_environment.py` | `command_env()`: solo pasan las variables permitidas, nunca una credencial con prefijo permitido, y `drop` |
| `unit/test_fake_runner.py` | `FakeRunner` cumple el puerto, sigue el guion, guarda lo que se ejecutó y falla al agotarse |
| `unit/test_errors.py` | Todos los errores del modelo heredan de `ModelError` |
| `unit/test_fake_model.py` | El fake cumple el puerto, sigue el guion (también en stream, con `Gate` y `HANG`) y falla al agotarse |
| `unit/test_config.py` | Combinación de niveles, `[providers]` prohibido en el proyecto, errores con mensaje y la clave |
| `unit/test_agent.py` | El bucle: sin llamadas, una, dos en orden, límite de pasos, historial, uso sumado, errores devueltos al modelo; aprobación (`once`, `session` por `scope`, sin `scope`, `deny` termina el turno, `once` y luego `deny`, decisión no válida, efecto sin petición, `ToolError` y fallo en `approval()`); fallo en `summary()`, resultado que no es texto y JSON demasiado anidado; lo ejecutado consta ante fallo del modelo, Ctrl+C durante una llamada, la pregunta o el stream, y el bucle cerrado (`GeneratorExit`) |
| `unit/test_sessions.py` | `Sessions` y `Conversation` con `MemorySessionStore`: sin turnos no hay sesión, el primer turno la crea, cada turno sus mensajes y tokens, Ctrl+C, guardado que falla y se reintenta, `/model`, retomar (historial, modelo, otro proveedor, otro directorio, respuesta cortada, la última de aquí, la actual, la de otro `maha`, aprobaciones que no vuelven), lista y borrado |
| `unit/test_approvals.py` | `SessionApprovals`: `session` guarda el `scope`, cada `scope` cubre solo el suyo, `once` y `deny` no guardan nada, sin `scope` nunca se guarda |
| `unit/test_fake_approval.py` | `FakeApproval` cumple el puerto, sigue el guion y falla al agotarse; `ApprovalRequest` sin aviso por defecto e inmutable |
| `unit/test_tools_registry.py` | `ToolSpec` desde Pydantic, búsqueda, nombre repetido rechazado y herramienta con efecto aceptada |
| `unit/test_fake_tool.py` | `FakeTool` cumple el puerto y sigue su guion, también en `approval()` |
| `fakes/model.py` | `FakeModelClient` guionizado (`complete()` y `stream()`), `collect()`, `reply()`, `tool_calls()`, `END`, `Gate` y `HANG` (no es un test: lo usan los tests) |
| `fakes/tools.py` | `FakeTool`: una herramienta guionizada, con `permission`, `requests` (lo que devuelve `approval()`: petición, `None` o error) y `gate` para probar la cancelación |
| `fakes/terminal.py` | `ScriptedInput`: lo que teclea una persona, línea a línea, y luego Ctrl+D |
| `fakes/commands.py` | `FakeRunner`: un `CommandRunner` que responde con un guion de `CommandResult` y guarda cada comando en `ran` |
| `fakes/approval.py` | `FakeApproval`: un `ApprovalGate` que responde con un guion de decisiones, guarda las peticiones en `requests` y falla si se agota. `HangingApproval`: nunca responde, para probar Ctrl+C durante la pregunta |
| `fakes/catalog.py` | `MemoryCatalog`: un `ModelCatalog` con los `ModelInfo` que recibe |
| `fakes/sessions.py` | `MemorySessionStore` y `MemoryLog`: las sesiones en memoria, que se portan como el adaptador real (bloqueo, errores, nada tras `close()`, entradas por JSON, todo o nada) |
| `architecture/test_no_hidden_characters.py` | Ningún carácter bidi o de control invisible en `src`, `tests` ni `docs` |
| `architecture/test_tool_params.py` | Las siete herramientas rechazan argumentos de más (`additionalProperties: false`) |
| `architecture/test_core_imports.py` | `domain`, `ports` y `application` solo usan la biblioteca estándar y Pydantic |
