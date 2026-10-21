# M-Harness — Documento de Diseño

**Proyecto:** agente de terminal de propósito general, construido desde cero en
Python. Comando: `maha`.
**Fecha:** 19/10/2026
**Estado:** Diseño cerrado — base de la fase de código (§14).

El análisis del problema está en `docs/ANALISIS.md`. Este documento no lo
repite: decide cómo se construye.

---

## 1. Contexto y objetivo
M-Harness es un agente de terminal, en la línea de Claude Code u OpenCode,
construido pieza a pieza para que cada parte del arnés (bucle, herramientas,
permisos, contexto, memoria, subagentes…) se pueda estudiar por separado. Desde
fuera es un programa de terminal, `maha`: el usuario conversa con el agente, que
usa herramientas sobre el directorio de trabajo y pide aprobación antes de
cualquier efecto.

## 2. Requisitos consolidados
| Requisito (ANALISIS) | Decisión |
|---|---|
| Desde cero, sin frameworks de agentes (§7) | A mano lo que es del agente, librerías estándar para la fontanería y el estándar de la industria documentado al lado (§7.1) |
| Elegir proveedor y modelo (RF 3) | Tipos internos propios + un adaptador por formato de API (§5, §8) |
| Ejecución local (§7) | Monolito modular con arquitectura hexagonal (§3) |
| Streaming e interrupción (RF 1, RF 4) | Asíncrono de punta a punta con `asyncio` (§7) |
| Permisos (RF 6) | Dos niveles registrados (lectura, efecto) y lo prohibido sin registrar; aprobación a través de un puerto (§10) |
| Trazas (RF 17) | Trazas propias en local; exportador OpenTelemetry opcional (§11) |
| Evals (RF 18) | Batería propia con modo no interactivo y línea base registrada (§9) |
| Repositorio que documenta la construcción (§7) | `docs/guia/` con una nota por hito, cada una con su sección "En la industria"; PRs con explicación por fichero; `docs/MAPA.md` (§3, §15) |

**Fuera de alcance v1:** el de `docs/ANALISIS.md` §5.

**Dependencias externas:** un proveedor de modelos con formato OpenAI (OpenCode
Go u OpenCode Zen) desde el hito 2. Hasta entonces, y siempre en los tests, se
usa un modelo falso guionizado (§12).

## 3. Arquitectura general
M-Harness es un **monolito modular con arquitectura hexagonal** (puertos y
adaptadores): un solo programa, un solo proceso y un solo paquete, que se
ejecuta en la máquina del usuario.

**Por qué monolito.** Es un producto local, igual que Claude Code, Codex CLI u
OpenCode. Lo que queda fuera del proceso son el modelo (remoto), los servidores
MCP (subprocesos) y el sandbox (contenedor o aislamiento del sistema
operativo), pero el arnés en sí es uno.

**Por qué hexagonal.** Un agente es, sobre todo, un núcleo que habla con el
exterior: proveedores de modelos, herramientas, disco, terminal y servidores
MCP. La arquitectura hexagonal pone ese núcleo en el centro y cada contacto con
el exterior detrás de un puerto. Eso da tres ventajas:
- cambiar de proveedor es cambiar de adaptador;
- el bucle se prueba con fakes, sin red;
- una interfaz nueva (un servidor local, una app de escritorio) es solo un
  adaptador de entrada más.

**Descartado:**
- capas clásicas (UI → lógica → datos), que no separan bien los muchos
  "exteriores" de un agente;
- servicios separados, que no tienen sentido en un producto local de un solo
  usuario.

*En la industria:* también se llama "puertos y adaptadores" (Alistair
Cockburn). Sus parientes son Clean Architecture y Onion Architecture.

