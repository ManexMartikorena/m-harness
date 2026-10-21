# M-Harness

[![CI](https://github.com/ManexMartikorena/m-harness/actions/workflows/ci.yml/badge.svg)](https://github.com/ManexMartikorena/m-harness/actions/workflows/ci.yml)

**Un agente de terminal construido desde cero, pieza a pieza, para entender cómo
funciona un arnés de agente por dentro.**

`maha` es un agente de propósito general para la terminal, en la línea de
Claude Code u OpenCode. Conversa contigo, usa herramientas sobre tu directorio
de trabajo y pide aprobación antes de cualquier efecto.

Lo que lo diferencia es cómo se construye:
- sin frameworks de agentes;
- cada pieza llega en su propio PR, con su spec, sus tests y una nota que
  explica el concepto;
- el historial del repositorio es la guía.

> 🚧 **En construcción.** Hito 3 (streaming) terminado: `maha` conversa en la
> terminal con un modelo y muestra la respuesta según llega, todavía sin
> herramientas. El estado
> al día está en [`docs/ESTADO.md`](docs/ESTADO.md).

```
uv tool install git+https://github.com/ManexMartikorena/m-harness@v0.3.0
```

Necesita un proveedor con formato OpenAI (de serie, OpenCode Go o Zen) y su
clave en una variable de entorno:

```toml
# ~/.config/maha/config.toml
provider = "opencode-go"
model = "glm-5.3-flash"
```

```
$ export OPENCODE_API_KEY=...
$ maha
maha 0.3.0 · opencode-go · glm-5.3-flash · /exit to quit
> Hola, soy Ane
Hola, Ane. ¿En qué te ayudo?
  [tokens: 25 in · 9 out]
```

Mientras espera el primer token, gira un spinner con "maha". Ctrl+C a mitad
de una respuesta la corta y vuelve al prompt; en el prompt, sale.

## Cómo funciona un agente

```
            ┌──────────────────────────────────────────────┐
            ▼                                              │
  mensajes + tools ──► modelo ──► respuesta ──► ¿pide tools? ──no──► fin del turno
                                                  │ sí
                                                  ▼
                              validar ─► permiso ─► ejecutar ─► resultado
```

El modelo nunca ejecuta nada: propone llamadas a herramientas, y el arnés las
valida, comprueba el permiso, las ejecuta y le devuelve el resultado. Todo lo
demás (contexto, memoria, skills, subagentes, MCP) se engancha alrededor de
este bucle.

## Principio

- **A mano lo que es del agente:** bucle, adaptadores de modelos, permisos,
  contexto, memoria y subagentes.
- **Librerías estándar para la fontanería:** HTTP, validación e interfaz de
  terminal.
- **La industria siempre al lado:** cada pieza documenta qué se usa
  normalmente para resolverla (LiteLLM, LangGraph, Mem0, OpenTelemetry…) y
  cuándo se elegiría.

## Arquitectura

Monolito modular con arquitectura hexagonal (puertos y adaptadores):

- **`domain`:** tipos y reglas puras (mensajes, herramientas, eventos).
- **`ports`:** interfaces con el exterior (modelo, herramientas, aprobaciones,
  almacenamiento, trazas).
- **`application`:** casos de uso (el bucle, la ejecución de herramientas, el
  contexto).
- **`adapters`:** implementaciones reales (proveedores de modelos, ficheros,
  terminal, MCP) y la interfaz de terminal.

Cambiar de proveedor es cambiar de adaptador, y el bucle se prueba sin red. El
detalle está en [`docs/DESIGN.md`](docs/DESIGN.md).

## Hoja de ruta

| # | Hito | Estado |
|---|---|---|
| 1 | Esqueleto del proyecto y CI | ✅ `v0.1.0` |
| 2 | Primera conversación con un modelo | ✅ `v0.2.0` |
| 3 | Streaming | ✅ `v0.3.0` |
| 4 | Tool calling y bucle agéntico | ⬜ |
| 5 | Permisos y herramientas con efecto | ⬜ |
| 6 | Sesiones e historial | ⬜ |
| 7 | Trazas y coste | ⬜ |
| 8 | Evals y modo no interactivo | ⬜ |
| 9 | Adaptador de Anthropic | ⬜ |
| 10 | System prompt por capas | ⬜ |
| 11 | Gestión del contexto | ⬜ |
| 12 | Skills | ⬜ |
| 13 | Memoria persistente | ⬜ |
| 14 | Sandbox | ⬜ |
| 15 | Subagentes | ⬜ |
| 16 | MCP | ⬜ |
| 17 | Web | ⬜ |
| 18 | Multimodal | ⬜ |
| 19 | Interfaz completa | ⬜ |
| 20 | Exportador OpenTelemetry | ⬜ |
| 21 | Versión 1.0 | ⬜ |

## Cómo se construye

- **Spec antes de código.** Cada hito empieza con una spec en su propio PR. Se
  aprueba al integrarse.
- **Commits pequeños.** Un commit por cada cosa pequeña, siempre con tests y
  lint en verde.
- **Revisión humana.** El código lo escribe un agente de código siguiendo
  [`AGENTS.md`](AGENTS.md), y cada fichero pasa por revisión antes de
  integrarse.
- **CI en cada PR:** lint, tipos, reglas de arquitectura, tests y escaneo de
  secretos. Sin el CI en verde, nada entra en `main`.
- **Un tag y una release por hito.**

## Documentación

- [`docs/ANALISIS.md`](docs/ANALISIS.md): el problema, el alcance y los
  criterios de éxito.
- [`docs/DESIGN.md`](docs/DESIGN.md): la arquitectura, el stack y el plan de
  hitos.
- [`docs/guia/`](docs/guia/README.md): una nota por pieza, del tool calling a
  los subagentes.
- [`docs/MAPA.md`](docs/MAPA.md): dónde está cada cosa.

## Licencia

[MIT](LICENSE)
