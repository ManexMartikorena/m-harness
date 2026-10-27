# Comparativa de capacidades: OpenCode, Claude Code y `maha`

Estado: PROPUESTA (2026-10-27) → ACEPTADA (2026-10-27, por el mantenedor,
todas las recomendaciones). Ya está en `docs/DESIGN.md` §14, con los hitos
renumerados: los números de este documento son los nuevos.

## Por qué existe

El 2026-10-27 el mantenedor añadió un segundo objetivo al proyecto (ANALISIS
§4): **un producto profesional para cualquier usuario, lo más completo
posible en capacidades e intuitivo**. Las 17 piezas pasan a ser el mínimo.
Este documento compara lo que ofrecen los dos agentes de terminal de
referencia con nuestro plan, y propone qué entra y cuándo.

## Fuentes y método

- **OpenCode:** las 33 páginas de su documentación oficial,
  https://opencode.ai/docs/ (OpenCode 1). OpenCode 2 tiene la suya en
  https://opencode.ai/v2/docs/; sus novedades van en una sección aparte.
- **Claude Code:** su documentación oficial, https://code.claude.com/docs/
  (índice en `llms.txt`). Algunas páginas se leyeron resumidas o no se
  abrieron; lo que no se comprobó del todo va marcado *(sin comprobar del
  todo)*.
- **Comprobado el 2026-10-27**, por dos agentes de investigación del agente
  de código que trabaja en el proyecto. Cada capacidad sale de una página
  leída; las URL concretas están en sus inventarios, y aquí se cita la página
  de cada área.
- **Se comparan capacidades, no se copian diseños.** `maha` sigue siendo un
  agente propio, construido a mano y pieza a pieza (AGENTS.md).

Leyenda de la columna **`maha`**: ✓ hecho (`v0.7.0`) · **hN** planeado en el
hito N · — no planeado. Columna **Propuesta**: dónde encajaría. Lo principal
(P1 a P15) está en DESIGN §14; el detalle por áreas es la lista de partida
de la spec de cada hito, y lo que queda abierto ("o", "mejora pequeña") se
decide en esa spec.

## Resumen: lo que se propone

Lo más importante, en una tabla. El detalle, por áreas, después.

| # | Propuesta | Por qué | Dónde |
|---|---|---|---|
| P1 | **Modo no interactivo completo:** `-p`, `-c`, `-r`, `--model`, salida JSON, entrada por stdin, códigos de salida, `--max-turns` y tope de coste | Los dos lo tienen; los evals y los scripts lo necesitan | Hito 8 (ya planeado en parte) |
| P2 | **Comandos de línea:** `maha models`, `maha sessions`, `maha stats` (coste acumulado) y `maha export` | Gestionar sin abrir la conversación | Hito 8 |
| P3 | **Variantes de razonamiento** (*effort*) y **modelo de respaldo** | Los dos las tienen; los proveedores las admiten | Hito 9 (el respaldo, hito 8) |
| P4 | **`/init`**, compatibilidad con `CLAUDE.md` e instrucciones extra | Crear y reutilizar las instrucciones de proyecto | Hito 10 |
| P5 | **Herramientas de flujo:** lista de tareas (*todo*) y pregunta estructurada al usuario | Los dos las tienen; mejoran tareas largas | Hito 10 |
| P6 | **`/compact`, `/context` y compactación automática** con lo que sobrevive | Ya en el plan; se concreta | Hito 11 |
| P7 | **Comandos personalizados** (`/nombre` con plantilla y argumentos) como parte de las skills | Claude Code los une a las skills; OpenCode los tiene aparte | Hito 13 |
| P8 | **Deshacer y puntos de control** (`/undo`, `/redo`, volver a un punto) | Los dos lo tienen; da confianza para dejar trabajar al agente | **Hito 12, nuevo** |
| P9 | **Modos y reglas de permisos:** modo plan, aceptar ediciones, reglas `allow`/`ask`/`deny` con patrones en la configuración, "siempre" que persiste por proyecto, detección de bucles | Los dos lo tienen; hoy solo hay "una vez" y "esta sesión" | Hito 15, junto al sandbox |
| P10 | **Agentes personalizados** (Markdown con modelo, herramientas y permisos), `@agente`, subagentes en segundo plano | Los dos lo tienen | Hito 16 |
| P11 | **Comandos en segundo plano** (un servidor de desarrollo, un `watch`) | Los dos lo tienen | Hito 16 |
| P12 | **MCP completo:** remoto con OAuth, *prompts* como comandos, recursos, activar y desactivar | Los dos lo tienen | Hito 17 |
| P13 | **Hooks:** acciones antes o después de una herramienta, de un turno, de compactar… | Claude Code tiene 33 eventos; OpenCode, eventos para plugins | **Hito 18, nuevo** |
| P14 | **Distribución:** instalación sencilla, `maha upgrade`, `maha doctor`, credenciales con `maha auth login` | Un producto para cualquier usuario | Hito 23 (ya decidido) |
| P15 | **Después de la 1.0:** LSP y formateadores, plugins y herramientas propias, servidor/API y SDK, ACP e IDE, GitHub Action, más APIs de modelo (Responses de OpenAI, Google), worktrees, tareas programadas, voz | Valiosos, pero no imprescindibles para la 1.0 | Versiones `v1.N` |