```
m-harness/
├── src/mharness/
│   ├── domain/            # Núcleo: tipos y reglas puras, sin E/S ni red
│   │   ├── messages.py    #   Message, bloques, ToolCall, ToolResult
│   │   ├── tools.py       #   ToolSpec, Permission
│   │   ├── events.py      #   ModelEvent, AgentEvent
│   │   ├── session.py
│   │   └── errors.py
│   ├── ports/             # Interfaces (typing.Protocol): lo que el núcleo necesita del exterior
│   │   ├── model.py       #   ModelClient, ModelCatalog
│   │   ├── tool.py        #   Tool
│   │   ├── approval.py    #   ApprovalGate
│   │   ├── sessions.py    #   SessionStore
│   │   ├── memory.py      #   MemoryStore
│   │   ├── skills.py      #   SkillSource
│   │   ├── sandbox.py     #   CommandRunner
│   │   └── tracing.py     #   TraceSink
│   ├── application/       # Casos de uso: orquestan el núcleo a través de los puertos
│   │   ├── agent_loop.py  #   el bucle agéntico
│   │   ├── tool_runner.py #   validar → permiso → ejecutar
│   │   ├── prompt.py      #   composición del system prompt
│   │   ├── context.py     #   conteo y compactación
│   │   └── subagents.py
│   ├── adapters/          # Implementaciones de los puertos: el contacto real con el exterior
│   │   ├── models/        #   openai_chat.py, anthropic.py
│   │   ├── tools/         #   filesystem.py, search.py, shell.py, web.py…
│   │   ├── mcp/
│   │   ├── storage/       #   sesiones (JSONL), memoria (SQLite)
│   │   ├── skills/
│   │   ├── sandbox/
│   │   ├── tracing/       #   jsonl_traces.py, otel.py
│   │   └── cli/           #   adaptador de entrada: terminal interactiva y modo no interactivo
│   ├── config.py          # carga y valida la configuración
│   └── bootstrap.py       # raíz de composición: el único sitio que conecta adaptadores y puertos
├── tests/
│   ├── unit/              # dominio y aplicación, con fakes
│   ├── adapters/          # cada adaptador contra respuestas HTTP simuladas o recursos temporales
│   ├── architecture/      # reglas de dependencia
│   └── fakes/             # FakeModelClient guionizado, FakeTool, FakeApproval…
├── evals/                 # batería de tareas, repos de prueba y líneas base
└── docs/                  # ANALISIS, DESIGN, ESTADO, MAPA, guia/, specs/…
```

El árbol muestra el destino: cada carpeta nace en el hito que la necesita
(§14). `docs/MAPA.md` describe lo que existe en cada momento y se actualiza en
el mismo PR que crea, mueve o borra ficheros.

**Reglas de dependencia (no negociables):**
- `domain` no importa nada del proyecto. Solo la biblioteca estándar y Pydantic.
- `ports` solo importa `domain`.
- `application` importa `domain` y `ports`, nunca `adapters`.
- Los adaptadores de salida implementan puertos. El adaptador de entrada
  (`cli`) llama a `application`. Ningún adaptador importa a otro.
- `bootstrap.py` es el único módulo que conoce todas las piezas.
- Las reglas se hacen cumplir con **import-linter** en el CI.

## 4. El núcleo: el bucle agéntico
El bucle repite cuatro pasos hasta que el modelo responde sin pedir
herramientas o se alcanza un límite:
1. llama al modelo con la conversación completa y las herramientas
   disponibles;
2. recibe texto y/o peticiones de herramientas;
3. ejecuta cada petición (validar → permiso → ejecutar);
4. añade los resultados a la conversación.

```
            ┌──────────────────────────────────────────────┐
            ▼                                              │
  mensajes + tools ──► ModelClient ──► respuesta ──► ¿pide tools? ──no──► fin del turno
                                                       │ sí
                                                       ▼
                                   validar ─► permiso ─► ejecutar ─► resultado
```

| Pieza (ANALISIS §5) | Dónde se engancha |
|---|---|
| 1 Cliente multiproveedor | La llamada al modelo |
| 3 Herramientas · 4 Permisos · 12 Sandbox | La ejecución de cada petición |
| 5 System prompt · 8 Skills · 9 Memoria | El principio de la conversación y la lista de herramientas |
| 6 Historial | Persistir la conversación |
| 7 Contexto | Antes de cada llamada: si no cabe, se compacta |
| 10 MCP | Más herramientas, ejecutadas por un servidor externo |
| 11 Subagentes | Una herramienta que lanza otro bucle con su propia conversación |
| 13 Multimodal · 14 Web | Más tipos de contenido y más herramientas |
| 15 Trazas | Un evento emitido en cada paso |
| 16 Evals | El bucle ejecutado sobre tareas conocidas |
| 17 Interfaz | Muestra los eventos y responde a las aprobaciones |

Los límites (pasos, tokens, tiempo) son código, no prompt. El bucle es
asíncrono: el streaming, la cancelación con Ctrl+C y la ejecución en paralelo
de herramientas y subagentes dependen de ello.

## 5. Contrato de datos
Los tipos internos son modelos Pydantic definidos en `domain`. El bucle solo
habla en estos tipos; cada adaptador traduce entre ellos y el formato de su
proveedor.

