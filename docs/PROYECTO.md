# Cómo se ha hecho M-Harness

`maha` es el producto: un agente de IA para la terminal (el
[README](../README.es.md) explica qué hace y cómo se usa). **M-Harness es el
proyecto que lo construye**, y este documento cuenta cómo: por qué existe,
cómo se trabaja y cómo puedes construir tú un agente desde cero siguiendo
el mismo camino.

## El objetivo

El proyecto tiene dos objetivos, al mismo nivel:

1. **Entender un agente por dentro, construyéndolo.** Usar Claude Code u
   OpenCode no enseña cómo se gestionan el bucle, los permisos, el contexto
   o la memoria. Construirlo pieza a pieza, sí.
2. **Un producto profesional para cualquier usuario**: lo más completo
   posible en capacidades (comandos, herramientas, conectores, memoria…) e
   intuitivo de usar. Las capacidades se han comparado con las de OpenCode
   y Claude Code, contra su documentación, en
   [`COMPARATIVA.md`](COMPARATIVA.md).

El análisis completo (problema, alcance, criterios de éxito) está en
[`ANALISIS.md`](ANALISIS.md).

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

## El principio

- **A mano lo que es del agente:** bucle, adaptadores de modelos, permisos,
  contexto, memoria y subagentes. Nada de LiteLLM, LangGraph ni frameworks
  de agentes.
- **Librerías estándar para la fontanería:** HTTP (httpx), validación
  (Pydantic) e interfaz de terminal.
- **La industria siempre al lado:** cada pieza documenta qué se usa
  normalmente para resolverla (LiteLLM, LangGraph, Mem0, OpenTelemetry…) y
  cuándo se elegiría.
- **El historial del repositorio es la guía:** cada pieza llega en su
  propio PR, con su spec, sus tests y una nota que explica el concepto.

## La arquitectura

Monolito modular con arquitectura hexagonal (puertos y adaptadores):

- **`domain`:** tipos y reglas puras (mensajes, herramientas, eventos, coste).
- **`ports`:** interfaces con el exterior (modelo, herramientas, comandos,
  aprobaciones, sesiones, trazas, catálogo).
- **`application`:** casos de uso (el bucle, las sesiones, el resumen de
  trazas).
- **`adapters`:** implementaciones reales (proveedores de modelos, ficheros,
  comandos, terminal).

Cambiar de proveedor es cambiar de adaptador, y el bucle se prueba sin red.
Una regla automática (import-linter) impide que una capa importe a la que no
debe. El detalle: [`DESIGN.md`](DESIGN.md); dónde está cada fichero:
[`MAPA.md`](MAPA.md).

## Cómo se trabaja

- **Un agente de código escribe, una persona revisa.** El código lo escribe
  un agente de código siguiendo [`AGENTS.md`](../AGENTS.md) (sus reglas,
  su flujo y lo que tiene que explicar); el mantenedor revisa cada fichero y
  decide el alcance.
- **Spec antes de código.** Cada hito empieza con una spec (en
  [`specs/`](specs/)) en su propio PR, con sus dudas para el mantenedor.
  Integrarla es aprobarla. Al cerrarse, la spec cuenta lo aprendido al
  implementar.
- **Commits pequeños**, cada uno con tests y lint en verde.
- **Cada fallo encontrado se convierte en test antes de arreglarse.**
  Ninguno se deja sin arreglar por decisión del agente.
- **CI en cada PR:** lint, tipos estrictos, reglas de arquitectura, tests y
  escaneo de secretos. Sin el CI en verde, nada entra en `main`.
- **Un tag y una release por hito**, y auditorías independientes del código
  antes de cerrar.

## Hoja de ruta

| # | Hito | Estado |
|---|---|---|
| 1 | Esqueleto del proyecto y CI | ✅ `v0.1.0` |
| 2 | Primera conversación con un modelo | ✅ `v0.2.0` |
| 3 | Streaming | ✅ `v0.3.0` |
| 4 | Tool calling y bucle agéntico | ✅ `v0.4.0` |
| 5 | Permisos y herramientas con efecto | ✅ `v0.5.0` (y `v0.5.1`, `v0.5.2`) |
| 6 | Sesiones e historial | ✅ `v0.6.0` (y `v0.6.1`) |
| 7 | Trazas y coste | ✅ `v0.7.0` |
| 8 | Evals y modo no interactivo | ⬜ |
| 9 | Adaptador de Anthropic | ⬜ |
| 10 | System prompt por capas | ⬜ |
| 11 | Gestión del contexto | ⬜ |
| 12 | Deshacer y puntos de control | ⬜ |
| 13 | Skills y comandos personalizados | ⬜ |
| 14 | Memoria persistente | ⬜ |
| 15 | Sandbox y modos de permiso | ⬜ |
| 16 | Subagentes y agentes propios | ⬜ |
| 17 | MCP | ⬜ |
| 18 | Hooks | ⬜ |
| 19 | Web | ⬜ |
| 20 | Multimodal | ⬜ |
| 21 | Interfaz completa (TUI) | ⬜ |
| 22 | Exportador OpenTelemetry | ⬜ |
| 23 | Versión 1.0 y distribución | ⬜ |

Qué entra en cada hito: [`DESIGN.md`](DESIGN.md) §14. El estado al día:
[`ESTADO.md`](ESTADO.md).

## Hazlo tú desde cero

Todo el camino está en el repositorio, en orden. Para construir tu propio
agente:

1. **Empieza por la guía**, [`guia/`](guia/README.md): una nota por hito,
   corta, con el problema, cómo se resuelve y qué se usa en la industria.
   Léelas en orden; cada una se apoya en la anterior.
2. **Para cada hito, lee su spec** en [`specs/`](specs/): qué se decidió y
   por qué, el plan de tests, la verificación a mano y lo que se aprendió al
   implementarlo (los errores incluidos).
3. **Mira cómo se construyó**: cada hito es un tag (`v0.N.0`) y varios PRs
   con commits pequeños. La [lista de releases](https://github.com/ManexMartikorena/m-harness/releases)
   resume cada versión; los PRs cuentan cada pieza.
4. **Copia el método, no solo el código**: [`AGENTS.md`](../AGENTS.md) es la
   forma de trabajar con un agente de código (spec, ramas, commits,
   revisión, evals), y [`ANALISIS.md`](ANALISIS.md) y
   [`DESIGN.md`](DESIGN.md) son el análisis y el diseño que lo preceden.

## Documentación

| Documento | Qué cuenta |
|---|---|
| [`ANALISIS.md`](ANALISIS.md) | El problema, el alcance y los criterios de éxito |
| [`DESIGN.md`](DESIGN.md) | La arquitectura, el stack y el plan de hitos |
| [`COMPARATIVA.md`](COMPARATIVA.md) | Las capacidades de OpenCode y Claude Code frente al plan |
| [`guia/`](guia/README.md) | Una nota por hito: los conceptos |
| [`specs/`](specs/) | La spec de cada hito y de cada mejora |
| [`ESTADO.md`](ESTADO.md) | El estado del trabajo |
| [`HISTORIAL_DESARROLLO.md`](HISTORIAL_DESARROLLO.md) | Lo hecho en cada hito y sesión, con detalle |
| [`MAPA.md`](MAPA.md) | Dónde está cada cosa |
| [`PUESTA_EN_MARCHA.md`](PUESTA_EN_MARCHA.md) | Preparar una máquina para desarrollar |