P8 y P13 entran como hitos nuevos (12 y 18): la 1.0 pasa del hito 21 al 23
y los tags `v0.N.0` siguientes se renumeran (DESIGN §14).

## 1. Interfaz y navegación

Fuentes: https://opencode.ai/docs/tui/, https://opencode.ai/docs/keybinds/,
https://code.claude.com/docs/en/interactive-mode.md,
https://code.claude.com/docs/en/keybindings.md.

Casi todo va al hito 21 (TUI completa, decisión del mantenedor del
2026-10-27).

| Capacidad | OpenCode | Claude Code | `maha` | Propuesta |
|---|---|---|---|---|
| Paleta de comandos que se filtra al escribir | `ctrl+p` | menú de `/` con filtro | — | h21 |
| `/` sugiere comandos | sí | sí, también a mitad del prompt | — | h21 |
| Ayuda de atajos | panel *which-key* | `?` con el prompt vacío | — | h21 |
| Atajos configurables y tecla líder | `ctrl+x`, `tui.json` | `keybindings.json`, acordes | — | h21 |
| `@fichero` para meter un fichero | búsqueda difusa | sí, con rangos de líneas | — | h21 |
| `!comando` de shell desde el prompt | sí | sí | — | h21 |
| Editor externo para escribir el mensaje | `/editor` | `ctrl+g` | — | h21 |
| Encolar o redirigir mientras trabaja | V2: Enter redirige | Enter encola | — | h21 |
| Historial de entrada y búsqueda | sí | `ctrl+r` | — | h21 |
| Visor de diferencias | V2 `/diff` | `/diff` | — | h21 |
| Línea de estado (modelo, contexto, coste) | barra lateral | *status line* configurable | — | h21 |
| Temas | `/themes`, propios | `/theme`, daltónicos | — | h21 |
| Ratón, desplazamiento, copiar | sí | sí, pantalla completa | — | h21 |
| Notificaciones al acabar o al preguntar | sí (opcional) | sí | — | h21 |
| Ver el razonamiento del modelo | `/thinking` | `alt+t` | — | h21 |
| Pegar imágenes | arrastrar | `ctrl+v` | — | h21 (con h20) |
| Modo vim al escribir | — | sí | — | después de la 1.0 |
| Accesibilidad (lector de pantalla) | — | `--ax-screen-reader` | — | h21 |
| Interfaz web o de escritorio | `opencode web`, app | app, web, móvil | — | fuera de alcance (ANALISIS §5) |

## 2. Comandos dentro de la conversación

Fuentes: https://opencode.ai/docs/tui/, https://code.claude.com/docs/en/commands.md.