```python
# Bloques de contenido de un mensaje
TextBlock(text)
ImageBlock(media_type, data)
ReasoningBlock(text, signature)          # razonamiento del modelo, si lo devuelve
ToolCallBlock(id, name, arguments: dict)
ToolResultBlock(call_id, content: list[TextBlock | ImageBlock], is_error)

Message(role: "user" | "assistant" | "tool", blocks: list[Block])

# Petición al modelo
ModelRequest(model, system, messages, tools: list[ToolSpec], max_tokens)
ToolSpec(name, description, input_schema)       # JSON Schema generado por Pydantic

# Respuesta del modelo, en streaming             (adaptador → bucle)
ModelEvent = TextDelta | ReasoningDelta | ToolCallDelta | MessageEnd(stop_reason, usage, model)
# (Corregido el 20/10/2026, spec del hito 3, §1.4: MessageEnd lleva `model`, que
#  ModelResponse exige y solo llega en los trozos. El hito 3 solo implementa
#  TextDelta y MessageEnd.)
Usage(input_tokens, output_tokens, cache_read_tokens, cache_write_tokens)

# Lo que cuenta el núcleo                        (bucle → interfaz y trazas)
AgentEvent = TurnStarted | TextDelta | ToolCallProposed | ApprovalRequested
           | ToolFinished(result, duration) | ModelCallFinished(usage, cost)
           | TurnFinished | AgentError

# Herramientas
Permission = READ | EFFECT                      # lo prohibido no se registra
Tool: name, description, Params (modelo Pydantic), permission,
      async run(params) -> ToolResultBlock

# Sesión
Session(id, created_at, cwd, model, messages, usage)
```

**Decisiones del contrato:**
- **Mensajes hechos de bloques**, al estilo de Anthropic. Un mensaje puede
  mezclar texto, razonamiento y llamadas a herramientas. El adaptador de OpenAI
  los aplana a su formato. Hacerlo al revés (partir del formato de OpenAI)
  perdería información al adaptar a Anthropic.
- **El system prompt no es un mensaje**: va aparte en `ModelRequest`, y cada
  adaptador lo coloca donde lo espera su API.
- **Dos flujos de eventos**: `ModelEvent` (del adaptador al bucle) y
  `AgentEvent` (del bucle a la interfaz y a las trazas). La interfaz no sabe qué
  proveedor hay detrás, y el bucle no sabe si le está mirando una terminal o
  una eval.
- **Pydantic dentro del dominio.** Es una excepción consciente al dominio sin
  dependencias: da serialización de sesiones y trazas, y validación, sin
  código duplicado.

## 6. Integraciones
| Puerto | Qué ofrece | Implementaciones (real · falsa) |
|---|---|---|
| `ModelClient` | `stream(ModelRequest)` → eventos `ModelEvent` asíncronos; `complete(ModelRequest)` → `ModelResponse` entera. *(Corregido el 21/10/2026, spec del hito 3, §1.2: `complete()` se queda junto a `stream()`, por decisión del mantenedor.)* | `OpenAIChatClient` (hito 2), `AnthropicClient` (hito 9) · `FakeModelClient` guionizado |
| `ModelCatalog` | Ventana de contexto, precios y capacidades de cada modelo | Fichero TOML propio (formato inspirado en models.dev) · catálogo en memoria |
| `Tool` | Especificación y ejecución de una herramienta | Ficheros, búsqueda, terminal, web, memoria, subagente, herramientas MCP · `FakeTool` |
| `ApprovalGate` | Decide sobre cada llamada con efecto: una vez, toda la sesión o denegar | Aviso en la terminal · política automática (evals) · `FakeApproval` |
| `SessionStore` | Guardar, cargar, listar y borrar sesiones | JSONL en disco · en memoria |
| `MemoryStore` | Guardar, buscar y borrar recuerdos | SQLite con FTS5 · en memoria |
| `SkillSource` | Listar y cargar skills | Carpetas con `SKILL.md` · en memoria |
| `CommandRunner` | Ejecutar un comando con directorio, entorno y tiempo límite | Proceso local · proceso aislado (hito 14) · `FakeRunner` |
| `TraceSink` | Recibir cada `AgentEvent` | JSONL en disco · exportador OpenTelemetry (hito 20) · lista en memoria |

