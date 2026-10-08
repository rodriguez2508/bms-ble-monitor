# Monitoreo Bluetooth BMS LiFePO₄

## 📋 Requisitos
- Python 3.8+ (probado en 3.10)
- Bluetooth LE (adaptador `hci0` activo)
- Dependencias: `pip install -r requirements.txt`

## 🚀 Cómo iniciar
```bash
python3 main.py
```

Arranca en un hilo el sondeo BLE (Modbus RTU sobre GATT) y el servidor Flask en
el puerto `FLASK_PORT` (8000 por defecto). El BMS se conecta al dispositivo
`AA:BB:CC:DD:EE:FF` cada `BMS_POLLING_INTERVAL` segundos y guarda cada lectura
en `data/*.csv` con timestamps.

## 🌐 API

| Endpoint | Descripción |
|----------|-------------|
| `GET /api/status` | Última lectura. `{"connected": bool, "data": {...}\|null}` |
| `GET /api/history/<metric>?limit=N` | Historial CSV; `metric` ∈ `voltage`, `current`, `soc` (default `limit=200`, tope 5000) |
| `GET /` o `GET /dashboard` | Dashboard web (HTML) |
| `WS /ws` | WebSocket (registro de clientes) |

Ejemplo:
```bash
curl http://localhost:8000/api/status
curl "http://localhost:8000/api/history/voltage?limit=50"
```

## 📊 Dashboard
`http://localhost:8000/` muestra:
- Tarjetas de estado: voltaje, corriente, SOC, SOH, capacidad restante, ciclos.
- Voltajes por celda con min/max/Δ.
- Gráfico del historial (voltaje / corriente / SOC) con pestañas.
- Badge de conexión y auto-refresh (estado 2 s, historial 10 s).

Funciona sin JavaScript externo: todo es vanilla JS + canvas servido por Flask.

## ⚙️ Ajustes (`.env`)
- `BMS_MAC_ADDRESS`: dirección MAC del BMS.
- `BMS_SLAVE_ADDR`: dirección esclava Modbus.
- `BMS_POLLING_INTERVAL`: segundos entre lecturas.
- `FLASK_PORT`, `FLASK_DEBUG`: servidor web.

## 🧪 Tests y typecheck
```bash
python3 -m mypy      # typecheck (config en mypy.ini)
python3 -m pytest     # tests (config en pytest.ini)
```

## 📈 Visualización de datos
Además del dashboard, los CSV de `data/` pueden abrirse con Excel, LibreOffice
Calc o cualquier herramienta de análisis (pandas, Grafana, etc.).
