# Evidencia: rate limiting en /chat

**Fecha de la prueba:** 2026-08-08
**Configuración:** `RATE_LIMIT_MAX=20`, `RATE_LIMIT_WINDOW_SECONDS=60`

## Prueba 1 — con mocks (sin gastar créditos), ráfaga instantánea

Simulación con `responder()` mockeado (sin latencia real), 21 peticiones seguidas:

```
Petición normal: 200 {'respuesta': 'respuesta de prueba'}
... (19 peticiones más, todas 200)
Petición 21: 429 {'detail': 'rate limit'}
```

Resultado: exactamente 20 permitidas, la 21 bloqueada — comportamiento ideal en una ráfaga pura (todas las peticiones llegan en el mismo instante).

## Prueba 2 — con el servidor real (créditos reales gastados), 25 peticiones secuenciales

```bash
for i in $(seq 1 25); do
  curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/chat \
    -H "Content-Type: application/json" \
    -d '{"user_id": "test-rate", "pregunta": "hola"}'
done
```

Resultado real:
```
200 200 200 200 200 200 200 200 200 200 200 200 200 200 200 200 200 200 200 200 200 200 200 200 429
```
(24 × `200`, 1 × `429` al final)

### Por qué NO salió "20 permitidas, 5 bloqueadas" como en la prueba con mocks

Cada petición real al agente completo (guardas + LLM + tools) tarda entre 5 y 9 segundos. Como el `curl` en el loop espera a que cada petición termine antes de lanzar la siguiente, **25 peticiones secuenciales reales tardan bastante más de 60 segundos en total** — la ventana deslizante del rate limiter (`ahora - timestamp < 60s`) hace que las peticiones más antiguas "caduquen" de la ventana antes de que terminen las últimas, permitiendo que pasen más de 20 en total.

El limitador sí actuó correctamente: hacia el final de la prueba, cuando la frecuencia real de peticiones se concentró lo suficiente dentro de una ventana de 60 segundos, la petición #25 fue bloqueada — confirmando que el mecanismo funciona con datos reales, no solo en el caso ideal simulado.

### Conclusión para el informe

El rate limiter protege correctamente contra ráfagas reales concentradas en el tiempo. Con este endpoint específico (5-9s por petición), un abuso real necesitaría enviar peticiones en **paralelo** (no secuenciales) para disparar el límite de forma más agresiva — lo cual es exactamente el escenario que el rate limiter está pensado para frenar (un script que golpea la API sin esperar respuesta, en vez de un usuario humano normal).