## 7. Stack
| Capa | Elección | Por qué (y desviación del stack por defecto) |
|---|---|---|
| Lenguaje | Python ≥ 3.14. Desarrollo en 3.14; CI en 3.14 y 3.15 | 3.15.0 salió el 9/10/2026: se prueba en CI, pero no se exige hasta que el ecosistema lo haya absorbido |
| Entorno y dependencias | uv, con lockfile | Stack por defecto |
| Concurrencia | `asyncio` | Streaming, cancelación y paralelismo |
| Transporte HTTP | httpx (asíncrono), directo | Se ve el JSON exacto que viaja. En la industria se usan los SDK oficiales o LiteLLM (§7.1) |
| Validación y esquemas | Pydantic v2 | Herramientas, JSON Schema para el modelo, configuración, tipos del dominio |
| Configuración | TOML (`tomllib`) validado con Pydantic. Usuario: `~/.config/maha/config.toml`; proyecto: `.maha/config.toml` | Biblioteca estándar. La configuración del proyecto prevalece sobre la del usuario, pero solo puede elegir proveedor y modelo: los proveedores (URL y variable de la clave) solo se declaran en la del usuario. *(Corregido el 20/10/2026, spec del hito 2, §1.10: un repositorio ajeno podría desviar la clave del usuario a otro servidor.)* |
| Credenciales | Variables de entorno (por ejemplo, `OPENCODE_API_KEY`). En desarrollo, `.env` cargado con `uv run --env-file .env` | `maha` nunca lee un `.env` por su cuenta, para no cargar secretos de los proyectos donde trabaja |
| Interfaz de terminal | Rich (pintar) + prompt_toolkit (entrada) | Fontanería estándar. Textual queda como opción si algún día se quiere una TUI completa |
| Argumentos de línea de comandos | `argparse` | Biblioteca estándar; bastan unas pocas opciones |
| Persistencia | JSONL (sesiones, trazas) y SQLite (memoria) en `~/.local/share/maha/` | Sin servidor: es un producto local (XDG) |
| Calidad | ruff (lint y formato), mypy estricto, pytest + pytest-asyncio, respx (simular httpx), import-linter | Stack por defecto + lo propio del proyecto |
| Secretos | gitleaks en pre-commit y en CI; push protection de GitHub | Repositorio público |
| CI | GitHub Actions | Stack por defecto |
| Agentes | **Ninguno** (bucle propio) | *Desviación:* el stack por defecto propone LangGraph. Aquí el bucle es lo que se quiere construir |
| Observabilidad LLM | Trazas propias; OpenTelemetry opcional | *Desviación:* el stack por defecto propone Langfuse Cloud. Aquí las trazas son una pieza que se construye, y Langfuse puede recibirlas por OpenTelemetry sin ser una dependencia |
| Base de datos | **Ninguna** (ficheros y SQLite) | *Desviación:* el stack por defecto propone PostgreSQL. Producto local de un solo usuario |
| Empaquetado | Paquete Python: distribución `m-harness`, módulo `mharness`, comando `maha` | *Desviación:* el stack por defecto propone Docker. Es una herramienta de terminal que se instala con `uv tool install` |
| Licencia | MIT | |

*Versiones: Python comprobado en python.org el 19/10/2026. Las versiones exactas
de las librerías las fija el lockfile en el hito 1, comprobadas ese día.*

### 7.1 Principio: a mano, fontanería estándar y la industria al lado
- **A mano**, lo que es del agente: el bucle, los adaptadores de modelos, los
  permisos, el contexto, la memoria y los subagentes.
- **Librería estándar**, lo que es fontanería: interfaz de terminal,
  validación, HTTP.
- **Cada pieza documenta qué se usa en la industria** (nombre, qué hace, cuándo
  se elegiría): en esta tabla, en la sección "En la industria" de su nota de
  `docs/guia/` y en su spec.

