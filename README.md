# Monitoreo Bluetooth BMS LiFePO₄

## 📋 Requisitos
- Python 3.8+
- Bluetooth LE (adaptador `hci0` activo)
- Dependencia python: `bleak`

```bash
pip install -r requirements.txt   # o: pip install bleak
```

## 🚀 Cómo iniciar
```bash
python3 bms_ble_reader.py
```

El script:
- Se conecta al dispositivo `AA:BB:CC:DD:EE:FF` (CDZG202512050020000327).
- Lee dos características vendor‑specific:
  - `00002760-08c2-11e1-9073-0e8ac72e0001` → Voltaje/Corriente.
  - `00002760-08c2-11e1-9073-0e8ac72e0002` → SOC/Temperatura.
- Guarda cada lectura en `data/*.csv` con timestamps.

## ⚙️ Ajustes
- **MAC**: Cambia `MAC` si tu batería tiene otra dirección.
- **UUIDs**: Modifica `CHARACTERISTICS` si el manual del fabricante indica diferentes UUIDs.
- **Parsing**: Adapta los cálculos de `voltage`, `current`, `soc` y `temperature` al formato exacto que tu BMS envíe (consultar la hoja de datos).

## 📈 Visualización
Los CSV generados pueden abrirse con Excel, LibreOffice Calc o cualquier herramienta de análisis (pandas, Grafana, etc.).

---

¡Listo! Ahora tienes un proyecto completo para monitorizar tu batería LiFePO₄ desde Linux vía Bluetooth. 🚀