| Capacidad | OpenCode | Claude Code | `maha` | Propuesta |
|---|---|---|---|---|
| Ayuda | `/help` | `/help` | ✓ `/help` | h21 la amplía |
| Salir | `/exit` | `/exit` | ✓ | — |
| Elegir modelo | `/models` (lista) | `/model` (selector) | ✓ `/model ID` | h21: selector |
| Sesiones: listar, retomar, borrar | `/sessions` | `/resume` | ✓ | — |
| Nueva sesión | `/new` | `/clear` | — | h8 o mejora pequeña |
| Renombrar sesión | sí | `/rename` | — | mejora pequeña |
| Exportar la conversación | `/export` (Markdown) | `/export` | — | h8 |
| Copiar la última respuesta | sí | `/copy` | — | h21 |
| Bifurcar la sesión | `--fork` | `/branch`, `/fork` | — | h8 o después |
| Compactar | `/compact` | `/compact` | — | h11 |
| Ver qué ocupa el contexto | — | `/context` | — | h11 |
| Crear `AGENTS.md`/`CLAUDE.md` | `/init` | `/init` | — | h10 |
| Memoria | — | `/memory` | — | h14 |
| Deshacer y rehacer | `/undo`, `/redo` | `/rewind` | — | h12 (P8, nuevo) |
| Coste y uso | `opencode stats` | `/usage` | ✓ `/trace` (por sesión) | h8: `stats` acumulado |
| Gestionar permisos | paleta (modo auto) | `/permissions` | — | h15 (P9) |
| Modo plan | Tab | `/plan`, `shift+tab` | — | h15 (P9) |
| Esfuerzo de razonamiento | `ctrl+t` (variantes) | `/effort` | — | h9 |
| MCP | — | `/mcp` | — | h17 |
| Skills y agentes | — | `/skills`, `/agents` | — | h13, h16 |
| Pregunta aparte que no entra en el historial | V2 `/btw` | `/btw` | — | después de la 1.0 |
| Cambiar de directorio | V2 `cd` | `/cd`, `/add-dir` | — | h15 |
| Diagnóstico de la instalación | `debug` | `/doctor` | — | h23 |
| Revisión de código, seguridad | — | `/code-review`, `/security-review` | — | h13 (skills incluidas) |
| Objetivo y bucle (`/goal`, `/loop`) | V2 | sí | — | después de la 1.0 |

## 3. Comandos personalizados

Fuentes: https://opencode.ai/docs/commands/, https://code.claude.com/docs/en/skills.md.

| Capacidad | OpenCode | Claude Code | `maha` | Propuesta |
|---|---|---|---|---|
| Un fichero Markdown = un comando `/nombre` | `commands/` | `skills/` (y `commands/` heredado) | — | h13 (P7) |
| Argumentos `$ARGUMENTS`, `$1` | sí | sí | — | h13 |
| Insertar la salida de un comando | `` !`cmd` `` | `` !`cmd` `` | — | h13, con permiso |
| Elegir modelo o agente por comando | sí | sí | — | h13 |
| Ejecutar como subagente | `subtask` | `context: fork` | — | h16 |
| *Prompts* de MCP como comandos | V2 | sí | — | h17 |

## 4. Línea de comandos y modo no interactivo

Fuentes: https://opencode.ai/docs/cli/, https://code.claude.com/docs/en/cli-reference.md,
https://code.claude.com/docs/en/headless.md.

| Capacidad | OpenCode | Claude Code | `maha` | Propuesta |
|---|---|---|---|---|
| Una instrucción y salir | `opencode run` | `claude -p` | — | h8 (P1) |
| Seguir o retomar al arrancar | `-c`, `-s` | `-c`, `-r` | — | h8 |
| Modelo y agente al arrancar | `-m`, `--agent` | `--model`, `--agent` | — | h8 (agente: h16) |
| Salida JSON / eventos en JSON | `--format json` | `--output-format json`, `stream-json` | — | h8 |
| Entrada por stdin | sí | sí | parcial (`maha < fichero`) | h8 |
| Tope de pasos y de coste | `steps` | `--max-turns`, `--max-budget-usd` | parcial (25 pasos fijos) | h8 |
| Permisos sin preguntar en scripts | `--auto` | `--permission-mode`, `--allowedTools` | — (deniega todo) | h8 y h15 |
| Listar modelos | `opencode models` | — | — | h8 (P2) |
| Sesiones desde la línea | `session list/delete` | `--resume` | — | h8 |
| Estadísticas de coste | `opencode stats` | `/usage`, `/insights` | — | h8 |
| Exportar e importar sesiones | `export`, `import` | `/export` | — | h8 |
| Iniciar sesión con un proveedor | `auth login` | `auth login` | — (variable de entorno) | h23 |
| Actualizar y desinstalar | `upgrade`, `uninstall` | `update`, `install` | — | h23 |
| Servidor HTTP con API | `serve` | — | — | después de la 1.0 |
| Protocolo para editores (ACP) | `opencode acp` | — | — | después de la 1.0 |

