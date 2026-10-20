# Mapa del repositorio

Dónde está cada cosa. Se actualiza en el mismo PR que crea, mueve o borra
ficheros.

Última actualización: 2026-10-20 (hito 2, PR 3: configuración y terminal).

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
| `.github/workflows/ci.yml` | CI: checks con Python 3.14 y 3.15, y gitleaks (commits del PR; historial entero si se lanza a mano) |
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
| `specs/PLANTILLA.md` | Formato de las specs de hito y de mejora |
| `specs/hito-1-esqueleto.md` | Spec del hito 1 (IMPLEMENTADA): paquete, capas, calidad, CI y release |
| `specs/hito-2-primera-conversacion.md` | Spec del hito 2 (APROBADA): dominio, puerto `ModelClient`, adaptador de OpenAI, configuración y conversación en la terminal |

## Código: `src/mharness/`

Arquitectura hexagonal (DESIGN §3). Las reglas entre capas las comprueba
import-linter (`pyproject.toml`).

| Fichero | Capa | Qué es |
|---|---|---|
| `__init__.py` | — | El paquete |
| `__main__.py` | entrada | `python -m mharness`: igual que `maha` |
| `bootstrap.py` | raíz de composición | `main()` del comando `maha`: lee la configuración, crea el adaptador y abre la conversación; el único que conoce todas las piezas |
| `config.py` | configuración (hermana de `adapters`) | `load()`: proveedores predefinidos, del usuario y del proyecto (este, solo `provider` y `model`); la clave, del entorno |
| `domain/messages.py` | domain | `TextBlock` y `Message`: mensajes hechos de bloques |
| `domain/model.py` | domain | `ModelRequest`, `ModelResponse`, `Usage` y `StopReason` |
| `domain/errors.py` | domain | `ModelError` y sus cinco tipos (autenticación, límite, petición, no disponible, respuesta) |
| `ports/model.py` | ports | `ModelClient`: `complete(request) -> response` |
| `application/chat.py` | application | `Chat`: la conversación en memoria, reenviada entera en cada llamada |
| `adapters/models/openai_chat.py` | adapters | `OpenAIChatClient`: la conversación en formato OpenAI Chat Completions, con httpx; traduce respuesta y errores |
| `adapters/cli/app.py` | adapters | Línea de comandos con argparse: `parse()` (`--version`, la ayuda) y `fail()` |
| `adapters/cli/conversation.py` | adapters | `converse()`: leer, enviar y mostrar, con `/exit`, Ctrl+D y Ctrl+C; `StdinLines`, lectura de stdin sin hilos |

## Tests: `tests/`

| Fichero | Qué comprueba |
|---|---|
| `test_entry_point.py` | El script `maha` entra por `bootstrap.main`; `python -m mharness --version` |
| `test_bootstrap.py` | `maha` de punta a punta con respx y un pipe como stdin: dos turnos, y los errores de arranque |
| `adapters/test_cli.py` | `--version`, la ayuda, sin argumentos devuelve las opciones, el error de uso y `fail()` |
| `adapters/test_conversation.py` | Respuesta y tokens, `/exit`, Ctrl+D, Ctrl+C, errores del modelo y `StdinLines` |
| `adapters/test_openai_chat.py` | JSON y cabeceras enviados, traducción de la respuesta y de cada error, y que la clave nunca sale en un error (con respx) |
| `fixtures/openai_chat/` | Respuestas de ejemplo de Chat Completions, con datos inventados |
| `unit/test_messages.py` | `Message.text` une los bloques; mensajes inmutables |
| `unit/test_model.py` | `Usage` a 0 por defecto; petición sin `system`; `StopReason` válido |
| `unit/test_errors.py` | Todos los errores del modelo heredan de `ModelError` |
| `unit/test_fake_model.py` | El fake cumple el puerto, sigue el guion y falla al agotarse |
| `unit/test_config.py` | Combinación de niveles, `[providers]` prohibido en el proyecto, errores con mensaje y la clave |
| `unit/test_chat.py` | `Chat` reenvía el historial y deshace el turno si la llamada falla |
| `fakes/model.py` | `FakeModelClient` guionizado y `reply()` (no es un test: lo usan los tests) |
| `architecture/test_core_imports.py` | `domain`, `ports` y `application` solo usan la biblioteca estándar y Pydantic |
