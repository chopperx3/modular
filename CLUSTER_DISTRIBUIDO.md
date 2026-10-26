# Clúster distribuido de OCR: coordinador y workers

El reconocimiento ya no corre en el servidor que atiende a los teléfonos. El
servidor es un **coordinador**: recibe las imágenes por HTTP o WebSocket, las
reparte entre **nodos worker** que corren en otras computadoras de la red y
junta los resultados. Cada worker carga sus propios modelos y procesa las
imágenes con su propio procesador.

```
 Teléfono A ──WebSocket──┐                         ┌──TCP :9000──  Worker "laptop-1"  (EasyOCR local)
 Teléfono B ──WebSocket──┤                         │
 Navegador  ──HTTP───────┼──►  Coordinador (PC) ───┼──TCP :9000──  Worker "laptop-2"  (EasyOCR local)
                         │     FastAPI :8000       │
                         │     SQLite              └──TCP :9000──  Worker "pc-lab"    (...)
```

| Componente | Archivo | Qué hace |
|---|---|---|
| Protocolo | `BACKEND/app/cluster_protocol.py` | Formato de trama y tipos de mensaje |
| Coordinador | `BACKEND/app/cluster.py` | Registro de workers, cola, reparto, latidos, reasignación |
| Worker | `BACKEND/app/worker.py` | Proceso independiente que ejecuta el OCR y responde |
| Monitoreo | `GET /cluster/status` | Workers conectados, carga, cola y contadores |
| Pruebas | `BACKEND/tests/test_cluster.py` | 10 pruebas sobre TCP real |

## 1. Protocolo coordinador ↔ worker

Se usa **TCP directo** (`asyncio` streams), no HTTP: la conexión con cada worker
queda abierta, el coordinador puede empujarle tareas en cuanto llegan y detecta
de inmediato cuando el worker se cae (la conexión se rompe o dejan de llegar
latidos).

### Trama

```
+-----------------+----------------------+---------------------------+
| 4 bytes (u32 BE)| N bytes              | M bytes (opcional)        |
| N = largo header| header JSON (UTF-8)  | payload binario (imagen)  |
+-----------------+----------------------+---------------------------+
```

- El header siempre lleva `type`. Si lleva `payload_len = M`, siguen M bytes crudos.
- La imagen viaja **en binario**, sin base64: un 33 % menos de bytes que por el WebSocket de los teléfonos.
- TCP garantiza orden y entrega; el prefijo de longitud delimita los mensajes dentro del flujo de bytes.
- Límites: header ≤ 64 KB, payload ≤ 25 MB. Una trama fuera de rango cierra la conexión (`ProtocolError`).

### Mensajes

| Tipo | Sentido | Campos | Propósito |
|---|---|---|---|
| `hello` | W→C | `protocol_version`, `worker_id`, `host`, `slots`, `engines`, `token` | Registrarse; `slots` = imágenes simultáneas |
| `welcome` | C→W | `heartbeat_s`, `dead_after_s`, `coordinator_time` | Aceptar al worker |
| `reject` | C→W | `code` (`VERSION`, `AUTH`, `INVALID_HELLO`), `message` | Rechazar al worker |
| `task` | C→W | `task_id`, `attempt`, `langs`, `handwriting` + imagen | Asignar una imagen |
| `result` | W→C | `task_id`, `text`, `engine`, `elapsed_ms` | Devolver la transcripción |
| `task_error` | W→C | `task_id`, `code`, `status`, `message` | Error de la imagen (no se reintenta) |
| `heartbeat` | W→C | `ts`, `active`, `done`, `rtt_ms` | Latido cada `heartbeat_s` |
| `heartbeat_ack` | C→W | `ts` | Eco del latido para medir el RTT |
| `drain` | W→C | — | El worker deja de aceptar tareas (va a salir) |
| `bye` | W→C | `unfinished` | Salida ordenada |

### Secuencia normal

```
Worker                         Coordinador                       Teléfono
  │── hello(laptop-1, slots=1) ──►│                                  │
  │◄──────── welcome ─────────────│                                  │
  │── heartbeat (cada 3 s) ──────►│◄──── ocr_request (WebSocket) ────│
  │◄──── task(t1, imagen) ────────│──── ack(queue_position) ────────►│
  │   [EasyOCR en el worker]      │                                  │
  │── result(t1, texto) ─────────►│── guarda en SQLite (worker_id) ─►│ result
```

## 2. Reparto de carga

- La tarea va al worker con **menor carga relativa** (`tareas en curso / slots`). Si hay empate, se rota entre ellos (round robin).
- Un worker nunca recibe más tareas que sus `slots`. Si todos están llenos, la tarea espera en la cola del coordinador y sale en cuanto alguno se libera.
- La capacidad que se anuncia a los teléfonos es la suma de los slots de los workers.

## 3. Tolerancia a fallos