## 5. Configuración

Fuentes: https://opencode.ai/docs/config/, https://code.claude.com/docs/en/settings.md.

| Capacidad | OpenCode | Claude Code | `maha` | Propuesta |
|---|---|---|---|---|
| Usuario y proyecto | sí | usuario, proyecto, local | ✓ (TOML) | — |
| Configuración local no compartida | — | `settings.local.json` | — | h15 (con los permisos) |
| Variables de entorno en la configuración | `{env:VAR}` | — | — | mejora pequeña |
| Gestionada por la empresa | sí | sí | — | después de la 1.0 |
| Editar la configuración desde la conversación | paleta | `/config` | — | h21 |
| Catálogo de modelos propio | models.dev | — | ✓ (`models.toml`) | — |

## 6. Herramientas

Fuentes: https://opencode.ai/docs/tools/, https://code.claude.com/docs/en/tools-reference.md.

| Herramienta | OpenCode | Claude Code | `maha` | Propuesta |
|---|---|---|---|---|
| Leer, listar, buscar ficheros y texto | sí | sí | ✓ | — |
| Escribir y editar | sí | sí | ✓ | — |
| Parche de varios ficheros | `apply_patch` | — | — | h9 o después |
| Ejecutar comandos | `bash` | `Bash` | ✓ `run_command` | — |
| Comandos en segundo plano | V2 | `Monitor`, `ctrl+b` | — | h16 (P11) |
| Leer y buscar en la web | `webfetch`, `websearch` | `WebFetch`, `WebSearch` | — | h19 |
| Lista de tareas | `todowrite` | `TaskCreate`… | — | h10 (P5) |
| Pregunta estructurada al usuario | `question` | `AskUserQuestion` | — | h10 (P5) |
| Cargar una skill | `skill` | `Skill` | — | h13 |
| Lanzar un subagente | `task` | `Agent` | — | h16 |
| Modo plan | agente Plan | `EnterPlanMode` | — | h15 (P9) |
| Inteligencia de código (LSP) | `lsp` (experimental) | `LSP` | — | después de la 1.0 |
| Cuadernos Jupyter | — | `NotebookEdit` | — | después de la 1.0 |
| Herramientas propias del usuario | `tools/` | plugins | — | después de la 1.0 |
| Cargar herramientas bajo demanda | — | `ToolSearch` | — | h17 (muchas herramientas MCP) |

## 7. Permisos

Fuentes: https://opencode.ai/docs/permissions/,
https://code.claude.com/docs/en/permission-modes.md,
https://code.claude.com/docs/en/permissions.md *(sin comprobar del todo)*.

| Capacidad | OpenCode | Claude Code | `maha` | Propuesta |
|---|---|---|---|---|
| Preguntar antes de cada efecto | `ask` | modo manual | ✓ | — |
| "Una vez" / "esta sesión" / "no" | once, always, reject | sí | ✓ | — |
| "Siempre" que persiste por proyecto | V2 | `settings.local.json` | — | h15 (P9) |
| Reglas con patrones (`git *`, rutas) | sí | sí | — | h15 |
| Modos (plan, aceptar ediciones, automático) | Plan, `--auto` | 6 modos, `shift+tab` | — | h15 |
| Fuera del directorio de trabajo | `external_directory` | `/add-dir` | ✓ (pregunta) | — |
| Ficheros secretos | `.env` pregunta | rutas protegidas | ✓ | — |
| Detección de bucles (misma llamada repetida) | `doom_loop` | — | — | h15 |
| Confianza en una carpeta nueva | — | diálogo de confianza | — | h15 |
| Clasificador automático | — | modo `auto` | — | después de la 1.0 |

## 8. Agentes y subagentes

Fuentes: https://opencode.ai/docs/agents/, https://code.claude.com/docs/en/sub-agents.md.

