# Guía: cómo se construye un agente

Una nota por hito, corta y directa. Cada nota tiene tres partes:
- **El problema:** qué resuelve la pieza.
- **Cómo lo resuelve M-Harness**, con un ejemplo de pocas líneas.
- **En la industria:** qué se usa normalmente (librerías, frameworks, patrones)
  y cuándo se elegiría.

Cada nota se escribe en el mismo PR que cierra su hito.

| # | Nota | Estado |
|---|---|---|
| 01 | [La arquitectura hexagonal de un agente](01-arquitectura-hexagonal.md) | Escrita (hito 1, `v0.1.0`) |
| 02 | [Qué es una llamada a un LLM y por qué el modelo no recuerda](02-llamada-a-un-llm.md) | Escrita (hito 2, `v0.2.0`) |
| 03 | [Streaming: el texto que llega a trozos](03-streaming.md) | Escrita (hito 3, `v0.3.0`) |
| 04 | [Tool calling y el bucle agéntico](04-tool-calling.md) | Escrita (hito 4, `v0.4.0`) |
| 05 | [Permisos: el modelo propone, el código decide](05-permisos.md) | Escrita (hito 5, `v0.5.0`) |
| 06 | [Historial y sesiones: el modelo no recuerda, el disco sí](06-historial.md) | Escrita (hito 6, `v0.6.0`) |
| 07 | [Trazas y coste: lo que pasó y lo que costó](07-observabilidad.md) | Escrita (hito 7, `v0.7.0`) |
| 08 | [Cómo se evalúa un agente](08-evals.md) | Escrita (hito 8, `v0.8.0`) |
| 09 | [Dos formatos para hablar con un modelo](09-formatos-de-api.md) | Escrita (hito 9, `v0.9.0`) |
| 10 | [El system prompt: lo que el modelo sabe antes de leerte](10-system-prompt.md) | Escrita (hito 10, `v0.10.0`) |
| 11 | [El contexto virtual: ventana fija, archivo y `recall`](11-contexto-virtual.md) | Escrita (hito 11, `v0.11.0`) |
| 12 | La órbita larga: menos idas y vueltas al modelo | Pendiente (hito 12) |
| 13 | Deshacer: puntos de control | Pendiente (hito 13) |
| 14 | Skills y comandos personalizados | Pendiente (hito 14) |
| 15 | Memoria persistente | Pendiente (hito 15) |
| 16 | Aislamiento (sandbox) y modos de permiso | Pendiente (hito 16) |
| 17 | Subagentes | Pendiente (hito 17) |
| 18 | MCP | Pendiente (hito 18) |
| 19 | Hooks | Pendiente (hito 19) |
| 20 | El agente y la web | Pendiente (hito 20) |
| 21 | Entrada multimodal | Pendiente (hito 21) |
| 22 | La interfaz de terminal | Pendiente (hito 22) |
| 23 | OpenTelemetry | Pendiente (hito 23) |
| 24 | Recorrido completo: de la primera llamada a la v1.0 | Pendiente (hito 24) |
