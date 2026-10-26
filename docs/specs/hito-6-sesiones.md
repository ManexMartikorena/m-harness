Estado: PROPUESTA (2026-10-26; ajustada tras `v0.5.2` y con la duda 2
cambiada por el mantenedor) → APROBADA (2026-10-26, por el humano, con el
cambio de la duda 2)

# Spec — Hito 6: Sesiones e historial

Referencias: `docs/DESIGN.md` §3 (árbol), §5 (`Session`), §6
(`SessionStore`), §7 (persistencia en `~/.local/share/maha/`), §10 (datos
sensibles) y §14 (hito 6); `docs/ANALISIS.md` §5 (pieza 6) y §6 (RF 3 y
RF 7); spec del hito 3 (§1.6, la respuesta cortada); spec del hito 5 (§0,
las aprobaciones mueren con el proceso); `AGENTS.md`.

## 0. Alcance

**El problema.** Al salir de `maha` se pierde la conversación: no se puede
retomar mañana lo que se dejó a medias. Además, una respuesta cortada con
Ctrl+C se queda en pantalla, pero el modelo no la recuerda (spec 3, §1.6), y
el modelo no se puede cambiar sin salir.

**Lo que hace este cambio.** Cada conversación se guarda sola en disco, turno
a turno. Desde la terminal se listan, se retoman y se borran, y se cambia de
modelo:

```
> /sessions
  * 20261026-091502-3fa2  hoy 09:15   12 mensajes  ~/proyecto  arregla el test de config
    20261025-174233-b01c  ayer 17:42   4 mensajes  ~/web       explícame el router
> /resume 20261025-174233-b01c
  [resumed 20261025-174233-b01c · 4 messages · glm-5.3-flash]
  [this session was in ~/web; tools work in ~/proyecto]
> /model kimi-k3
  [model: kimi-k3]
```

Dentro de alcance:
- Tipos de la sesión y su registro en disco (§1.2, §1.3).
- Puerto `SessionStore` y su adaptador JSONL (§1.4, §1.5).
- La conversación se guarda sola, al terminar cada turno (§1.6).
- La respuesta cortada con Ctrl+C se guarda, marcada (§1.7).
- `/sessions`, `/resume`, `/delete`, `/model` y `/help` (§1.8).
- Al retomar, las aprobaciones empiezan de cero (§1.9).
- Nota 06 de la guía y docs al día.

**Fuera de alcance** (y por qué):
- Retomar al arrancar (`maha --continue`, `maha --resume ID`): el hito 8
  trae las opciones de línea de comandos (`maha -p`). Aquí se retoma con
  `/resume` dentro de `maha`.
- Cambiar de proveedor dentro de una sesión: necesita otro cliente y otra
  clave; `/model` cambia el modelo del proveedor actual. Cambiar de
  proveedor es reiniciar `maha` con otra configuración.
- Coste por sesión: hito 7 (catálogo y precios). Aquí se guardan los tokens
  de cada turno, para que el hito 7 los tenga.
- Buscar dentro de las sesiones, exportarlas o ponerles nombre: sin hito.
- Recordar aprobaciones entre ejecuciones: no se hace (§1.9).
- Guardar la respuesta parcial cuando falla el modelo a mitad (no Ctrl+C):
  se repite el turno, como hoy (§1.7).

## 1. Decisiones de fondo

### 1.1 Hechos comprobados

Todos el 2026-10-26 por el agente.