| Capacidad | OpenCode | Claude Code | `maha` | Propuesta |
|---|---|---|---|---|
| Subagente con contexto propio | General, Explore | Explore, Plan, general | h16 | — |
| Agentes propios en Markdown | sí | sí | — | h16 (P10) |
| Llamarlos con `@agente` | sí | sí | — | h16 |
| Cambiar de agente principal | Tab | `--agent` | — | h16 |
| En segundo plano y en paralelo | experimental | sí | — | h16 |
| Profundidad máxima | `subagent_depth` | 3 niveles | — | h16 |
| Aislado en un *worktree* de git | V2 | `isolation: worktree` | — | después de la 1.0 |
| Equipos de agentes | — | experimental | — | después de la 1.0 |

## 9. Contexto, instrucciones y memoria

Fuentes: https://opencode.ai/docs/rules/, https://code.claude.com/docs/en/memory.md
*(sin comprobar del todo)*, https://code.claude.com/docs/en/context-window.md.

| Capacidad | OpenCode | Claude Code | `maha` | Propuesta |
|---|---|---|---|---|
| `AGENTS.md` del proyecto y del usuario | sí | lee `AGENTS.md` | h10 | — |
| Compatibilidad con `CLAUDE.md` | sí | propio | — | h10 (P4) |
| Instrucciones extra (rutas, URL) | `instructions` | `.claude/rules/` con rutas | — | h10 |
| `/init` | sí | sí | — | h10 |
| Compactación automática y manual | sí | sí | h11 | — |
| Qué sobrevive a la compactación | `prune` | lista documentada | — | h11 |
| Ver qué ocupa el contexto | — | `/context` | — | h11 |
| Caché del prompt del proveedor | V2 *warming* | documentada | — | h9 y h11 |
| Memoria entre sesiones | plugin de la comunidad | memoria automática | h14 | — |
| Skills | `SKILL.md` | `SKILL.md` | h13 | — |

## 10. Sesiones

Fuentes: https://opencode.ai/docs/tui/, https://code.claude.com/docs/en/sessions.md,
https://code.claude.com/docs/en/checkpointing.md.

| Capacidad | OpenCode | Claude Code | `maha` | Propuesta |
|---|---|---|---|---|
| Guardar, listar, retomar, borrar | sí | sí | ✓ | — |
| De cualquier directorio | — | `ctrl+a` en el selector | ✓ | — |
| Títulos automáticos | modelo pequeño | sí | parcial (primera línea) | h10 |
| Renombrar | sí | sí | — | mejora pequeña |
| Bifurcar | sí | sí | — | h8 o después |
| Exportar e importar | sí | exportar | — | h8 |
| Deshacer cambios en ficheros | `/undo` (git) | puntos de control | — | h12 (P8, nuevo) |
| Borrado automático de las antiguas | — | 30 días | — | h23 |
| Trazas por sesión | — | — | ✓ | — |

## 11. Modelos y proveedores

Fuentes: https://opencode.ai/docs/models/, https://opencode.ai/docs/providers/,
https://code.claude.com/docs/en/model-config.md *(sin comprobar del todo)*.

| Capacidad | OpenCode | Claude Code | `maha` | Propuesta |
|---|---|---|---|---|
| Formato de OpenAI (Chat Completions) | sí | — | ✓ | — |
| Formato de Anthropic | sí | propio | h9 | — |
| Responses de OpenAI y API de Google | sí | — | — | después de la 1.0 (decisión pendiente) |
| Proveedores compatibles propios | sí | pasarelas | ✓ (configuración) | — |
| Modelos locales (Ollama, LM Studio) | sí | — | ✓ (compatibles con OpenAI) | documentar en h23 |
| Esfuerzo o variantes de razonamiento | variantes | `/effort` | — | h9 (P3) |
| Modelo de respaldo | — | `--fallback-model` | — | h8 (P3) |
| Modelo pequeño para títulos | `small_model` | — | — | h10 |
| Iniciar sesión (OAuth, clave guardada) | `/connect` | `/login` | — | h23 |

## 12. MCP y conectores

Fuentes: https://opencode.ai/docs/mcp-servers/, https://code.claude.com/docs/en/mcp.md
*(sin comprobar del todo)*.

