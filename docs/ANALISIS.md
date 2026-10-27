# M-Harness — Análisis del problema (fase 1)

**Fecha:** 19/10/2026
**Tipo:** Software + IA
**Estado:** Cerrado. Base del diseño (`docs/DESIGN.md`).

## 1. Resumen
M-Harness es un agente de terminal de propósito general, en la línea de Claude
Code, OpenCode o Hermes Agent. Se construye desde cero en Python, sin
frameworks de agentes, en 17 piezas incrementales (§5). Tiene un doble
objetivo:
- un arnés completo, comprensible pieza a pieza y con modelo y proveedor
  intercambiables;
- un repositorio público que documente cómo se construye, con un historial de
  PRs, specs y versiones que sirva de guía.

El código lo genera un agente de código, y cada fichero pasa por revisión
humana antes de integrarse.

## 2. Contexto y actores
Es un proyecto personal de código abierto (licencia MIT) con un único
mantenedor, que decide el alcance, revisa cada cambio y es el primer usuario.

- **Mantenedor:** define el alcance, aprueba las specs, revisa cada fichero e
  integra los PRs.
- **Agentes de código** (Claude Code, OpenCode): escriben el código y los
  documentos siguiendo `AGENTS.md`, desde varias máquinas (Linux, y Windows con
  WSL2).
- **Usuario:** el propio mantenedor, en esta etapa.
- **Lectores del repositorio:** cualquiera que quiera entender cómo se
  construye un agente. El historial, las specs y la documentación están
  escritos pensando en ellos.

## 3. Situación actual
Los agentes de código actuales resuelven bien el uso, pero no el
entendimiento. O no publican su código, o lo reparten en bases de código
grandes y en rápida evolución, donde el bucle, los permisos, el contexto y la
memoria no se pueden estudiar por separado.

```
Agentes existentes:  usuario ──► agente (caja negra) ──► modelo
                     las piezas internas no se ven por separado

M-Harness:           cada pieza llega en su propio PR, con su spec, sus tests
                     y lo aprendido al implementarla; el historial es la guía
```

**Referencias de producto:** Claude Code, OpenCode y Hermes Agent (Nous
Research, MIT, febrero de 2026). Sirven de referencia de comportamiento y de
diseño, no de base de código.

## 4. Problema y objetivo
Entender un agente en profundidad exige construirlo. Usarlo no enseña cómo se
gestionan el bucle, los permisos, el contexto o la memoria, y sin ese
conocimiento no se puede modificar a fondo ni adaptar a un entorno concreto. No
hay línea base numérica. El valor se mide por las piezas construidas, el
comportamiento en las evals y la legibilidad del historial (§11).

**Objetivo:** un agente de terminal funcional, escrito desde cero, que cumpla
tres condiciones:
- cada pieza de §5 está implementada, probada y documentada;
- cambia de modelo y de proveedor solo con configuración;
- el repositorio público documenta su construcción de forma profesional.

*(Ampliado el 27/10/2026 por decisión del mantenedor:)* **Segundo objetivo,
al mismo nivel: un producto profesional para cualquier usuario.** Lo más
completo posible en capacidades (comandos, opciones, herramientas,
conectores, memoria…) y, a la vez, intuitivo y fácil de usar (DESIGN §14,
hito 19: una TUI completa). Se sigue construyendo a mano, pieza a pieza y
documentado: los dos objetivos van juntos. Qué capacidades entran, y
cuándo, sale de comparar el plan con OpenCode y Claude Code
(`docs/COMPARATIVA.md`).

## 5. Alcance
El sistema son 17 piezas, que se construyen de forma incremental en el orden
que fije el diseño, empezando por las herramientas más comunes.

| # | Pieza | Qué incluye |
|---|---|---|
| 1 | Cliente de modelos multiproveedor | Adaptadores propios para los formatos de OpenAI y Anthropic; proveedor y modelo en configuración |
| 2 | Bucle agéntico | Llamar al modelo → ejecutar herramientas → devolver resultados → repetir; límites de pasos, tokens y tiempo; parada; interrupción por el usuario |
| 3 | Herramientas | Definición tipada, ejecución y errores devueltos al modelo. Primero las comunes (ficheros, búsqueda, terminal) |
| 4 | Permisos | Tres niveles: lectura libre, efecto con aprobación, prohibido inexistente. Denegado por defecto |
| 5 | System prompt | Composición por capas: base + instrucciones del proyecto + skills + memoria |
| 6 | Historial y sesiones | Guardar, listar, reanudar y borrar conversaciones |
| 7 | Gestión del contexto | Contar tokens; compactar antes de llenar la ventana |
| 8 | Skills | Carga bajo demanda: índice en el prompt y contenido solo cuando hace falta. El usuario añade las suyas |
| 9 | Memoria persistente | Recuerdos entre sesiones, guardados y consultados con herramientas |
| 10 | MCP | Cliente que conecta los servidores MCP que declare el usuario |
| 11 | Subagentes | Herramienta que lanza un agente hijo con contexto propio, herramientas acotadas y límites propios |
| 12 | Ejecución aislada | El código y los comandos que lanza el agente pueden correr aislados (sandbox) |
| 13 | Entrada multimodal | Leer PDFs e imágenes, si el modelo lo admite |
| 14 | Web | Buscar y leer páginas |
| 15 | Trazas y coste | Registro de cada llamada al modelo y a herramientas, con tokens, coste y tiempo |
| 16 | Evals | Batería de tareas con resultado comprobable; comparación con la línea base |
| 17 | Interfaz de terminal | Programa interactivo, como Claude Code u OpenCode |