| # | Pieza | M-Harness | En la industria |
|---|---|---|---|
| 1 | Cliente de modelos | httpx + adaptadores propios | SDKs oficiales (`openai`, `anthropic`, `google-genai`); LiteLLM (una interfaz para más de 100 proveedores); AI SDK de Vercel (TypeScript, lo usa OpenCode); pasarelas OpenRouter, LiteLLM Proxy, Portkey |
| — | Catálogo de modelos | Fichero propio | models.dev (base de datos abierta de modelos, precios y límites, del equipo de OpenCode) |
| 2 | Bucle agéntico | Propio | OpenAI Agents SDK, Claude Agent SDK, Pydantic AI, LangGraph, smolagents, Google ADK. Claude Code, Codex CLI y OpenCode escriben el suyo |
| 3 | Herramientas | Pydantic → JSON Schema | Igual en Python (Pydantic o decoradores `@tool`); Zod en TypeScript |
| 4 | Permisos | Propio | Sin estándar: reglas allow/ask/deny (Claude Code), modos de aprobación + sandbox (Codex); *human-in-the-loop* en los frameworks |
| 5 | System prompt | Plantillas propias | Jinja2; prompts versionados en Langfuse o LangSmith; `AGENTS.md` como instrucciones de proyecto |
| 6 | Historial | JSONL propio | JSONL por sesión (Claude Code); checkpointers de LangGraph; Sessions del OpenAI Agents SDK |
| 7 | Contexto | Conteo y compactación propios | tiktoken; endpoints de conteo de los proveedores; compactación por resumen (auto-compact de Claude Code); compactación en la API de algunos proveedores |
| 8 | Skills | Cargador propio, formato Agent Skills | Agent Skills (`SKILL.md`), estándar abierto publicado por Anthropic en agentskills.io (diciembre de 2025) |
| 9 | Memoria | SQLite propia | Mem0, Letta (antes MemGPT), Zep; bases vectoriales sqlite-vec, pgvector, Chroma |
| 10 | MCP | Se decide en su hito | SDK oficial de MCP (`mcp`) |
| 11 | Subagentes | Herramienta que lanza otro bucle | Agente como herramienta y handoffs (OpenAI Agents SDK); supervisor (LangGraph); subagentes del Claude Agent SDK |
| 12 | Sandbox | Se decide en su hito | Docker/Podman; bubblewrap (Linux) y Seatbelt (macOS), usados por Claude Code; Landlock + seccomp (Codex); E2B, Modal, Daytona |
| 13 | Multimodal | Se decide en su hito | Envío nativo de PDF o imagen al modelo; pypdf, PyMuPDF |
| 14 | Web | Se decide en su hito | Brave Search, Tavily, Exa; búsqueda nativa de algunos proveedores; trafilatura, markdownify; Jina Reader |
| 15 | Trazas | Eventos propios en local | OpenTelemetry (convenciones GenAI); Langfuse, LangSmith, Arize Phoenix, Helicone; OpenLLMetry, OpenLIT |
| 16 | Evals | Runner propio | Inspect AI, promptfoo, DeepEval, Braintrust; benchmarks SWE-bench, Terminal-Bench |
| 17 | Interfaz | Rich + prompt_toolkit | Rich, prompt_toolkit, Textual; Typer, Click |
| — | Tests de adaptadores HTTP | respx | VCR.py y pytest-recording (graban y reproducen respuestas reales) |

*Nombres y referencias comprobados el 19/10/2026.*

## 8. Modelos, prompts y skills
- **Agente o pipeline:** agente. El modelo decide qué herramientas usar y en
  qué orden. Lo determinista (límites, permisos, persistencia, ejecución) es
  código.
- **Modelos:** detrás del puerto `ModelClient`, con un adaptador por formato de
  API:
  - primero el compatible con OpenAI (hito 2), que cubre OpenCode Go/Zen,
    OpenRouter, Ollama, LiteLLM Proxy y otros;
  - después el de Anthropic (hito 9).

  Proveedor y modelo van en configuración y se pueden cambiar dentro de una
  sesión. El catálogo da la ventana de contexto, el precio y las capacidades de
  cada modelo.
- **Identificación ante el proveedor:** `maha` se identifica con su propio
  user-agent y un identificador de sesión estable, como pide OpenCode Go a los
  clientes de terceros.
- **Herramientas:** tipadas con Pydantic, con mínimo privilegio. Crecen por
  hitos: solo lectura (hito 4) → efecto (5) → memoria (13) → subagentes (15) →
  MCP (16) → web (17).
- **System prompt:** composición por capas (base + entorno + `AGENTS.md` del
  proyecto + skills + memoria), con plantillas versionadas en el repositorio y
  evaluadas como código (hito 10).
- **Skills:** formato Agent Skills (`SKILL.md`). El índice va en el prompt y el
  contenido se carga bajo demanda (hito 12).
- **Supervisión:** toda herramienta con efecto pide aprobación. "Aprobar para
  toda la sesión" es la única forma de autonomía; no hay modo sin aprobaciones
  en v1.

## 9. Evals
- **Batería:** tareas genéricas en `evals/tasks/`. Cada tarea define un repo de
  prueba (en `evals/fixtures/`), una instrucción y una comprobación automática:
  un comando que tiene que terminar bien, o un fichero con un contenido
  esperado.
  - Tamaño inicial: 10 tareas (hito 8). Objetivo: 30 o más al cerrar v1.
  - Un 20 % se reserva como conjunto de validación y no se mira al ajustar
    prompts.
  - Solo datos inventados: el repositorio es público.