| Capacidad | OpenCode | Claude Code | `maha` | Propuesta |
|---|---|---|---|---|
| Servidores locales (stdio) | sí | sí | h17 | — |
| Remotos (HTTP) con OAuth | sí | sí | — | h17 (P12) |
| Activar y desactivar servidores | sí | `/mcp` | — | h17 |
| Recursos y *prompts* | V2 | sí | — | h17 |
| Herramientas bajo demanda | V2 Code Mode | *tool search* | — | h17 |
| Límite de lo que devuelve una herramienta | — | 25 000 tokens | — | h17 |

## 13. Extensibilidad

Fuentes: https://opencode.ai/docs/plugins/, https://opencode.ai/docs/server/,
https://code.claude.com/docs/en/hooks.md, https://code.claude.com/docs/en/plugins/overview.md.

| Capacidad | OpenCode | Claude Code | `maha` | Propuesta |
|---|---|---|---|---|
| Hooks antes y después de herramientas, turnos… | eventos de plugin | 33 eventos | — | h18 (P13, nuevo) |
| Plugins | JS/TS | plugins y *marketplaces* | — | después de la 1.0 |
| Herramientas propias | `tools/` | plugins | — | después de la 1.0 |
| Servidor con API y SDK | `serve`, SDK | Agent SDK | — | después de la 1.0 |

## 14. Integraciones

Fuentes: https://opencode.ai/docs/github/, https://opencode.ai/docs/ide/,
https://code.claude.com/docs/en/github-actions.md.

| Capacidad | OpenCode | Claude Code | `maha` | Propuesta |
|---|---|---|---|---|
| GitHub Action (`/opencode`, `@claude`) | sí | sí | — | después de la 1.0 |
| Extensión de VS Code / JetBrains | sí | sí | — | después de la 1.0 (vía ACP) |
| Navegador (Chrome) | — | sí | — | después de la 1.0 |
| Docker | imagen oficial | contenedor de desarrollo | — | h23 |

## 15. Coste, uso y observabilidad

Fuentes: https://opencode.ai/docs/cli/, https://code.claude.com/docs/en/costs.md,
https://code.claude.com/docs/en/monitoring-usage.md *(sin comprobar del todo)*.

| Capacidad | OpenCode | Claude Code | `maha` | Propuesta |
|---|---|---|---|---|
| Coste por turno y sesión | — (no documentado en V1) | `/usage` | ✓ | — |
| Coste acumulado por días, modelos | `stats` | `/usage`, `/insights` | — | h8 (P2) |
| Traza de cada sesión | — | — | ✓ | — |
| OpenTelemetry | V1 no soportado | sí (métricas, eventos, trazas) | h22 | — |
| Registro de diagnóstico | `opencode.log` | `--debug` | ✓ `maha.log` | — |

## 16. Seguridad y aislamiento

Fuentes: https://code.claude.com/docs/en/sandboxing.md *(sin comprobar del
todo)*, https://code.claude.com/docs/en/security.md.

| Capacidad | OpenCode | Claude Code | `maha` | Propuesta |
|---|---|---|---|---|
| Sandbox de comandos | (plugins de la comunidad) | bubblewrap / Seatbelt | h15 | — |
| Sin la clave en los comandos | — | — | ✓ | — |
| Detectar comandos que no puede analizar | — | sí | — | h15 |
| Credenciales en el llavero del sistema | `auth.json` | Keychain / `0600` | — | h23 |

## OpenCode 2: hacia dónde va

Fuente: https://opencode.ai/v2/docs/. Para tener en cuenta en los hitos que
tocan cada cosa, no como propuesta cerrada:
- un **servicio en segundo plano** compartido por todos los clientes;
- **redirigir al agente mientras trabaja** (Enter) o encolar;
- pestañas de sesión, sesiones fijadas, panel de terminal;
- "siempre" en los permisos, duradero y por proyecto; políticas de
  organización;
- compactación con puntos de control y la nativa del proveedor;
- *Code Mode*: el modelo escribe un script que llama a varias herramientas.

## Lo que decidió el mantenedor (2026-10-27)

Acepta todas las recomendaciones: P1 a P7 y P9 a P12 amplían sus hitos; P8
(deshacer) y P13 (hooks) son hitos nuevos, el 12 y el 18; P14 entra en la
1.0 (hito 23); P15 y las APIs de Responses y de Google, después de la 1.0.
"El objetivo es tener un programa completo, muy bueno y llamativo para el
usuario final."