Las 17 piezas son el mínimo, no el techo *(27/10/2026)*: la comparación con
OpenCode y Claude Code puede añadir capacidades a los hitos o a las
versiones posteriores a la 1.0, siempre por decisión del mantenedor.

**Fuera de alcance:**
- **Varios usuarios, interfaz de escritorio o web, y despliegue en servidor.**
  Son capas de producto que no aportan al objetivo de entender el arnés.
- ~~**Distribución pública** (paquete instalable, documentación de usuario). Se
  abordará cuando el proyecto esté maduro. Hasta entonces, la estructura del
  código no lo impide.~~ *(Cambiado el 27/10/2026 por decisión del
  mantenedor: entra en la versión 1.0, DESIGN §13.)*

## 6. Requisitos funcionales
1. Es un programa interactivo de terminal: el usuario escribe, el agente responde
   en streaming y muestra cada llamada a herramienta y su resultado.
2. Tiene un modo no interactivo: recibe una instrucción como argumento y escribe
   la respuesta en la salida estándar. Hace falta para la batería de evals y
   para scripts.
3. El usuario elige proveedor y modelo en la configuración y puede cambiarlos
   dentro de una sesión.
4. El bucle agéntico tiene límites configurables de pasos, tokens y tiempo, y el
   usuario puede interrumpirlo en cualquier momento.
5. Herramientas base: leer, escribir y editar ficheros; listar y buscar en
   ficheros; ejecutar comandos de terminal. Después se amplían.
6. Cada herramienta declara su nivel de permiso. Las que tienen efecto piden
   aprobación con un aviso que muestra qué se va a hacer, y el usuario aprueba
   una vez, aprueba para toda la sesión o deniega. Lo no declarado está
   denegado.
7. Las sesiones se guardan solas y se pueden listar, reanudar y borrar.
8. El agente sabe cuántos tokens lleva en el contexto y lo compacta antes de
   llenarlo.
9. Skills: carpetas con `SKILL.md`, a nivel de proyecto y de usuario. El agente
   ve su índice y carga el contenido cuando lo necesita.
10. Las instrucciones del proyecto (un fichero tipo `AGENTS.md` en el directorio
    de trabajo) entran en el system prompt.
11. Memoria: el agente guarda y consulta recuerdos persistentes entre sesiones
    con herramientas. El usuario puede verlos y borrarlos.
12. MCP: el usuario declara servidores MCP en la configuración. Sus herramientas
    entran en el bucle con el mismo sistema de permisos.
13. Subagentes: una herramienta lanza un agente hijo con una tarea, contexto
    limpio, herramientas acotadas y límites propios. El hijo devuelve un
    resultado resumido.
14. Los comandos y el código que ejecuta el agente pueden correr en un entorno
    aislado.
15. El agente lee PDFs e imágenes cuando el modelo lo admite.
16. El agente busca en la web y lee páginas.
17. Cada sesión deja una traza de cada llamada al modelo y a herramientas, con
    tokens, coste y tiempo.
18. Un comando ejecuta la batería de evals y compara el resultado con la línea
    base.

## 7. Requisitos no funcionales
M-Harness corre en Linux, está escrito en Python sin frameworks de agentes, se
desarrolla con asistencia de agentes de código bajo revisión humana, y su
repositorio público documenta la evolución del proyecto.

- **Plataforma:** Linux. En Windows, a través de WSL2.
- **Lenguaje:** Python.
- **Desde cero:**
  - sin frameworks de agentes (LangGraph, Pydantic AI, SDKs de agentes…),
    porque ocultan justo lo que el proyecto quiere hacer explícito;
  - para transportar las llamadas al modelo se admite un cliente HTTP o el SDK
    oficial del proveedor;
  - los adaptadores de formato son propios.

  La frontera exacta se concreta en el diseño.