| Métrica | Cómo | Componente |
|---|---|---|
| Tasa de éxito | Tareas cuya comprobación pasa | Agente completo |
| Pasos | Llamadas al modelo por tarea | Bucle, prompt |
| Tokens y coste | Suma de `Usage` por tarea, con precios del catálogo | Contexto, memoria |
| Tiempo | Duración por tarea | Agente completo |

- **Ejecución:** `maha eval`, en local y con llamadas reales. Nunca en el CI de
  cada push.
- **Línea base:** cada ejecución de referencia se guarda en `evals/baselines/`
  con fecha y modelo.
- **Puerta:** todo cambio en prompts, bucle, herramientas, contexto o memoria
  se evalúa contra la última línea base antes del merge, y el resultado se
  anota en la spec.

## 10. Seguridad y datos sensibles
- **Credenciales:** solo en variables de entorno; en desarrollo, en `.env`
  fuera de git, con `.env.example` en el repositorio.
- **Permisos:**
  - `READ` se ejecuta sin preguntar;
  - `EFFECT` pide aprobación (una vez, toda la sesión o denegar);
  - lo que no está registrado no existe para el modelo.
- **Perímetro:** las herramientas de ficheros trabajan dentro del directorio
  de trabajo. Fuera de él, incluso leer pide aprobación.
- **Ficheros secretos:** `.env`, claves privadas, `~/.ssh`, credenciales de la
  nube y similares quedan denegados salvo aprobación explícita, para que su
  contenido no acabe en el modelo.
- **Terminal:** cada comando es `EFFECT`. Desde el hito 14 corre además en un
  entorno aislado.
- **Entrada no confiable:** los resultados de herramientas, webs, MCP y
  subagentes se delimitan en el prompt y nunca cambian permisos. La defensa
  real es el permiso en código; el prompt solo avisa.
- **Subagentes:** heredan como máximo los permisos del agente padre. Sus
  aprobaciones vuelven al usuario.
- **MCP:** sus herramientas son `EFFECT` por defecto, salvo que el usuario las
  declare `READ` en la configuración.
- **Trazas:** los valores de credenciales conocidas y los patrones de claves se
  enmascaran antes de escribir.
- **Repositorio público:**
  - gitleaks en pre-commit y en CI;
  - push protection de GitHub;
  - fixtures con datos inventados;
  - nada de sesiones, trazas ni memoria en git.

## 11. Observabilidad
- **Trazas:** `~/.local/share/maha/traces/<sesión>.jsonl`, con un `AgentEvent`
  por línea, marca de tiempo, uso de tokens y coste. Nunca en el repositorio.
- **Registro de la aplicación:** módulo `logging` de la biblioteca estándar, en
  `~/.local/state/maha/maha.log`. Solo errores y diagnóstico, nunca contenido
  de conversaciones.
- **En la interfaz:** modelo activo, tokens del contexto y coste de la sesión,
  siempre visibles.
- **Exportador OpenTelemetry (hito 20, opcional):** permite enviar las trazas a
  Langfuse (que las acepta en `/api/public/otel`), Phoenix u otra plataforma,
  sin que ninguna sea una dependencia.

## 12. Tests y CI
- **Unitarios:** dominio y aplicación con fakes. El bucle se prueba con
  `FakeModelClient`, que devuelve respuestas guionizadas (texto, peticiones de
  herramientas, errores): deterministas y sin red.
- **Adaptadores:**
  - los de modelos, con respx, contra respuestas HTTP de ejemplo guardadas en
    `tests/fixtures/` (sin claves);
  - los de herramientas y almacenamiento, sobre directorios temporales.
- **Arquitectura:** import-linter verifica las reglas de dependencia (§3).
- **No se prueba con tests:** la calidad de las respuestas del modelo, que es
  cosa de las evals (§9).
- **CI** (GitHub Actions, en cada PR y en cada push a `main`, con Python 3.14
  y 3.15). *(Corregido el 19/10/2026, spec del hito 1, §1.11: antes decía "en
  cada push y PR". Todo entra por PR, así que cubre lo mismo sin duplicar
  ejecuciones.)*
  - `ruff check`, `ruff format --check`;
  - `mypy`;
  - `lint-imports`;
  - `pytest`;
  - gitleaks.

  **Sin llamadas reales a servicios externos.**
- **Release** (GitHub Actions, al hacer push de un tag `v*`): crea la GitHub
  Release con sus notas. Nace en el hito 1, junto con el CI.
