# Mapa del repositorio

Dónde está cada cosa. Se actualiza en el mismo PR que crea, mueve o borra
ficheros.

Última actualización: 2026-10-20 (hito 2, PR 1: el núcleo).

## Raíz

| Fichero | Qué es |
|---|---|
| `README.md` | Presentación pública del proyecto y hoja de ruta |
| `LICENSE` | Licencia MIT |
| `AGENTS.md` | Reglas para cualquier agente de código: la única fuente de reglas |
| `CLAUDE.md` | Importa `AGENTS.md` para Claude Code |
| `.gitignore` | Lo que nunca entra en git |
| `.gitattributes` | Finales de línea LF en todas las máquinas |
| `pyproject.toml` | Metadatos, dependencias de desarrollo y configuración de ruff, mypy, pytest e import-linter |
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
| `bootstrap.py` | raíz de composición | `main()` del comando `maha`; el único que conoce todas las piezas |
| `domain/messages.py` | domain | `TextBlock` y `Message`: mensajes hechos de bloques |
| `domain/model.py` | domain | `ModelRequest`, `ModelResponse`, `Usage` y `StopReason` |
| `domain/errors.py` | domain | `ModelError` y sus cinco tipos (autenticación, límite, petición, no disponible, respuesta) |
| `ports/model.py` | ports | `ModelClient`: `complete(request) -> response` |
| `application/chat.py` | application | `Chat`: la conversación en memoria, reenviada entera en cada llamada |
| `adapters/cli/app.py` | adapters | Línea de comandos con argparse: `--version` y la ayuda |

## Tests: `tests/`

| Fichero | Qué comprueba |
|---|---|
| `test_entry_point.py` | El script `maha` entra por `bootstrap.main`; `python -m mharness --version` |
| `adapters/test_cli.py` | `--version`, la ayuda y el error con una opción desconocida |
| `unit/test_messages.py` | `Message.text` une los bloques; mensajes inmutables |
| `unit/test_model.py` | `Usage` a 0 por defecto; petición sin `system`; `StopReason` válido |
| `unit/test_errors.py` | Todos los errores del modelo heredan de `ModelError` |
| `unit/test_fake_model.py` | El fake cumple el puerto, sigue el guion y falla al agotarse |
| `unit/test_chat.py` | `Chat` reenvía el historial y deshace el turno si la llamada falla |
| `fakes/model.py` | `FakeModelClient` guionizado y `reply()` (no es un test: lo usan los tests) |
| `architecture/test_core_imports.py` | `domain`, `ports` y `application` solo usan la biblioteca estándar y Pydantic |