- **Repositorio público y profesional:**
  - una rama por cambio y un PR por rama;
  - un commit por cada pieza pequeña de código;
  - un tag por hito;
  - CI visible en cada push;
  - README, licencia MIT y specs que documentan cada paso.

  El historial tiene que mostrar cómo se construye un agente desde cero.
- **Desarrollo asistido con revisión humana:** el código lo escribe un agente
  de código, y ningún cambio se integra sin que el mantenedor haya revisado
  cada fichero. Para que eso funcione:
  - PRs lo bastante pequeños para revisarse de una sentada;
  - cada PR explica qué hace cada fichero nuevo o cambiado y por qué;
  - un mapa del código en la documentación dice dónde está cada cosa.
- **Continuidad entre máquinas y agentes:** todo el contexto vive en el repo.
  Cualquier agente de código que lo abra, en cualquier máquina, entiende el
  proyecto, el método de trabajo y el estado leyendo los documentos.
- **Ritmo:** sin plazo y con sesiones de trabajo discontinuas (puede haber
  semanas de dedicación intensa y semanas sin actividad). Los hitos son
  pequeños y cada uno deja el agente funcionando. El estado siempre está al día
  para poder retomar en cualquier momento.
- **Seguridad:**
  - credenciales solo en `.env`;
  - herramientas denegadas por defecto y aprobación para las que tienen efecto;
  - aislamiento para el código;
  - el contenido de ficheros, webs, servidores MCP y salidas de herramientas es
    entrada no confiable;
  - en un repo público, una credencial filtrada queda expuesta al momento.
- **Coste:** visible por llamada y por sesión.
- **Latencia:** respuesta en streaming.
- **Auditabilidad:** traza completa de cada sesión.
- **Legibilidad:** se prefiere código claro a abstracciones, porque el
  propósito del repositorio es que se entienda.
- **Integraciones:** proveedores de modelos con formato OpenAI o Anthropic
  (OpenCode Go; OpenCode Zen como alternativa) y servidores MCP.
- **Idioma:** documentación, commits y PRs en español. Código (nombres,
  comentarios y docstrings) en inglés.

## 8. Inventario de datos
El agente trabaja con los ficheros del directorio de trabajo y con la web. En el
repositorio público solo entran datos inventados o públicos.

| Fuente | Contenido | Uso | Acceso hoy |
| --- | --- | --- | --- |
| OpenCode Go (Zen como alternativa) | API de modelos, formatos OpenAI y Anthropic | Inferencia | Suscripción del mantenedor (ver §12) |
| Directorio de trabajo | Código y documentos | Lo que lee y edita el agente | Local |
| Web | Páginas y resultados de búsqueda | Herramienta web | Proveedor de búsqueda por decidir en el diseño |
| Sesiones, trazas y memoria | Generados por el agente | Persistencia | Local, nunca en el repo |
| Batería de evals | Tareas con resultado comprobable, con datos inventados | Evals | Por crear; vive en el repo |

## 9. Naturaleza del problema de IA
La IA es el núcleo, porque el objetivo es construir el arnés que rodea al LLM.
Todo lo determinista (permisos, límites, persistencia, ejecución de
herramientas) es código, nunca prompt.

- **¿Hace falta IA?** Sí, por definición del proyecto. Lo que pueden resolver
  reglas se resuelve con reglas dentro del arnés.
- **Tipo de tarea:** actuar con herramientas (agente), con subagentes.
- **Coste del error:** asimétrico.
  - Una respuesta mala cuesta poco: se repite.
  - Una herramienta con efecto mal ejecutada puede borrar ficheros, lanzar
    comandos dañinos o filtrar credenciales.
- **Humano en el bucle:** antes del efecto. Cada herramienta con efecto pide
  aprobación.
- **Datos para evaluar:** no hay golden dataset previo. Se crea una batería de
  tareas genéricas con resultado comprobable de forma automática, por ejemplo
  sobre repos de prueba:
  - crear o editar ficheros;
  - hacer pasar un test;
  - encontrar un dato;
  - delegar en un subagente.

  Se mide el éxito, los pasos, los tokens y el coste por tarea. El tamaño se
  fija en el diseño.
- **Privacidad:** se usan modelos sin retención y que no entrenan con los datos.
  Se evitan los que sí entrenan; en OpenCode Go, *Gemini 4 Argon Contributor* y
  *Muse Spark Contributor* (comprobado el 19/10/2026 en la documentación de
  OpenCode Go).
- **Entrada no confiable:** webs, ficheros, salidas de herramientas, resultados
  de MCP y de subagentes. La defensa contra la inyección de prompts es un
  requisito desde el primer hito con herramientas: el contenido externo es dato,
  nunca instrucción, y nunca amplía permisos.

