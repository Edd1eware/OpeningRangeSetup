# Protección contra suspensión durante corridas

Se implementó `windows_run_awake.py` mediante la API nativa de Windows
`SetThreadExecutionState`.

## Comportamiento

- Solicita `ES_SYSTEM_REQUIRED` para impedir suspensión automática.
- Solicita `ES_DISPLAY_REQUIRED` para impedir que la pantalla se apague.
- No mueve el mouse ni envía teclas artificiales.
- No modifica permanentemente el plan de energía.
- Renueva la solicitud cada 30 segundos.
- Al terminar la corrida libera la solicitud con `ES_CONTINUOUS` y Windows vuelve
  a utilizar la configuración normal del usuario.

`resume_replay_x10_uia_failfast.py` activa esta protección automáticamente en
futuras corridas. Para la corrida que ya estaba en ejecución se lanzó un watcher
independiente asociado al coordinador post-run; seguirá activo también durante el
análisis Grupo D y se cerrará al terminar todos los procesos.