- **Hábito:** cada fallo se convierte en un test antes de arreglarse.

## 13. Distribución
Es un producto local: no hay servidor que desplegar. La fase de despliegue del
método se convierte aquí en distribución.
- **Desde el hito 1:** `uv tool install git+https://github.com/ManexMartikorena/m-harness`
  instala el comando `maha` en cualquier máquina con uv.
- **Cada hito:** tag anotado `v0.N.0`. Su push dispara el workflow que crea la
  GitHub Release con sus notas (§12).
- **Cuando el proyecto esté maduro** (fuera de alcance v1): publicación en PyPI
  con *trusted publishing* desde GitHub Actions y documentación de usuario. Se
  documentará en `docs/DISTRIBUCION.md`.

## 14. Orden de construcción (plan de la fase de código)
Los hitos siguen las dependencias entre piezas, y antes van los riesgos que
pueden matar el proyecto:
- conectar con un proveedor real con cliente propio (hito 2);
- que el bucle funcione (hito 4);
- dejar de ajustar a ojo (hito 8).

Cada hito es pequeño, deja `maha` funcionando, tiene su spec en
`docs/specs/hito-N-<slug>.md`, su nota en `docs/guia/` y su tag `v0.N.0`.

1. **Esqueleto.** Estructura hexagonal vacía, `pyproject.toml` con uv, ruff,
   mypy, pytest, import-linter, pre-commit con gitleaks, CI y `maha --version`.
   Guía: la arquitectura. *(Mata el riesgo de empezar sin base profesional: CI
   en verde desde el primer día.)*
2. **Primera conversación.** Tipos del dominio, puerto `ModelClient`, adaptador
   compatible con OpenAI (sin streaming), configuración (proveedor, modelo,
   clave), conversación mínima en la terminal y `FakeModelClient`. Guía: qué es
   una llamada a un LLM y por qué el modelo no recuerda. *(Mata el riesgo de no
   poder hablar con un proveedor real con un cliente propio.)*
3. **Streaming.** Eventos del servidor (SSE), `ModelEvent`, texto que aparece a
   medida que llega, cancelación con Ctrl+C. Guía: streaming.
4. **Tool calling y bucle agéntico.** Puerto `Tool`, esquemas con Pydantic,
   herramientas de solo lectura (leer fichero, listar, glob, grep), bucle con
   límite de pasos, `AgentEvent` y la terminal mostrando cada llamada. Guía:
   tool calling y el bucle. *(Mata el riesgo central: que el núcleo funcione.)*
5. **Permisos y herramientas con efecto.** Niveles, `ApprovalGate` en la
   terminal, escribir y editar ficheros, terminal con aprobación, perímetro del
   directorio y ficheros secretos. Guía: permisos. *(Primer agente de código
   usable: desde aquí `maha` puede trabajar en su propio repo.)*
6. **Sesiones e historial.** `SessionStore` en JSONL; listar, reanudar y borrar;
   comandos `/sessions`, `/resume` y `/model`. Guía: historial.
7. **Trazas y coste.** `TraceSink` en JSONL, catálogo de modelos, coste por
   llamada y por sesión, comando para ver una traza. Guía: observabilidad.
8. **Evals y modo no interactivo.** `maha -p "<instrucción>"`, batería inicial
   de 10 tareas, `maha eval` y primera línea base. Guía: cómo se evalúa un
   agente. *(Mata el riesgo de ajustar a ojo.)*
9. **Adaptador de Anthropic.** Segundo formato de API; evals comparando
   proveedores. Guía: en qué se diferencian los formatos.
10. **System prompt por capas.** Base, entorno, `AGENTS.md` del proyecto y
    plantillas versionadas, medido con evals. Guía: el system prompt.
11. **Gestión del contexto.** Conteo, umbral y compactación por resumen. Guía:
    la ventana de contexto.
12. **Skills.** Formato Agent Skills, índice en el prompt y carga bajo demanda.
    Guía: skills.
13. **Memoria persistente.** SQLite con FTS5, herramientas para guardar, buscar
    y borrar, y medición del ahorro de tokens con evals. Guía: memoria.
14. **Sandbox.** `CommandRunner` aislado (la tecnología se decide en su spec).
    Guía: aislamiento.
15. **Subagentes.** Herramienta que lanza un agente hijo con contexto limpio,
    herramientas acotadas y límites propios, con ejecución en paralelo. Guía:
    subagentes.
16. **MCP.** Cliente de servidores MCP; sus herramientas entran en el bucle con
    el sistema de permisos. Guía: MCP.