- **XDG Base Directory**
  (https://specifications.freedesktop.org/basedir-spec/latest/): si
  `XDG_DATA_HOME` no está o está vacía, se usa `$HOME/.local/share`; una
  ruta relativa en esa variable se ignora. Es la misma regla que ya sigue
  `config.user_config_path()` con `XDG_CONFIG_HOME`.
- **Python 3.14** (https://docs.python.org/3.14/library/fcntl.html):
  `fcntl.flock(fd, operation)` bloquea un fichero abierto (flock(2));
  `LOCK_EX | LOCK_NB` falla en el acto si otro proceso lo tiene. El bloqueo
  se suelta solo al cerrar el descriptor o al morir el proceso.
- **`os.O_APPEND`** (https://docs.python.org/3.14/library/os.html y
  open(2)): cada `write` va al final del fichero.
- **Claude Code** guarda cada sesión como un JSONL por carpeta de proyecto
  (`~/.claude/projects/<carpeta>/<id>.jsonl`), observado en el puesto del
  agente.
- **Prueba local** (Python 3.14.4, WSL): `fcntl.LOCK_EX | fcntl.LOCK_NB`
  existe en el módulo.

### 1.2 Los tipos de la sesión

**Dónde:** `domain/session.py`.

```python
class SessionHeader(BaseModel, frozen=True):
    id: str  # "20261026-091502-3fa2"
    created_at: datetime  # UTC
    cwd: str  # resolved directory where maha ran
    provider: str
    model: str  # the model when the session started
    maha: str  # version that created it


class MessageEntry(BaseModel, frozen=True):
    type: Literal["message"] = "message"
    message: Message


class UsageEntry(BaseModel, frozen=True):
    type: Literal["usage"] = "usage"
    usage: Usage  # tokens of one finished turn


class ModelEntry(BaseModel, frozen=True):
    type: Literal["model"] = "model"
    model: str  # /model changed it from here on


type SessionEntry = Annotated[
    MessageEntry | UsageEntry | ModelEntry, Field(discriminator="type")
]


class Session(BaseModel, frozen=True):
    header: SessionHeader
    messages: list[Message]
    model: str  # the last one: header.model or the last ModelEntry
    usage: Usage  # sum of every UsageEntry


class SessionSummary(BaseModel, frozen=True):
    id: str
    cwd: str
    updated_at: datetime
    messages: int
    title: str  # first line of the first user message, cut
```

- **El id se lee y se ordena:** fecha y hora UTC más 4 hex al azar
  (`secrets.token_hex(2)`). Es corto de teclear y dos sesiones en el mismo
  segundo no chocan. Un uuid (también el uuid7) no se teclea a mano.
- **`is_session_id()`** comprueba el formato (`^\d{8}-\d{6}-[0-9a-f]{4}$`)
  antes de convertir un id en ruta: `/resume ../../etc/passwd` no llega
  nunca al disco.
- **`check_history(messages)`** comprueba lo que exige la API: cada
  `ToolCallBlock` del asistente tiene su `ToolResultBlock` en el mensaje
  `tool` siguiente, y nada sobra. Una sesión que no lo cumple no se retoma:
  daría un error 400 en la primera llamada.
- **Errores:** `SessionError` y sus tres tipos, `SessionNotFound`,
  `SessionInUse` y `SessionCorrupt`, en `domain/session.py`.
- Corrige DESIGN §5 (`Session`): lleva cabecera, modelo actual y tokens.

### 1.3 El fichero: un JSONL por sesión, solo se añade

`$XDG_DATA_HOME/maha/sessions/<id>.jsonl`. La primera línea es la cabecera;
cada línea siguiente, una `SessionEntry`:

```json
{"type": "session", "version": 1, "id": "20261026-091502-3fa2", "created_at": "2026-10-26T09:15:02Z", "cwd": "/home/ana/proyecto", "provider": "opencode-go", "model": "glm-5.3-flash", "maha": "0.6.0"}
{"type": "message", "message": {"role": "user", "blocks": [{"type": "text", "text": "Hola"}]}}
{"type": "message", "message": {"role": "assistant", "blocks": [{"type": "text", "text": "Hola. ¿Qué hacemos?"}]}}
{"type": "usage", "usage": {"input_tokens": 742, "output_tokens": 31, "cache_read_tokens": 0, "cache_write_tokens": 0}}
{"type": "model", "model": "kimi-k3"}
```

- **Solo se añade** (`O_APPEND`): un turno es una sola escritura con todas
  sus líneas, seguida de `fsync`. Si `maha` muere a mitad, como mucho queda
  una última línea rota.
- **Última línea rota:** al cargar, se ignora si es la última y no acaba en
  salto de línea; al retomar, se recorta antes de añadir, para que no quede
  en medio. Una línea rota en otro sitio es `SessionCorrupt`.
- **`version: 1`:** una versión que `maha` no conoce da `SessionCorrupt` con
  un mensaje claro, en lugar de leerla mal.
- **Permisos:** carpeta `0700` y ficheros `0600`. Una sesión guarda todo lo
  que leyó el agente, también un secreto que aprobaste leer (DESIGN §10).
- **Fuera del repositorio siempre:** vive en el `HOME`, no en el directorio
  de trabajo (AGENTS.md, datos sensibles).
- **Sin fichero hasta el primer turno:** abrir `maha` y salir no deja una
  sesión vacía.
- Descartado: SQLite (es para la memoria, hito 13; aquí se lee y se escribe
  de punta a punta) y un JSON por sesión reescrito entero en cada turno (más
  lento y, si falla a mitad, se pierde todo).

### 1.4 Puerto `SessionStore`

**Dónde:** `ports/sessions.py`.

```python
class SessionLog(Protocol):
    """An open session: maha holds its lock until close()."""

    async def append(self, entries: Sequence[SessionEntry]) -> None: ...
    async def close(self) -> None: ...


class SessionStore(Protocol):
    async def create(self, header: SessionHeader) -> SessionLog: ...
    async def open(self, session_id: str) -> tuple[Session, SessionLog]: ...
    async def summaries(self) -> list[SessionSummary]: ...
    async def delete(self, session_id: str) -> None: ...
```

- **`SessionLog` lleva el bloqueo** (§1.5): mientras una sesión está abierta
  en un `maha`, otro no la retoma ni la borra (`SessionInUse`). Sin él, dos
  `maha` añadirían turnos mezclados al mismo fichero.
- **`open()` carga y bloquea en un paso:** no hay hueco entre leer y
  bloquear.
- **`summaries()` da todas**; la aplicación las ordena y marca las del
  directorio actual (§1.8).
- Fake: `MemorySessionStore` en `tests/fakes/sessions.py`, con el mismo
  bloqueo en memoria.

### 1.5 Adaptador `JsonlSessionStore`

**Dónde:** `adapters/storage/sessions.py`. Recibe la carpeta en el
constructor; `bootstrap` la calcula con la regla XDG (§1.1).

- `create()`: crea la carpeta (`0700`) si falta, abre el fichero con
  `O_CREAT | O_EXCL | O_APPEND` (`0600`), `flock(LOCK_EX | LOCK_NB)`, y
  escribe la cabecera.
- `open()`: valida el id, abre, bloquea (si falla, `SessionInUse`), lee y
  valida cada línea con Pydantic, recorta una última línea rota y comprueba
  `check_history()`.
- `append()`: una sola llamada `os.write` con todas las líneas y `fsync`.
- `summaries()`: lee cada fichero (cabecera, número de mensajes, primer
  mensaje del usuario), con la fecha de modificación como `updated_at`. Un
  fichero ilegible se salta, no rompe la lista.
- `delete()`: valida el id, comprueba que nadie lo tiene bloqueado y lo
  borra.
- Disco síncrono dentro de `async def`, como las herramientas de ficheros
  (sin hilos): son escrituras pequeñas.

### 1.6 La conversación se guarda sola

**Dónde:** `application/sessions.py`, nuevo.

```python
class Sessions:
    """Starts, resumes, lists and deletes sessions; owns the current one."""

    async def start(self) -> Conversation: ...
    async def resume(self, session_id: str | None) -> Conversation: ...
    async def summaries(self) -> list[SessionSummary]: ...  # all, newest first
    async def delete(self, session_id: str) -> None: ...


class Conversation:
    """An Agent plus the log where its turns go."""

    id: str | None  # None until the first turn is saved

    async def run(self, text: str) -> AsyncGenerator[AgentEvent]: ...
    async def switch_model(self, model: str) -> None: ...
    async def close(self) -> None: ...
```

- **`Conversation.run()` envuelve a `Agent.run()`:** pasa los eventos tal
  cual y, en su `finally`, guarda los mensajes nuevos de `agent.messages` y
  el `UsageEntry` del `TurnFinished`, si llegó. Guarda también tras Ctrl+C o
  un fallo del modelo: lo que el `Agent` ya conservó (spec 5, §1.5) consta en
  disco.
- **El `Agent` no sabe nada del disco:** sigue guardando el historial en
  memoria. Recibe el historial inicial (`history=`) y deja cambiar el modelo
  (`model` con setter). Retomar es crear un `Agent` nuevo con ese historial.
- **Un fallo al guardar no corta la conversación:** se avisa en la terminal
  (`warning: session not saved: …`) y se sigue. Perder el disco no debe
  perder la respuesta que ya está en pantalla.
- La terminal usa `Conversation`, no `Agent` (`adapters/cli` llama a
  `application`, DESIGN §3).

### 1.7 La respuesta cortada con Ctrl+C se guarda, marcada

Cierra la pendiente de la spec 3, §1.6.

- **Qué se guarda:** si Ctrl+C llega mientras el modelo escribe y ya hay
  texto, el turno conserva el mensaje del usuario, los pasos completos y un
  mensaje del asistente con el texto que llegó. Las llamadas a herramientas
  a medio llegar se descartan: no se ejecutaron.
- **La marca, en el dominio:** `Message.interrupted: bool = False`. Es un
  hecho de la conversación, no un texto: la terminal lo enseña al retomar y
  cada adaptador decide cómo contárselo al modelo.
- **En el adaptador de OpenAI:** el `content` del mensaje cortado acaba en
  `"\n\n[interrupted by the user]"`. Así el modelo sabe que no terminó y no
  lo repite como si fuera completo.
- **`Accumulator.text`:** el texto recibido hasta ahora, sin exigir
  `MessageEnd`.
- **Un fallo del modelo a mitad** (no Ctrl+C) no guarda el parcial: el texto
  puede estar mal formado y el turno se repite, como hoy.
- Descartado: meter la marca como texto del asistente en el dominio (el
  modelo aprendería a escribirla) o como mensaje `user` aparte (dos mensajes
  `user` seguidos al escribir el siguiente).

### 1.8 Comandos en la terminal

**Dónde:** `adapters/cli/commands.py` (parsear) y `conversation.py`
(ejecutar).

| Comando | Qué hace |
|---|---|
| `/sessions` | Las 20 más recientes **de todos los directorios**: id, fecha, mensajes, directorio y título; las de este directorio, marcadas con `*` |
| `/resume [ID]` | Retoma esa sesión, sea del directorio que sea; sin ID, la última de este directorio |
| `/delete ID` | Borra esa sesión, tras confirmar `[y/N]`; nunca la actual |
| `/model [ID]` | Sin ID, enseña el modelo; con ID, lo cambia desde el siguiente turno |
| `/help` | La lista de comandos |
| `/exit` | Como ahora |

- **Todas las sesiones, con su directorio** (decisión del mantenedor,
  2026-10-26): abras `maha` donde lo abras, ves y retomas cualquier
  conversación. El directorio sale abreviado con `~`; las de este, con `*`.
  Se compara el `cwd` resuelto de la cabecera con el actual.
- **Retomar una sesión de otro directorio:** se puede, con aviso
  (`[this session was in ~/web; tools work in ~/proyecto]`). Las
  herramientas **siguen** sobre el directorio donde se abrió `maha`: cambiar
  el perímetro (DESIGN §10) a mitad de la conversación, sin preguntar, no se
  hace. Para trabajar allí, se abre `maha` allí y se retoma.
- **El modelo no sabe del cambio** hasta el hito 10, que pone el directorio
  de trabajo en el system prompt (capa de entorno). Hasta entonces, el aviso
  es para ti.
- **`/resume` sin ID** retoma la última de este directorio; si aquí no hay
  ninguna, `no session in this directory (see /sessions)`. La última de
  todas sería una sorpresa: otro proyecto sin pedirlo.
- **Un comando no se manda al modelo.** Una línea cuya primera palabra es
  `/` y letras (`^/[a-z]+$`) es un comando; si no existe, `unknown command:
  /foo (see /help)`. Una línea como `/etc/hosts no existe` sí va al modelo.
- **`/resume`** cierra la sesión actual (suelta el bloqueo) y abre la otra.
  Enseña `[resumed ID · N messages · modelo]` y, si el último mensaje del
  asistente quedó cortado, `[the last answer was interrupted]`.
- **Modelo al retomar:** el último de la sesión, si es del mismo proveedor;
  si no, el de la configuración, con un aviso.
- **`/model`** no valida el id: no hay catálogo hasta el hito 7. Un id que no
  existe da el error del proveedor en el turno siguiente. El cambio se
  guarda como `ModelEntry`.
- **La confirmación de `/delete` es una pregunta:** como la de aprobación,
  descarta antes lo tecleado (`StdinLines.discard()`, spec
  `mejora-2026-10-26-deuda-pre-hito-6`, A2). Un `y` pegado detrás de
  `/delete ID` no borra nada.
- Todo texto de una sesión (títulos, ids leídos del disco) pasa por
  `clean()` antes de pintarse.

### 1.9 Las aprobaciones no viajan con la sesión

- Al retomar, "always this session" empieza vacío: el `Agent` nuevo trae su
  `SessionApprovals` nuevo.
- **Por qué:** una aprobación es una decisión de este momento, sobre este
  estado del disco. Recuperar ayer un "siempre" para `rm -rf build` es
  autonomía que nadie dio hoy (DESIGN §8).
- Las aprobaciones no se escriben en el fichero.

## 2. En la industria

| Pieza | M-Harness | Alternativas | Cuándo se elegirían |
|---|---|---|---|
| Formato | JSONL por sesión, solo se añade | JSON entero por sesión; SQLite; checkpointers de LangGraph (estado del grafo en cada paso); Sessions del OpenAI Agents SDK (SQLite) | Consultas entre sesiones; muchas sesiones o muy largas |
| Dónde | `~/.local/share/maha/sessions/` (XDG), todas juntas | Carpeta por proyecto (Claude Code: `~/.claude/projects/<carpeta>/`); en la nube | Sincronizar entre máquinas |
| Retomar | `/resume` dentro, de cualquier directorio | Opciones al arrancar (`--continue`, `--resume`); bifurcar una sesión | Scripts; probar dos caminos desde un punto |
| Respuesta cortada | Mensaje marcado en el dominio | Mensaje del usuario "[interrupted]"; no guardarla | Formatos que no admiten metadatos |

*Solo se citan categorías y herramientas; lo de Claude Code es lo observado en
el puesto (§1.1).*

## 3. Diseño de detalle

### 3.1 Ficheros

```
src/mharness/
├── domain/session.py             # nuevo: cabecera, entradas, Session, errores, is_session_id, check_history
├── domain/messages.py            # Message.interrupted
├── ports/sessions.py             # nuevo: SessionStore, SessionLog
├── application/collect.py        # Accumulator.text
├── application/agent.py          # history=, model, guarda el texto cortado
├── application/sessions.py       # nuevo: Sessions, Conversation
└── adapters/
    ├── storage/__init__.py       # nuevo
    ├── storage/sessions.py       # nuevo: JsonlSessionStore
    ├── models/openai_chat.py     # la marca de interrumpido
    ├── cli/commands.py           # nuevo: parsear los comandos
    └── cli/conversation.py       # usa Conversation; ejecuta los comandos
config.py                         # data_dir(env), con la regla XDG
bootstrap.py                      # cablea JsonlSessionStore y Sessions
tests/fakes/sessions.py           # nuevo: MemorySessionStore
docs/guia/06-historial.md
```

DESIGN §3 (árbol) gana `application/sessions.py` y `adapters/storage/
sessions.py`; se anota con fecha.

### 3.2 Configuración nueva

Ninguna en `config.toml`. La carpeta sale de `XDG_DATA_HOME` o de `HOME`.

## 4. Plan de tests

Sin llamadas reales ni red. Disco: solo en `tmp_path`.

**4.1 Dominio** (`tests/unit/test_session.py`)
1. `is_session_id()`: válidos; `../x`, vacío, mayúsculas, con `/`.
2. `check_history()`: conversación normal; llamada sin resultado; resultado
   sin llamada; ids que no casan.
3. `SessionEntry` validada por `type`; `Message.interrupted` por defecto
   `False` y se conserva al serializar.

**4.2 Fake** (`tests/unit/test_fake_sessions.py`): cumple el puerto; el
bloqueo da `SessionInUse`; `delete` de una abierta falla.

**4.3 Adaptador** (`tests/adapters/test_session_store.py`)
1. Crear, añadir y abrir: los mensajes, el modelo y los tokens vuelven
   iguales.
2. Permisos `0700` y `0600`, también con un umask permisivo.
3. Última línea rota: se ignora al cargar y se recorta antes de añadir; rota
   en medio → `SessionCorrupt`.
4. `version` desconocida y JSON inválido → `SessionCorrupt`; historial roto
   → `SessionCorrupt`.
5. Bloqueo entre dos `JsonlSessionStore` sobre la misma carpeta:
   `SessionInUse` al abrir y al borrar; tras `close()`, se puede.
6. Un id con otro formato no toca el disco (`SessionNotFound`).
7. `summaries()`: título, número de mensajes, orden; un fichero ilegible se
   salta.
8. Sin `fsync` no se considera escrito: un `fsync` que falla da error.

**4.4 Bucle** (`tests/unit/test_agent.py`)
1. `history=` entra en la primera petición.
2. Cambiar `model` cambia la petición siguiente.
3. Ctrl+C con texto a medias: el turno guarda usuario + asistente con
   `interrupted=True`; sin texto aún, nada (como hoy); tras una herramienta,
   el parcial va detrás de sus resultados. Las llamadas a medio llegar no
   constan.
4. Un fallo del modelo a mitad no guarda el parcial.

**4.5 Aplicación** (`tests/unit/test_sessions.py`, con el fake)
1. Sin turnos, no se crea sesión; tras el primero, sí, con su cabecera.
2. Cada turno añade sus mensajes y su `UsageEntry`; tras Ctrl+C, lo
   conservado consta sin `UsageEntry`.
3. `resume()`: historial, modelo de la sesión (mismo proveedor) o de la
   configuración (otro, con aviso); de otro directorio, con su aviso; sin id,
   la última de este directorio, o el mensaje si no hay;
   aprobaciones vacías.
4. `summaries()` da todas, las más recientes primero y las de este
   directorio marcadas; `delete()` de la actual falla.
5. Un fallo al guardar no corta el turno y se avisa.
6. `switch_model()` guarda un `ModelEntry`.

**4.6 Adaptador de OpenAI** (`tests/adapters/test_openai_chat.py`): un
mensaje con `interrupted=True` lleva la marca en `content`.

**4.7 Terminal** (`tests/adapters/test_commands.py` y
`test_conversation.py`)
1. Parseo: comandos, argumentos, desconocido, `/etc/hosts …` va al modelo.
2. `/sessions` (vacío y con varias), `/resume`, `/delete` con `y` y con `n`
   (y un `y` tecleado antes se descarta), `/model` con y sin id, `/help`.
3. Títulos con caracteres de control salen escapados.

**4.8 De punta a punta** (`tests/test_bootstrap.py`): dos `maha` seguidos
con el mismo `XDG_DATA_HOME` temporal: el segundo hace `/resume` y el modelo
recibe el historial del primero.

## 5. Evals

No aplica todavía (hito 8). El cambio toca el bucle (el parcial cortado), y
la marca `[interrupted by the user]` es texto para el modelo: candidata a la
batería.

## 6. Orden de piezas para el implementador

Cada punto es un commit, en verde.

**PR 1** (`feature/hito-6-contrato`): dominio, puerto y fake.
1. **Tipos de la sesión.** `domain/session.py`; tests 4.1.1 y 4.1.3.
   *Commit:* "Añadir los tipos de la sesión"
2. **Historial válido.** `check_history()`; test 4.1.2. *Commit:*
   "Comprobar que un historial se puede mandar al modelo"
3. **Puerto y fake.** `ports/sessions.py`, `MemorySessionStore`; tests 4.2.
   *Commit:* "Añadir el puerto de las sesiones"
4. **Mapa.**

**PR 2** (`feature/hito-6-jsonl`): el disco.
5. **Crear, añadir y abrir.** 4.3.1, 4.3.2, 4.3.6 y 4.3.8. *Commit:*
   "Guardar las sesiones en JSONL"
6. **Líneas rotas y versión.** 4.3.3 y 4.3.4.
7. **Bloqueo.** 4.3.5. *Commit:* "Bloquear la sesión abierta"
8. **Lista y borrado.** 4.3.7.
9. **Mapa.**

**PR 3** (`feature/hito-6-conversacion`): bucle y aplicación.
10. **`Message.interrupted` y la marca en OpenAI.** 4.4 (parte) y 4.6.
11. **El `Agent` guarda el parcial cortado.** `Accumulator.text`; 4.4.3 y
    4.4.4.
12. **Historial inicial y modelo.** 4.4.1 y 4.4.2.
13. **`Sessions` y `Conversation`.** 4.5. *Commit:* "Guardar la conversación
    al terminar cada turno"
14. **Mapa.**

**PR 4** (`feature/hito-6-terminal`): comandos y cableado.
15. **Parsear comandos.** 4.7.1.
16. **`/sessions`, `/resume`, `/delete`, `/model`, `/help`.** 4.7.2 y
    4.7.3.
17. **Cableado.** `data_dir()`, `JsonlSessionStore`, `Sessions`; 4.8.
18. **Mapa.**

**PR 5** (`feature/hito-6-cierre`): versión 0.6.0, verificación, nota de la
guía, spec IMPLEMENTADA y docs. **Tras el PR 5:** tag `v0.6.0`.

## 7. Verificación a mano

Con `opencode-go` y `glm-5.3-flash`, en un directorio desechable.

1. `maha --version` → `maha 0.6.0`.
2. Dos turnos ("me llamo Ana", "¿cómo me llamo?") y `/exit`. Hay un
   fichero en `~/.local/share/maha/sessions/`, con permisos `0600`.
3. `maha` de nuevo, `/sessions` → la sesión, con su título; `/resume` →
   "¿cómo me llamo?" responde Ana.
4. Una pregunta larga y Ctrl+C a mitad; `/exit`; `/resume` → aviso de
   respuesta cortada; "¿qué estabas diciendo?" → el modelo sabe que lo
   cortaron.
5. `/model kimi-k3`, un turno: la línea de tokens sale; `/resume` en otro
   `maha` → sigue con `kimi-k3`.
6. Una escritura aprobada con `a`; `/exit`; `/resume` y otra escritura →
   vuelve a preguntar.
7. Dos terminales: la misma sesión abierta en una; `/resume` en la otra →
   `session in use`.
8. `/delete` de otra sesión, con `n` (sigue) y con `y` (desaparece de
   `/sessions`).
9. `/sesions` (mal escrito) → `unknown command`, no va al modelo.
10. En otro directorio, `/sessions` enseña también las del primero, con su
    directorio; `/resume ID` de una de ellas avisa de que las herramientas
    trabajan aquí.

## 8. Lo que no viaja por git y lo que necesita la release

- Ninguna variable nueva. `PUESTA_EN_MARCHA` §3 ya cita
  `~/.local/share/maha/`; se añade que las sesiones viven en `sessions/` y
  no pasan entre máquinas.
- `docs/MAPA.md`: los ficheros de §3.1.
- `docs/DESIGN.md` §3 y §5: corregidos en el mismo commit que esta spec, con
  fecha.

## 9. Guía

`docs/guia/06-historial.md`, "Historial y sesiones: el modelo no recuerda,
el disco sí":
1. El historial es la memoria del modelo: se manda entero en cada llamada
   (enlaza con la nota 02).
2. JSONL que solo se añade: por qué aguanta un corte a mitad.
3. Un historial válido: llamadas y resultados emparejados.
4. La respuesta cortada: guardarla marcada y por qué no como texto.
5. Lo que no se recupera: las aprobaciones.
6. "En la industria": la tabla de §2.

Corrige la nota 03, que dice que esto llega en el hito 6.

## 10. Riesgos

**POR VERIFICAR:**
- Cómo reacciona `glm-5.3-flash` a la marca `[interrupted by the user]`
  (verificación a mano, punto 4).

**Riesgos y contingencias:**
- **Sesiones con secretos en disco:** si aprobaste leer un `.env`, su
  contenido queda en la sesión. Mitigación: `0600`, fuera del repo, y la
  guía lo dice. Borrar es `/delete`.
- **Sesiones muy largas:** se cargan enteras y se mandan enteras; la ventana
  de contexto es del hito 11. Una sesión que ya no cabe da el error del
  proveedor.
- **Disco lleno o sin permisos:** se avisa y la conversación sigue sin
  guardar (§1.6).
- **`flock` en sistemas de ficheros de red:** puede no funcionar; el destino
  es el disco local del usuario (Linux, DESIGN §7).

## 11. Decisiones

Del humano (2026-10-26): **acepta las recomendaciones 1, 3, 4 y 5**. **Cambia
la 2:** `/sessions` enseña las sesiones de todos los directorios, con el de
cada una, y se puede retomar cualquiera ("algo que echo de menos de Claude
Code es que si no abro exactamente el mismo directorio es como si no supiera
nada"). El agente concretó cómo (§1.8): las del directorio actual marcadas,
aviso al retomar una de otro, las herramientas siguen sobre el directorio
de `maha` y `/resume` sin ID mira solo este.

Dudas que se plantearon al mantenedor (registro):

1. **La respuesta cortada** (§1.7). Propuesta: un campo `interrupted` en el
   mensaje, que el adaptador traduce a una marca de texto. Alternativas:
   (a) un mensaje `user` "[interrupted]" aparte; (b) seguir sin guardarla.
2. **Sesiones por directorio** (§1.8). Propuesta: `/sessions` y `/resume`
   solo ven las del directorio actual. Alternativa: todas, con su
   directorio en la lista.
3. **Las aprobaciones no se recuperan al retomar** (§1.9). Propuesta: no.
   Alternativa: guardarlas en la sesión.
4. **Bloqueo de la sesión abierta** (§1.4, §1.5). Propuesta: `flock`, y
   otro `maha` no la retoma ni la borra. Alternativa: sin bloqueo (más
   simple; dos `maha` con la misma sesión la mezclarían).
5. **Retomar solo con `/resume`** (§0). Propuesta: las opciones al arrancar
   (`--continue`) van al hito 8, con `maha -p`. Alternativa: añadir ya
   `maha --continue`.

## 12. Aprendido al implementar (2026-10-26)

**PR 1** (`feature/hito-6-contrato`, piezas 1 a 4):
1. Tipos (`839f54e`). `session_id(created_at, token)` es pura: la hora y
   el azar los pone quien crea la sesión (la aplicación, PR 3). El test de
   `Message.interrupted` (4.1.3) va con su pieza, la 10.
2. `check_history()` (`acd219b`): da el primer problema, con el id.
3. Fuera de plan: `replay()` y `summarize()` en el dominio (`ffbd2f4`).
   Reconstruir una sesión desde sus líneas lo necesitan el fake y el
   adaptador JSONL; así no se escribe dos veces. `replay()` llama a
   `check_history()`; `summarize()` no, para que una sesión rota salga en
   `/sessions` y se pueda borrar. Para sumar los tokens, `Usage.__add__`
   (`434c463`), que sustituye al `_add` del bucle.
4. Puerto y fake (`55b6e5f`). El fake usa
   `replay()` y `summarize()`, como hará el adaptador.

**PR 2** (`feature/hito-6-jsonl`, piezas 5 a 9):
5. Crear, añadir y abrir (`e30b65a`). La carpeta se crea con `mkdir` y se
   le pone `0700` después, porque `mkdir` sigue al umask. Un `OSError` al
   escribir o al hacer `fsync` sale como `SessionError("cannot save session
   …")`, para que la aplicación (PR 3) solo tenga que capturar
   `SessionError`. `summaries` y `delete` quedaron sin implementar hasta la
   pieza 8.
6. Líneas rotas y versión (`ca400c1`). Cada escritura acaba en `\n`, así
   que una última línea sin él está cortada aunque sea JSON válido: se
   ignora siempre. Una versión mayor dice "made by a newer maha"; una que
   falta o no es un número, "unknown version".
7. Bloqueo (`db3b828`). Fuera de plan: entre abrir el fichero y bloquearlo,
   otro `maha` puede borrarlo; se compara el inodo del fichero bloqueado con
   el del nombre (`_still_named`), y si no es el mismo, `SessionNotFound`.
   Sin eso, el turno se escribiría en un fichero sin nombre y se perdería.
8. Lista y borrado (`3652d68`). La
   lista no bloquea (una sesión abierta también sale) y no comprueba el
   historial, para que una rota se pueda borrar. Salta lo que no casa con
   un id, lo que no puede leer y una cabecera con otro id.

**PR 3** (`feature/hito-6-conversacion`, piezas 10 a 14):
10. `Message.interrupted` y la marca en OpenAI (`777d1ef`). Con el test de
    4.1.3 que quedó del PR 1.
11. El parcial cortado (`d12ea22`). Una bandera `streaming` dice si el corte
    llegó mientras el modelo escribía; solo entonces se guarda el texto.
    Dos tests antiguos fijaban lo contrario (spec 3, §1.6: "no se guarda") y
    se reescribieron con la spec §1.7.
12. Historial y modelo (`4c22e4a`). `model` es un atributo público, no una
    propiedad con setter: no hace falta más.
13. `Sessions` y `Conversation` (`e197e77`). Lo que la spec no fijaba,
    dentro de las reglas hexagonales:
    - `application` no pinta: un fallo al guardar queda en
      `Conversation.unsaved`, y `resume()` devuelve hechos (`Resumed`); el
      texto lo pone la terminal (PR 4);
    - el `Agent` lo crea una fábrica inyectada (`new_agent(model,
      history)`), y el reloj y el azar del id se inyectan, con valores por
      defecto de la biblioteca estándar;
    - lo no guardado (mensajes y tokens) se reintenta en el turno siguiente
      y al cerrar;
    - `/model` antes del primer turno va en la cabecera; después, como
      `ModelEntry` en el acto;
    - `resume()` abre y bloquea la nueva antes de soltar la actual, y si
      algo falla entre medias suelta la nueva;
    - retomar la sesión actual o borrarla da `this is the current session`.

    Fuera de plan, un arreglo del PR 2 (`f2949f3`): un `OSError` de
    `fchmod`, del `fsync` de la carpeta, de la lectura o de `ftruncate`
    salía tal cual, y `Conversation` solo captura `SessionError`. Ahora todo
    fallo del disco es `SessionError`, y una sesión que no se pudo crear
    entera se borra (si no, quedaría vacía en `/sessions`, porque el
    reintento usa otro id).

**PR 4** (`feature/hito-6-terminal`, piezas 15 a 18):
15. Parsear comandos (`3309dbf`). Un `/tmp` solo es un comando desconocido,
    como dice la regla (`^/[a-z]+$` como primera palabra); `/tmp/x` es texto.
16. y 17. Comandos y cableado, en un commit (`dbd6036`): `converse` recibe
    `Sessions`, y sin cambiar `bootstrap` a la vez el commit no quedaba en
    verde. Antes, `data_dir()` en su propio commit (`b2211c1`). Lo que la
    spec no fijaba:
    - los comandos se ejecutan en `adapters/cli/commands.py` (`Commands`),
      junto al parser, y no en `conversation.py`, que sigue dedicado a la
      respuesta. *(Corregido al implementarlo: §1.8 decía
      `conversation.py`.)*
    - la fecha de `/sessions` va en hora local, `2026-10-26 09:15`, no "hoy"
      o "ayer" como el ejemplo de §0: la interfaz está en inglés y no hace
      falta un reloj para pintarla;
    - la cabecera dice `/help for commands` en lugar de `/exit to quit`;
    - `/delete` de la sesión actual se rechaza antes de preguntar `[y/N]`;
    - Ctrl+C durante la confirmación de `/delete` termina `maha`, como en el
      prompt.
    Fuera de plan (`6b089f9`): al cablear, los tests de punta a punta
    escribieron seis sesiones de prueba en el `~/.local/share/maha` real del
    puesto. Se borraron (eran todas de carpetas temporales de pytest) y
    `tests/conftest.py` da a cada test su propio `XDG_DATA_HOME`; un test lo
    fija.
    La prueba de punta a punta de §4.8, en su commit (`d163657`).
18. Mapa y `PUESTA_EN_MARCHA` §0 y §3.
