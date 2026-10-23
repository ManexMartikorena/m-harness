# Mapa del repositorio

Dónde está cada cosa. Se actualiza en el mismo PR que crea, mueve o borra
ficheros.

Última actualización: 2026-10-23 (hito 5 cerrado, con la mejora "cero
deuda" y los arreglos de la auditoría final).

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
| `guia/05-permisos.md` | Nota del hito 5: leer frente a efecto, la pregunta y sus ámbitos, lo que nunca es para la sesión, escribir sin romper nada, ejecutar comandos (y lo que no protege), lo ejecutado consta y las reglas en el dominio |
| `guia/04-tool-calling.md` | Nota del hito 4: herramientas con JSON Schema, el viaje de una llamada, el bucle y su límite, errores devueltos al modelo, perímetro y secretos |
| `guia/03-streaming.md` | Nota del hito 3: SSE, eventos propios, fallos a mitad, cancelar con Ctrl+C, tokens de razonamiento y el spinner |
| `specs/PLANTILLA.md` | Formato de las specs de hito y de mejora |
| `specs/hito-1-esqueleto.md` | Spec del hito 1 (IMPLEMENTADA): paquete, capas, calidad, CI y release |
| `specs/hito-2-primera-conversacion.md` | Spec del hito 2 (IMPLEMENTADA): dominio, puerto `ModelClient`, adaptador de OpenAI, configuración y conversación en la terminal |
| `specs/hito-5-permisos.md` | Spec del hito 5 (IMPLEMENTADA): contrato de aprobación, ámbitos de sesión, `write_file`, `edit_file`, `run_command` con `CommandRunner`, lo ejecutado consta y `refusal` |
| `specs/hito-4-bucle-agentico.md` | Spec del hito 4 (IMPLEMENTADA): bloques de llamada y resultado, `ToolCallDelta`, puerto `Tool`, cuatro herramientas de solo lectura, el bucle `Agent` y la terminal con llamadas |
| `specs/mejora-2026-10-23-deuda-hito-5.md` | Mejora (IMPLEMENTADA): cero deuda antes de cerrar el hito 5 — fallos de la auditoría, arquitectura, escritura de ficheros, entorno de los comandos y `.gitignore` |
| `specs/hito-3-streaming.md` | Spec del hito 3 (IMPLEMENTADA): eventos del modelo, `stream()` en el puerto junto a `complete()`, `collect()`, SSE a mano, spinner de espera y Ctrl+C por respuesta |

## Código: `src/mharness/`

Arquitectura hexagonal (DESIGN §3). Las reglas entre capas las comprueba
import-linter (`pyproject.toml`).

| Fichero | Capa | Qué es |
|---|---|---|
| `__init__.py` | paquete | `DISTRIBUTION` y `__version__`: el nombre y la versión de `maha`, en un solo sitio |
| `__main__.py` | entrada | `python -m mharness`: igual que `maha` |
| `bootstrap.py` | raíz de composición | `main()` del comando `maha`: lee la configuración, crea el adaptador, las siete herramientas sobre el directorio de arranque (`run_command` con `LocalCommandRunner` y el entorno de `command_env()`, sin la clave del proveedor), un solo `StdinLines` para la conversación y las preguntas, y el gate: `TerminalApproval` en una terminal, `DenyAll` sin ella; el único que conoce todas las piezas |
| `config.py` | configuración (hermana de `adapters`) | `load()`: proveedores predefinidos, del usuario y del proyecto (este, solo `provider` y `model`); la clave, del entorno |
| `domain/messages.py` | domain | `TextBlock`, `ToolCallBlock`, `ToolResultBlock` y `Message`: mensajes hechos de bloques, validados por `type` |
| `domain/model.py` | domain | `ModelRequest` (con `tools`), `ToolSpec`, `ModelResponse`, `Usage` y `StopReason` |
| `domain/events.py` | domain | `TextDelta`, `ToolCallDelta`, `MessageEnd` y `ModelEvent`: lo que llega mientras el modelo responde |
| `domain/commands.py` | domain | `CommandResult` (`exit_code`, `output`, `truncated`, `timed_out`) y `OUTPUT_MAX_CHARS` (30 000) |
| `domain/environment.py` | domain | `command_env()`: las variables que recibe un comando, por lista de permitidas (spec `mejora-2026-10-23-deuda-hito-5`, E1) |
| `domain/tools.py` | domain | `Permission` (`read` o `effect`) y `ToolError`, el fallo esperado que se explica al modelo |
| `domain/approval.py` | domain | `Decision` (`once`, `session` o `deny`) y `ApprovalRequest` (`tool`, `title`, `detail`, `scope`, `warning`): la pregunta antes de ejecutar y la respuesta |
| `domain/agent_events.py` | domain | `ToolCallProposed`, `ApprovalRequested`, `ToolFinished` (con `decision`), `ModelCallFinished`, `TurnFinished` (`end_turn`, `max_steps` o `denied`) y `AgentEvent`: lo que el bucle cuenta a la terminal |
| `domain/gitignore.py` | domain | `GitIgnore`: las reglas de `.gitignore` (gitignore(5)) traducidas a mano a expresiones regulares, sin tocar el disco (spec `mejora-2026-10-23-deuda-hito-5`, E6) |
| `domain/paths.py` | domain | `is_secret()` y `SKIPPED_DIRS`: qué ficheros no ve el modelo y qué carpetas no se recorren, sin tocar el disco. Las reglas de lo que pregunta una ruta ya resuelta: `is_inside()`, `is_secret_at()`, `read_warning()` y `change_warning()` (también `.git` y lo que ejecuta código: `.github`, `.husky`, `.vscode`, `.maha`, `.pre-commit-config.yaml`, `.envrc`), con los textos de los avisos |
| `domain/errors.py` | domain | `ModelError` y sus cinco tipos (autenticación, límite, petición, no disponible, respuesta) |
| `ports/commands.py` | ports | `CommandRunner`: `run(command, *, cwd, time_limit, env) -> CommandResult`; mata el comando al pasar el tiempo o al cancelar |
| `ports/tools.py` | ports | `Tool`: nombre, descripción, modelo Pydantic de parámetros, permiso, `approval()` asíncrono (qué preguntar antes, o `None`), `run()` y `summary()` |
| `ports/approval.py` | ports | `ApprovalGate`: `decide(request) -> Decision`; quien aprueba una llamada |
| `ports/model.py` | ports | `ModelClient`: `complete(request) -> response` y `stream(request) -> eventos` |
| `application/collect.py` | application | `Accumulator`: la respuesta entera a partir de los eventos, con las llamadas a herramientas juntadas por `index` |
| `application/tools.py` | application | `ToolRegistry`: herramientas por nombre y sus `ToolSpec`; acepta las de efecto (el bucle pregunta antes) |
| `application/approvals.py` | application | `SessionApprovals`: los `scope` aprobados para toda la sesión, en memoria (`covers()` y `record()`); un `scope` `None` nunca se guarda |
| `application/agent.py` | application | `Agent`: el bucle agéntico (modelo → herramientas → resultados, hasta 25 pasos), con los errores devueltos al modelo. Pregunta al `gate` antes de ejecutar y solo ejecuta con una respuesta de `DECISIONS`; una negativa termina el turno; lo ejecutado consta aunque falle el modelo o se cancele |
| `adapters/models/sse.py` | adapters | `parse_sse()`: el dato de cada evento SSE, con las líneas partidas solo en CRLF, LF o CR |
| `adapters/models/openai_chat.py` | adapters | `OpenAIChatClient`: la conversación en formato OpenAI Chat Completions, con httpx. `complete()` (respuesta entera) y `stream()` (eventos SSE); envía herramientas, llamadas y resultados; traduce respuesta, trozos (también `tool_calls`) y errores. `refusal` (con stream y sin él) llega como texto |
| `adapters/tools/__init__.py` | adapters | Exporta `Workspace`, las cuatro de lectura, `WriteFile`, `EditFile` y `RunCommand` |
| `adapters/tools/search_worker.py` | adapters | El proceso hijo donde `grep` ejecuta la regex del modelo (`search_files()`), con tiempo límite y matado con Ctrl+C: una regex catastrófica no congela `maha` |
| `adapters/tools/files.py` | adapters | `Workspace` (perímetro del directorio de trabajo) y las herramientas de lectura `read_file`, `list_dir`, `glob` y `grep`, con topes y sin hilos: fuera del directorio o con un secreto, su `approval()` pregunta (`scope=None`) y `run()` solo lee la ruta resuelta que se preguntó. `run()` solo ejecuta la llamada exacta que se preguntó (`_Asked`, también con los bytes que mostró la pregunta). `WriteFile` (`write_file`: vista previa o diff) y `EditFile` (`edit_file`: texto exacto, diff, adaptación a CRLF), herramientas `effect`; con aviso (las reglas de `domain/paths.py`), nunca para la sesión, y los errores que dependen del contenido esperan a la aprobación. `CHANGE_MAX_FILE_BYTES` (2 MiB) para cambiar un fichero; `_reading`: un `OSError` al leer da `cannot read`; `_endings`: el aviso de cambio de saltos de línea en el diff. Escritura atómica compartida (`_as_shown` y `_write`): temporal `.maha-<hex>.tmp` en la misma carpeta con el propietario, el modo y los atributos extendidos del original, `fsync`, última comprobación, `os.replace` y `fsync` de la carpeta y de las carpetas nuevas; con enlaces duros o atributos que no se copian, escribe en el sitio y, si falla, devuelve los bytes viejos. Una escritura que falla borra las carpetas que creó. El diff recorta lo común y no se calcula por encima de `DIFF_MAX_WORK` líneas. `grep` recorre aquí y busca en `search_worker.py` por tandas de `GREP_BATCH_FILES` (`_search_apart`, `GREP_TIME_LIMIT` para toda la búsqueda). `glob` y `grep` saltan al recorrer lo que ignoran `.gitignore` y `.git/info/exclude` (`_add_rules`). `edit_file` cuenta las apariciones solapadas y acepta cualquier salto de línea en `old_string`. |
| `adapters/tools/shell.py` | adapters | `RunCommand` (`run_command`, `effect`): pregunta con el comando, el directorio y "with your permissions", `scope` del comando exacto; usa el puerto `CommandRunner`, nunca el adaptador local. |
| `adapters/commands/local.py` | adapters | `LocalCommandRunner`: `create_subprocess_shell` en un grupo de procesos propio, stdin cerrado, stderr con stdout, salida leída mientras corre y cortada a 30 000 caracteres, y `killpg(SIGKILL)` del grupo entero al pasar el tiempo, al cancelar y al terminar; como *subreaper*, mata también lo que el comando sacó de su grupo (`_kill_escaped`). Sin hilos |
| `adapters/cli/app.py` | adapters | Línea de comandos con argparse: `parse()` (`--version`, la ayuda) y `fail()` |
| `adapters/cli/conversation.py` | adapters | `converse()`: leer, enviar al `Agent` y mostrar la respuesta según llega, cada llamada a herramienta (`→`, `✓`/`✗`), la negativa (`[denied: …]`) y la línea de tokens con las llamadas, con `/exit`, Ctrl+D y Ctrl+C (a mitad de respuesta, solo la corta). Todo texto no confiable pasa por `clean()` |
| `adapters/cli/approval.py` | adapters | `TerminalApproval`: la pregunta (`┌`, `│`, `└ Allow?`), `y`/`a`/`n`, Ctrl+D deniega, aviso en amarillo, detalle cortado y saneado con `clean()`. `DenyAll`: sin terminal, deniega sin preguntar |
| `adapters/cli/input.py` | adapters | `StdinLines` (lectura de stdin sin hilos) y `ReadLine`: un solo lector para la conversación y las preguntas |
| `adapters/cli/text.py` | adapters | `clean()`: escapa los caracteres de control y bidi del texto no confiable antes de pintarlo (spec `mejora-2026-10-23-deuda-hito-5`, A2) |
| `adapters/cli/spinner.py` | adapters | `Spinner` y `frame()`: spinner braille con "maha" en colores ANSI mientras llega el primer token; solo en una terminal real, y `NO_COLOR` |

## Tests: `tests/`

| Fichero | Qué comprueba |
|---|---|
| `test_entry_point.py` | El script `maha` entra por `bootstrap.main`; `python -m mharness --version` |
| `test_bootstrap.py` | `maha` de punta a punta con respx (streams SSE) y un pipe o una pseudoterminal como stdin: dos turnos, un stream cortado, las siete herramientas, una llamada a `read_file` sobre un fichero real, sin terminal una escritura se deniega sin preguntar, en una terminal `run_command` pregunta y su `env` no ve la clave; errores de configuración y `--version` |
| `adapters/test_cli.py` | `--version`, la ayuda, sin argumentos devuelve las opciones, el error de uso y `fail()` |
| `adapters/test_conversation.py` | Respuesta en directo y tokens, llamadas a herramientas (marcas, argumentos cortados, plural, límite de pasos, fallo interno, Ctrl+C durante una herramienta, que guarda el turno con la llamada cancelada), `/exit`, Ctrl+D, Ctrl+C en el prompt y a mitad de respuesta, errores a mitad, spinner y `StdinLines` |
| `adapters/test_approval.py` | `TerminalApproval`: la pregunta, cada respuesta, repetir, Ctrl+D, sin `scope` no hay `a`, aviso con y sin color, detalle cortado y caracteres de control escapados; `DenyAll` |
| `adapters/test_spinner.py` | Fotogramas con y sin color, `NO_COLOR`, solo en terminal, borrado de la línea |
| `adapters/test_sse.py` | Analizador SSE: eventos, comentarios, saltos de línea, trozos partidos, U+2028 y el tope de 1 MiB |
| `adapters/test_local_runner.py` | `LocalCommandRunner` con comandos reales e inocuos: salida y código, stderr mezclado, directorio, stdin cerrado, corte sin bloquear, tiempo límite con salida parcial, Ctrl+C y fin normal matan el grupo, entorno exacto |
| `adapters/test_shell_tool.py` | `run_command` con `FakeRunner`: descripción, límites de `timeout`, la pregunta y su `scope`, el texto del resultado (código, corte, tiempo) y el resumen |
| `adapters/test_file_tools.py` | Las seis herramientas de ficheros en `tmp_path`. Lectura: resultados, topes, perímetro (`..`, rutas absolutas, enlaces), secretos, binarios y errores; dentro no pregunta; fuera o con un secreto pregunta, con los avisos, y los fallos baratos van antes; un enlace cambiado tras la pregunta no se lee. `write_file`: vista previa, diff, carpetas, `scope`, errores antes de preguntar, lo mostrado es lo escrito, escritura atómica (fallo sin temporal, modo, umask, `fsync` del fichero y de la carpeta). `edit_file`: diff, 0 o varias apariciones, `replace_all`, CRLF (se conserva y se adapta), UTF-8, errores antes de preguntar, lo mostrado es lo editado. De la revisión: con aviso, la pregunta va antes de los errores de contenido (detail de reserva); tamaño máximo; `cannot read` (y `grep` salta los ilegibles); `run()` rechaza otros parámetros que los preguntados; `.git` nunca para la sesión; aviso de cambio de saltos de línea |
| `adapters/test_openai_chat.py` | `complete()`: JSON y cabeceras enviados, herramientas e historial con llamadas y resultados, traducción de la respuesta y de cada error, y que la clave nunca sale en un error (con respx) |
| `adapters/test_openai_chat_stream.py` | `stream()`: petición con `stream` y herramientas, traducción de los trozos medidos (también `tool_calls`), errores antes y a mitad del stream, y cierre de la conexión al cancelar (con respx) |
| `fixtures/openai_chat/` | Respuestas de ejemplo de Chat Completions (JSON) y streams SSE (`.sse`), también con llamadas a herramientas, con la forma medida en OpenCode Go, con datos inventados |
| `unit/test_messages.py` | `Message.text` une los bloques de texto; bloques de llamada y resultado; validación por `type`; mensajes inmutables |
| `unit/test_model.py` | `Usage` a 0 por defecto; petición sin `system` y sin herramientas; `ToolSpec`; `StopReason` válido |
| `unit/test_events.py` | Eventos inmutables (también `ToolCallDelta`), `type` por defecto y `StopReason` válido |
| `unit/test_collect.py` | `Accumulator` (por el `collect()` del fake) junta el texto y las llamadas (argumentos partidos, varios `index`), toma el final de `MessageEnd` y falla sin él |
| `unit/test_paths.py` | `is_secret()`: qué rutas son secretas y cuáles no (sin distinguir mayúsculas); `read_warning()` y `change_warning()`, sin disco |
| `unit/test_gitignore.py` | `GitIgnore`: 35 casos de las reglas de gitignore(5), la última regla gana, `!`, ficheros más hondos y CRLF |
| `unit/test_environment.py` | `command_env()`: solo pasan las variables permitidas, nunca una credencial con prefijo permitido, y `drop` |
| `unit/test_fake_runner.py` | `FakeRunner` cumple el puerto, sigue el guion, guarda lo que se ejecutó y falla al agotarse |
| `unit/test_errors.py` | Todos los errores del modelo heredan de `ModelError` |
| `unit/test_fake_model.py` | El fake cumple el puerto, sigue el guion (también en stream, con `Gate` y `HANG`) y falla al agotarse |
| `unit/test_config.py` | Combinación de niveles, `[providers]` prohibido en el proyecto, errores con mensaje y la clave |
| `unit/test_agent.py` | El bucle: sin llamadas, una, dos en orden, límite de pasos, historial, uso sumado, errores devueltos al modelo; aprobación (`once`, `session` por `scope`, sin `scope`, `deny` termina el turno, `once` y luego `deny`, decisión no válida, efecto sin petición, `ToolError` y fallo en `approval()`); fallo en `summary()` y JSON demasiado anidado; lo ejecutado consta ante fallo del modelo, Ctrl+C durante una llamada, la pregunta o el stream, y el bucle cerrado (`GeneratorExit`) |
| `unit/test_approvals.py` | `SessionApprovals`: `session` guarda el `scope`, cada `scope` cubre solo el suyo, `once` y `deny` no guardan nada, sin `scope` nunca se guarda |
| `unit/test_fake_approval.py` | `FakeApproval` cumple el puerto, sigue el guion y falla al agotarse; `ApprovalRequest` sin aviso por defecto e inmutable |
| `unit/test_tools_registry.py` | `ToolSpec` desde Pydantic, búsqueda, nombre repetido rechazado y herramienta con efecto aceptada |
| `unit/test_fake_tool.py` | `FakeTool` cumple el puerto y sigue su guion, también en `approval()` |
| `fakes/model.py` | `FakeModelClient` guionizado (`complete()` y `stream()`), `collect()`, `reply()`, `tool_calls()`, `END`, `Gate` y `HANG` (no es un test: lo usan los tests) |
| `fakes/tools.py` | `FakeTool`: una herramienta guionizada, con `permission`, `requests` (lo que devuelve `approval()`: petición, `None` o error) y `gate` para probar la cancelación |
| `fakes/terminal.py` | `ScriptedInput`: lo que teclea una persona, línea a línea, y luego Ctrl+D |
| `fakes/commands.py` | `FakeRunner`: un `CommandRunner` que responde con un guion de `CommandResult` y guarda cada comando en `ran` |
| `fakes/approval.py` | `FakeApproval`: un `ApprovalGate` que responde con un guion de decisiones, guarda las peticiones en `requests` y falla si se agota. `HangingApproval`: nunca responde, para probar Ctrl+C durante la pregunta |
| `architecture/test_no_hidden_characters.py` | Ningún carácter bidi o de control invisible en `src`, `tests` ni `docs` |
| `architecture/test_core_imports.py` | `domain`, `ports` y `application` solo usan la biblioteca estándar y Pydantic |