| Falla | Cómo se detecta | Qué hace el coordinador |
|---|---|---|
| Worker se apaga o pierde la red | La conexión TCP se rompe | Reasigna sus tareas en curso a otro worker |
| Worker congelado | Sin mensajes por `dead_after_s` (10 s) | Lo da por caído y reasigna |
| Tarea que nunca termina | Más de `task_timeout_s` (180 s) | La reasigna; si el primero responde después, se ignora el duplicado |
| Falla repetida | `max_attempts` (3) intentos | Responde error 503 al cliente |
| Imagen inválida (PDF corrupto) | `task_error` del worker | Error 500 al cliente, **sin** reintentar: daría lo mismo en otro nodo |
| Ningún worker conectado | Lista vacía | Respaldo local en el coordinador (`CLUSTER_LOCAL_FALLBACK=1`) o 503 tras `no_worker_wait_s` |
| Worker se reconecta con el mismo id | Nuevo `hello` | Cierra la sesión vieja y reasigna lo que tenía |
| Coordinador se reinicia | El worker pierde la conexión | El worker reintenta con espera creciente de 1 a 30 s |

Cada registro de `ocr_results` guarda en `worker_id` qué nodo lo procesó (`local` si fue el respaldo del coordinador).

## 4. Cómo correrlo en varias computadoras

Todas en la misma red Wi-Fi o LAN, con el repositorio y `pip install -r requirements.txt`.

**PC coordinadora** (la que recibe a los teléfonos):

```bash
cd BACKEND
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Al arrancar aparece `Coordinador escuchando workers en tcp://0.0.0.0:9000`.
En Windows hay que permitir el puerto 9000 en el firewall la primera vez
(o aceptar el aviso de Windows Defender para Python).

**Cada PC worker** (con la IP de la coordinadora, `ipconfig` en Windows):

```bash
cd BACKEND
python -m app.worker --coordinator 192.168.1.10:9000 --id laptop-1 --slots 1
```

Para ver el estado del clúster: `http://<IP-coordinador>:8000/cluster/status`.

Prueba de tolerancia a fallos para la demo: manda varias fotos desde el
teléfono y cierra la terminal de un worker a la mitad. En el log del
coordinador aparece `Worker laptop-1 fuera (...)` y `Reasignando tarea ...`,
y el teléfono recibe su resultado desde el otro worker.

Sin modelos instalados se puede probar todo el flujo con `--simulate 2`,
que reemplaza el OCR por una espera de 2 s.

### Variables de entorno (`BACKEND/.env`)

| Variable | Defecto | Uso |
|---|---|---|
| `CLUSTER_ENABLED` | `1` | `0` desactiva el coordinador y el servidor procesa todo él mismo |
| `CLUSTER_PORT` | `9000` | Puerto TCP para los workers |
| `CLUSTER_TOKEN` | vacío | Si se define, los workers deben mandar el mismo valor (`--token`) |
| `CLUSTER_HEARTBEAT_S` | `3` | Intervalo de latidos |
| `CLUSTER_DEAD_AFTER_S` | `10` | Silencio tras el cual un worker se da por caído |
| `CLUSTER_TASK_TIMEOUT_S` | `180` | Tiempo máximo de una tarea antes de reasignarla |
| `CLUSTER_MAX_ATTEMPTS` | `3` | Intentos por tarea |
| `CLUSTER_LOCAL_FALLBACK` | `1` | Procesar en el coordinador cuando no hay workers |
| `CLUSTER_NO_WORKER_WAIT_S` | `15` | Espera por un worker antes de rendirse (sin respaldo local) |

## 5. Pruebas

```bash
cd BACKEND
python -m pytest tests -q
```

`tests/test_cluster.py` levanta el coordinador y los workers sobre sockets TCP
reales en `127.0.0.1`, con el OCR simulado:

| Prueba | Verifica |
|---|---|
| `test_reparte_entre_workers_en_paralelo` | 4 tareas en 2 workers: 2 a cada uno, ~0.8 s frente a 1.6 s |
| `test_worker_que_se_cae_reasigna_la_tarea` | Worker cae a mitad de tarea → la termina otro |
| `test_worker_sin_latidos_se_da_por_caido` | Worker congelado → se detecta por latidos y se reasigna |
| `test_timeout_de_tarea_reasigna_a_otro_worker` | Tarea lenta → pasa a otro worker |
| `test_sin_workers_usa_respaldo_local_o_responde_503` | Sin nodos: respaldo local o 503 |
| `test_error_de_ocr_no_se_reintenta` | Error de la imagen no se reintenta |
| `test_salida_ordenada_termina_lo_pendiente` | `drain`/`bye`: termina lo pendiente y sale |
| `test_rechaza_token_o_version_incorrectos` | Autenticación y versión del protocolo |
| `test_trama_binaria_ida_y_vuelta` | Codificación de la trama |
| `test_api_rest_procesa_en_worker_de_otro_proceso` | `POST /ocr/` atendido por un worker en **otro proceso**, `worker_id` guardado en SQLite |

Prueba manual con procesos separados en una sola PC (servidor + 2 workers simulados de 1.5 s):

| Escenario | Resultado |
|---|---|
| 4 solicitudes simultáneas | 3.0 s (2 por worker), frente a 6 s con un solo nodo |
| Se mata `laptop-1` (`kill -9`) a los 0.7 s | Su tarea se reasignó a `laptop-2` (intento 2); las 2 solicitudes respondieron 200 |

Falta repetir estas pruebas con computadoras físicas distintas y el OCR real.