17. **Web.** Buscar y leer páginas. Guía: el agente y la web.
18. **Multimodal.** Imágenes y PDFs. Guía: entrada multimodal.
19. **Interfaz completa.** Markdown renderizado, barra de estado (modelo,
    tokens, coste), historial de entrada y atajos. Guía: la interfaz.
20. **Exportador OpenTelemetry.** Opcional; probado con Langfuse. Guía:
    OpenTelemetry.
21. **Versión 1.0.** README de uso, índice de la guía, batería de evals completa
    y revisión de los criterios de éxito del análisis. Con él, **`v1.0.0`**.

Después, fase de mantenimiento y mejora continua (`AGENTS.md`).

## 15. Flujo de trabajo en GitHub (adaptación del método)
El método integra las ramas con fast-forward en local. Este proyecto trabaja con
PRs en un repositorio público, y eso exige estas adaptaciones, que se trasladan
a `AGENTS.md`:

0. **Muchos commits pequeños.** Un commit por cada cosa pequeña (un tipo, una
   función, un adaptador, un test), cada uno en verde. Todo entra en `main` por
   PR, también los ajustes menores de documentación.

1. **La spec va en su propio PR.** Se abre un PR solo de documentación con la
   spec en estado PROPUESTA. Integrarlo es la aprobación, y la spec pasa a
   APROBADA. Después se abren el PR o los PRs de implementación.
2. **Integración con merge commit.** Conserva los commits pequeños y sus
   hashes, y agrupa cada PR en el historial. Se descartan *squash*, porque borra
   la evolución, y *rebase and merge*, porque cambia los hashes que citan los
   documentos.
3. **Push y PRs.** El agente commitea en la rama y nunca hace push por su
   cuenta. El push y la apertura del PR (con `gh pr create`) los hace el
   mantenedor, o el agente cuando el mantenedor se lo pide en esa sesión. Cada
   PR usa la plantilla `.github/pull_request_template.md`, que obliga a
   explicar qué hace cada fichero nuevo o cambiado y por qué. Un PR que no se
   puede revisar de una sentada se parte.
4. **Explicar al mantenedor.** Todo agente de código explica cada cosa que
   hace, corto y directo: qué, por qué, dónde y cómo se hace en la industria
   (`AGENTS.md`, "Explicar al mantenedor").
5. **Ramas conservadas.** Las ramas integradas no se borran en GitHub: quedan
   como registro visible de cada paso de la construcción. No se reutilizan.
   En local sí se borran.

**Ajustes de GitHub que se hacen una vez** (anotados en
`docs/PUESTA_EN_MARCHA.md`):
- solo merge commit habilitado, con el título y la descripción del PR como
  mensaje;
- las ramas integradas se conservan (sin borrado automático);
- `main` protegida con un ruleset: solo por PR, solo merge commit,
  conversaciones resueltas, sin force push ni borrado. Desde el hito 1, además,
  con el CI en verde;
- tags `v*` protegidos: no se mueven ni se borran;
- escaneo de secretos con push protection, alertas de Dependabot y reporte
  privado de vulnerabilidades.

---

## Registro de decisiones de la fase 2
- **19/10/2026.** Transporte con httpx directo (D1); primero el adaptador de
  OpenAI y después el de Anthropic (D2); trazas propias y OpenTelemetry
  opcional (D3); Pydantic (D4); `docs/guia/` con "En la industria" en cada
  nota (D5).
- **19/10/2026.** Principio: a mano lo que es del agente, fontanería estándar y
  la industria documentada al lado.
- **19/10/2026.** Monolito modular con arquitectura hexagonal; árbol, reglas de
  dependencia y contrato de datos.
- **19/10/2026.** Asíncrono con `asyncio` (D6). Pydantic dentro del dominio
  (D7, recomendación aceptada sin objeción). Comando `maha`, módulo `mharness`,
  distribución `m-harness` (D8).
- **19/10/2026.** Aprobados: spec en su propio PR (D9), integración con merge
  commit (D10), muchos commits pequeños y explicaciones al mantenedor (§15);
  CI y release con GitHub Actions (§12); plan de hitos (§14). **Diseño
  cerrado.**
- **19/10/2026.** Las ramas integradas se conservan en GitHub como registro
  visible (§15, punto 5). `main` y los tags `v*` se protegen con rulesets.

---

*Cualquier cambio de alcance, durante el código o en mantenimiento, se refleja
aquí antes de implementarse, anotado en el sitio con fecha y spec.*
