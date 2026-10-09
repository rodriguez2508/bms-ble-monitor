# LiFePO₄ BMS Bluetooth Monitor

Read-only monitor for a PACE/BUKUNGO-style LiFePO₄ BMS over Bluetooth Low
Energy. It polls the BMS using Modbus RTU over GATT (function `0x03`, read-only),
stores the readings as CSV, and serves a live web dashboard with charts,
cell/temperature detail, protection flags, a charge-balance cycle log and
browser push alerts.

The BMS never receives write commands: the client only issues Modbus read
requests, so the battery configuration cannot be modified from here.

## Features

- **Read-only polling** — Modbus function `0x03` over BLE GATT notifications.
- **Live dashboard** — status cards (voltage, current, power, SOC, SOH,
  remaining capacity, cycles, estimated runtime), per-cell voltages, pack and
  cell temperatures, and decoded warning/protection/status flags.
- **Real-time push** — status is pushed over WebSocket every 2 s; history and
  the balance log refresh on an interval, with automatic browser live-reload in
  dev mode.
- **Charge-balance cycle log** — the server samples the pack during charging and
  records cell voltages, current, pack voltage and the raw balance registers to
  `data/balance_cycle.csv`, with automatic retention.
- **Browser push alerts** — low-SOC and high-SOC notifications via the Web Push
  API (VAPID), delivered even when the dashboard tab is closed (the browser must
  stay open).
- **Clean architecture** — domain / application (CQRS) / infrastructure split.

## Requirements

- Python 3.10+ (tested on 3.10)
- An active Bluetooth LE adapter (`hci0`)
- Linux with BlueZ (the reference environment); macOS/Windows are untested

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # then edit BMS_MAC_ADDRESS (and the rest)
PYTHONPATH=. python3 main.py
```

Then open <http://localhost:8000>.

`BMS_MAC_ADDRESS` has no default and must be set in `.env` (or the
environment). To find your BMS address:

```bash
bluetoothctl scan on        # look for your BMS name/address, then: scan off
```

> The BLE link is exclusive: only one process can talk to the BMS at a time.
> Stop the server before running the standalone logger in `tools/`.

## Configuration

All settings are environment variables (loaded from `.env`). See
[`.env.example`](.env.example) for a ready-to-copy template.

| Variable | Default | Description |
|----------|---------|-------------|
| `BMS_MAC_ADDRESS` | *(required)* | Bluetooth MAC address of the BMS |
| `BMS_SLAVE_ADDR` | `1` | Modbus slave address |
| `BMS_POLLING_INTERVAL` | `10` | Seconds between BLE polls |
| `FLASK_PORT` | `8000` | HTTP port |
| `FLASK_DEBUG` | `False` | Flask debug mode |
| `FLASK_RELOAD` | `False` | Auto-reload server on code changes (dev) |
| `BALANCE_LOG_ENABLED` | `true` | Enable the charge-balance cycle log |
| `BALANCE_LOG_INTERVAL` | `30` | Seconds between balance-log samples |
| `BALANCE_LOG_RETENTION_H` | `48` | Hours of balance log to keep |
| `BALANCE_LOG_FILE` | `balance_cycle.csv` | Balance log file name (under `data/`) |
| `VAPID_SUBJECT` | `mailto:admin@localhost` | VAPID contact (`mailto:` or URL) |
| `SOC_ALERT_PCT` | `10` | Low-SOC alert threshold (%) |
| `SOC_ALERT_HYSTERESIS` | `5` | Low-SOC re-arm band (percentage points) |
| `SOC_HIGH_ALERT_PCT` | `95` | High-SOC alert threshold (%) |
| `SOC_HIGH_HYSTERESIS` | `5` | High-SOC re-arm band (percentage points) |
| `ALERT_CHECK_INTERVAL` | `5` | Seconds between alert checks |
| `ALERT_STALE_SECONDS` | `60` | Ignore readings older than this |
| `PUSH_ON_START` | `true` | Send a push when the server starts |

## HTTP API

| Endpoint | Description |
|----------|-------------|
| `GET /` | Web dashboard (HTML) |
| `GET /api/status` | Latest reading: `{"connected": bool, "data": {...}|null}` |
| `GET /api/config` | Read-only BMS thresholds (protection/alarm values) |
| `GET /api/history/<metric>?limit=N` | CSV history; `metric` ∈ `voltage`, `current`, `power`, `soc` |
| `GET /api/balance?limit=N` | Charge-balance cycle log points |
| `GET /api/push/public_key` | VAPID application server key |
| `POST /api/push/subscribe` | Register a browser push subscription |
| `POST /api/push/unsubscribe` | Remove a push subscription |
| `POST /api/push/test` | Send a test push to all subscribers |
| `GET/POST /api/alerts/config` | Read/update alert thresholds |
| `WS /ws` | WebSocket: status pushed every 2 s |

Examples:

```bash
curl http://localhost:8000/api/status
curl "http://localhost:8000/api/history/voltage?limit=50"
curl -X POST http://localhost:8000/api/push/test
```

## Push alerts

Push notifications use the Web Push API with VAPID keys generated on first run
and stored in `data/vapid_keys.json`. Subscriptions are kept in
`data/push_subscriptions.json`.

To enable them:

1. Open the dashboard over **`http://localhost`** (Web Push requires a secure
   context; plain HTTP over a LAN IP will not work).
2. Click **Activate notifications** and grant the permission.
3. Click **Test** to send a test push.
4. Set the **minimum** and **maximum** SOC thresholds and save.

Each threshold fires once when crossed and re-arms after the hysteresis band, so
you do not get a storm of notifications around the boundary.

## Charge-balance cycle log

While polling, the server samples the pack to `data/balance_cycle.csv` (interval
configurable via `BALANCE_LOG_INTERVAL`, retention via
`BALANCE_LOG_RETENTION_H`). Each row records the timestamp, pack voltage and
current, SOC, per-cell voltages, the cell delta in mV, and the raw `reg9`–`reg13`
values with their hex form. The dashboard plots the delta against the 30 mV
balancing threshold and highlights rows where balancing is reported.

A standalone logger is also available as an offline tool (it owns the BLE link,
so stop the server first):

```bash
PYTHONPATH=. python3 tools/balance_logger.py --interval 30
```

## Testing

```bash
PYTHONPATH=. python3 -m pytest     # test suite
PYTHONPATH=. python3 -m mypy src tools main.py   # type check
```

## Project structure

```
src/modules/bms/
├── domain/            # entities, models and ports (pure)
│   ├── models/        # BmsReading, BmsConfig
│   └── ports/         # BmsRepository interface
├── application/       # use cases (CQRS) and services
│   ├── queries/       # status, history, config, balance-log handlers
│   └── services/      # SocAlertService
└── infrastructure/
    ├── adapters/      # BLE repository, balance log, push service
    └── entrypoints/   # Flask app, WebSocket, static dashboard
tools/                 # standalone read-only balance logger
```

## Privacy and data

- `data/` and `.env` are git-ignored. They hold the CSVs, VAPID keys, push
  subscriptions, alert configuration and your device MAC — none of it belongs in
  version control.
- `BMS_MAC_ADDRESS` has no default, so no specific device address ships in the
  code.
- The dashboard is served on `0.0.0.0`; if you expose it beyond localhost, put it
  behind a reverse proxy with authentication, since the API is unauthenticated.

## License

Not specified yet.