## 10. Riesgos y modos de fallo
Los dos riesgos que pueden hacer fracasar el proyecto son perder la continuidad
entre sesiones discontinuas y que el alcance (17 piezas) no deje nunca nada
funcionando. Los dos se atacan con hitos pequeños que dejan el agente usable.

| Riesgo | Efecto | Mitigación |
| --- | --- | --- |
| Pérdida de continuidad entre sesiones | El proyecto se estanca y se pierde el hilo | Hitos pequeños; `ESTADO.md` con un siguiente paso concreto; protocolo de inicio de sesión |
| Alcance demasiado grande | Nunca hay nada que funcione | Orden por dependencias; bucle mínimo funcionando en el primer hito y el resto encima |
| La revisión humana se relaja | El repo crece, pero el código deja de entenderse | PRs pequeños; explicación por fichero en cada PR; mapa del código; ningún merge sin revisión |
| El agente ejecuta algo destructivo | Pérdida de ficheros o daño al sistema | Permisos por niveles desde el primer hito con herramientas; denegado por defecto; sandbox; pruebas en directorios desechables |
| Inyección de prompts (web, ficheros, MCP) | El agente obedece instrucciones ajenas | Entrada no confiable delimitada; permisos en código; aprobación humana |
| Credencial expuesta en el repo público | Uso fraudulento de la API en minutos | `.env` fuera de git; escaneo de secretos en GitHub y antes de cada commit; secretos ocultos en las trazas |
| Cambios en los proveedores (modelos, límites, condiciones) | Se rompe el cliente o sube el coste | Proveedor detrás de una interfaz; modelo en configuración; hechos verificados con fecha |
| Ajustar el prompt a ojo | Regresiones invisibles | Batería de evals temprana |
| Coste descontrolado (bucles, subagentes) | Gasto inesperado | Límites de pasos y tokens; coste visible; topes de la suscripción |
| Dependencias rotas tras semanas sin actividad | El proyecto no arranca | Dependencias bloqueadas (lockfile); CI en cada push |
| Divergencia entre máquinas | Funciona en una y no en otra | Linux como destino; WSL2 en Windows; LF en git; CI en Linux |

## 11. Criterios de éxito
El proyecto tiene éxito si cumple tres cosas:
- las 17 piezas están construidas, probadas y documentadas (cada una con su
  spec cerrada y su "Aprendido al implementar");
- el agente resuelve la batería de evals con modelo y proveedor
  intercambiables;
- el historial público documenta la construcción.

| Métrica | Definición | Umbral |
| --- | --- | --- |
| Piezas construidas | Piezas de §5 implementadas, con tests y con la spec cerrada ("Aprendido al implementar") | 17 de 17, por hitos |
| Éxito en evals | Porcentaje de tareas de la batería resueltas | A fijar tras medir la línea base en el hito de evals |
| Cambio de modelo | Cambiar de proveedor o de modelo sin tocar código | Solo configuración |
| Trazabilidad | Sesiones con traza completa | 100 % |
| Seguridad | Herramientas con efecto ejecutadas sin aprobación | 0 |
| Secretos en el repo | Credenciales en el historial público | 0 |
| Ahorro de la memoria | Tokens por tarea con memoria frente a sin memoria | A fijar tras medir |
| Historial legible | Cada pieza llega por un PR con descripción, spec y commits pequeños | Todas |
| Revisión | Ficheros revisados por el mantenedor antes del merge | 100 % |
| Continuidad | Al retomar tras semanas sin actividad, un agente de código sabe dónde está y cuál es el siguiente paso solo con los documentos | En cada inicio de sesión |
| Uso propio | M-Harness se usa para desarrollar su propio repositorio | Sí, al cerrar la fase de desarrollo |

## 12. Restricciones y pendientes
El proyecto no tiene plazo ni presupuesto fijo, y todo lo que entra en el
repositorio es público. Lo pendiente se resuelve en el diseño o antes del hito
que lo necesita.

**Restricciones**
- Sin plazo; sesiones de trabajo discontinuas.
- Repositorio público: nada sensible en el historial, ni siquiera en un commit
  que se borre después.
- Python. Linux como destino.
- El código lo escribe un agente de código; cada fichero pasa por revisión
  humana.

**Pendientes**
- **Estrategia de merge de los PRs** (diseño): el método pide fast-forward, y
  desde la web de GitHub no se puede.
- **Frontera de "desde cero"** (diseño): concretar la propuesta de §7.
- **Tecnologías** de sandbox, búsqueda web y almacenamiento de memoria (diseño).
- **Proveedor de modelos para el desarrollo** (hito del cliente de modelos):
  OpenCode Go solo admite un miembro por espacio de trabajo; la alternativa es
  OpenCode Zen con pago por uso.
