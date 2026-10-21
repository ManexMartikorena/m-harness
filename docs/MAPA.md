# Mapa del repositorio

Dónde está cada cosa. Se actualiza en el mismo PR que crea, mueve o borra
ficheros.

Última actualización: 2026-10-21 (hito 4, PR 2: herramientas en el adaptador).

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
| `guia/03-streaming.md` | Nota del hito 3: SSE, eventos propios, fallos a mitad, cancelar con Ctrl+C, tokens de razonamiento y el spinner |
| `specs/PLANTILLA.md` | Formato de las specs de hito y de mejora |
| `specs/hito-1-esqueleto.md` | Spec del hito 1 (IMPLEMENTADA): paquete, capas, calidad, CI y release |
| `specs/hito-2-primera-conversacion.md` | Spec del hito 2 (IMPLEMENTADA): dominio, puerto `ModelClient`, adaptador de OpenAI, configuración y conversación en la terminal |
| `specs/hito-4-bucle-agentico.md` | Spec del hito 4 (APROBADA): bloques de llamada y resultado, `ToolCallDelta`, puerto `Tool`, cuatro herramientas de solo lectura, el bucle `Agent` y la terminal con llamadas |
| `specs/hito-3-streaming.md` | Spec del hito 3 (IMPLEMENTADA): eventos del modelo, `stream()` en el puerto junto a `complete()`, `collect()`, SSE a mano, spinner de espera y Ctrl+C por respuesta |

## Código: `src/mharness/`

Arquitectura hexagonal (DESIGN §3). Las reglas entre capas las comprueba
import-linter (`pyproject.toml`).

| Fichero | Capa | Qué es |
|---|---|---|
| `__init__.py` | — | El paquete |
| `__main__.py` | entrada | `python -m mharness`: igual que `maha` |
| `bootstrap.py` | raíz de composición | `main()` del comando `maha`: lee la configuración, crea el adaptador y abre la conversación; el único que conoce todas las piezas |
| `config.py` | configuración (hermana de `adapters`) | `load()`: proveedores predefinidos, del usuario y del proyecto (este, solo `provider` y `model`); la clave, del entorno |
| `domain/messages.py` | domain | `TextBlock`, `ToolCallBlock`, `ToolResultBlock` y `Message`: mensajes hechos de bloques, validados por `type` |
| `domain/model.py` | domain | `ModelRequest` (con `tools`), `ToolSpec`, `ModelResponse`, `Usage` y `StopReason` |
| `domain/events.py` | domain | `TextDelta`, `ToolCallDelta`, `MessageEnd` y `ModelEvent`: lo que llega mientras el modelo responde |
| `domain/errors.py` | domain | `ModelError` y sus cinco tipos (autenticación, límite, petición, no disponible, respuesta) |
| `ports/model.py` | ports | `ModelClient`: `complete(request) -> response` y `stream(request) -> eventos` |
| `application/collect.py` | application | `Accumulator` y `collect()`: la respuesta entera a partir de los eventos, con las llamadas a herramientas juntadas por `index` |
| `application/chat.py` | application | `Chat`: la conversación en memoria, reenviada entera en cada llamada. `send()` (entera) y `stream()` (eventos; guarda el turno al llegar `MessageEnd`) |
| `adapters/models/sse.py` | adapters | `parse_sse()`: el dato de cada evento SSE, con las líneas partidas solo en CRLF, LF o CR |
| `adapters/models/openai_chat.py` | adapters | `OpenAIChatClient`: la conversación en formato OpenAI Chat Completions, con httpx. `complete()` (respuesta entera) y `stream()` (eventos SSE); envía herramientas, llamadas y resultados; traduce respuesta, trozos (también `tool_calls`) y errores |
| `adapters/cli/app.py` | adapters | Línea de comandos con argparse: `parse()` (`--version`, la ayuda) y `fail()` |
| `adapters/cli/conversation.py` | adapters | `converse()`: leer, enviar y mostrar la respuesta según llega, con `/exit`, Ctrl+D y Ctrl+C (a mitad de respuesta, solo la corta); `StdinLines`, lectura de stdin sin hilos |
| `adapters/cli/spinner.py` | adapters | `Spinner` y `frame()`: spinner braille con "maha" en colores ANSI mientras llega el primer token; solo en una terminal real, y `NO_COLOR` |

## Tests: `tests/`

| Fichero | Qué comprueba |
|---|---|
| `test_entry_point.py` | El script `maha` entra por `bootstrap.main`; `python -m mharness --version` |
| `test_bootstrap.py` | `maha` de punta a punta con respx (streams SSE) y un pipe como stdin: dos turnos, un stream cortado, y los errores de arranque |
| `adapters/test_cli.py` | `--version`, la ayuda, sin argumentos devuelve las opciones, el error de uso y `fail()` |
| `adapters/test_conversation.py` | Respuesta en directo y tokens, `/exit`, Ctrl+D, Ctrl+C en el prompt y a mitad de respuesta, errores a mitad, spinner y `StdinLines` |
| `adapters/test_spinner.py` | Fotogramas con y sin color, `NO_COLOR`, solo en terminal, borrado de la línea |
| `adapters/test_sse.py` | Analizador SSE: eventos, comentarios, saltos de línea, trozos partidos, U+2028 y el tope de 1 MiB |
| `adapters/test_openai_chat.py` | `complete()`: JSON y cabeceras enviados, herramientas e historial con llamadas y resultados, traducción de la respuesta y de cada error, y que la clave nunca sale en un error (con respx) |
| `adapters/test_openai_chat_stream.py` | `stream()`: petición con `stream` y herramientas, traducción de los trozos medidos (también `tool_calls`), errores antes y a mitad del stream, y cierre de la conexión al cancelar (con respx) |
| `fixtures/openai_chat/` | Respuestas de ejemplo de Chat Completions (JSON) y streams SSE (`.sse`), también con llamadas a herramientas, con la forma medida en OpenCode Go, con datos inventados |
| `unit/test_messages.py` | `Message.text` une los bloques de texto; bloques de llamada y resultado; validación por `type`; mensajes inmutables |
| `unit/test_model.py` | `Usage` a 0 por defecto; petición sin `system` y sin herramientas; `ToolSpec`; `StopReason` válido |
| `unit/test_events.py` | Eventos inmutables (también `ToolCallDelta`), `type` por defecto y `StopReason` válido |
| `unit/test_collect.py` | `collect()` junta el texto y las llamadas (argumentos partidos, varios `index`), toma el final de `MessageEnd` y falla sin él |
| `unit/test_errors.py` | Todos los errores del modelo heredan de `ModelError` |
| `unit/test_fake_model.py` | El fake cumple el puerto, sigue el guion (también en stream, con `Gate` y `HANG`) y falla al agotarse |
| `unit/test_config.py` | Combinación de niveles, `[providers]` prohibido en el proyecto, errores con mensaje y la clave |
| `unit/test_chat.py` | `Chat` reenvía el historial y deshace el turno si la llamada falla o se cancela; `stream()` guarda el turno al llegar `MessageEnd` |
| `fakes/model.py` | `FakeModelClient` guionizado (`complete()` y `stream()`), `reply()`, `END`, `Gate` y `HANG` (no es un test: lo usan los tests) |
| `architecture/test_core_imports.py` | `domain`, `ports` y `application` solo usan la biblioteca estándar y Pydantic |
