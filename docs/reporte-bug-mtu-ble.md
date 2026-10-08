# Reporte de bug: lecturas BLE del BMS se pierden por fragmentación de notificación

Fecha: 2026-10-07
Alcance: `src/modules/bms/infrastructure/adapters/bleak_bms_repository.py`
Estado: diagnosticado con evidencia, pendiente de fix

## Síntoma

`/api/status` y `/api/history` ya responden 200 (bug resuelto en `6fd030b`), pero
`connected` se queda en `false` y el historial nunca crece: **no llega ni una sola
lectura real del BMS**. `get_latest_reading()` devuelve `None` de forma permanente.

## Causa raíz 1 — no hay negociación de MTU (y ya no se puede hacer con la API actual)

La lectura pide `REG_STATUS_COUNT = 0x003B` = **59 registros**. La respuesta Modbus RTU
mide:

```
slave(1) + func(1) + byteCount(1) + datos(59*2=118) + CRC(2) = 123 bytes
```

El ATT MTU por defecto es 23, así que el payload máximo por notificación es
**23 - 3 = 20 bytes**. Una lectura ocupa por tanto:

```
ceil(123 / 20) = 7 notificaciones
```

Verificado en el entorno con la versión instalada:

```
bleak 3.0.1
BleakClient -> metodos: address, backend_id, connect, disconnect, is_connected,
              mtu_size, name, pair, read_gatt_char, services, start_notify,
              stop_notify, write_gatt_char, write_gatt_descriptor
request_mtu: NO EXISTE
```

**`bleak` 3.0.1 eliminó `request_mtu`.** No hay API pública para negociar MTU. Y el
backend BlueZ de Linux devuelve siempre el mínimo:

```python
# bleak/backends/bluezdbus/client.py
@property
def mtu_size(self) -> int:
    if self._mtu_size is None:
        warnings.warn("Using default MTU value. Call _acquire_mtu() or set _mtu_size first ...")
        return 23
    return self._mtu_size
```

Conclusión: en Linux no se puede subir el MTU por vía pública. **La fragmentación es
inevitable y hay que soportarla bien.** La negociación de MTU pasa a ser una
optimización opcional, no la solución.

## Causa raíz 2 — `handle_notify` confunde una continuación con una cabecera (ESTA ES LA QUE MATA LA LECTURA)

`ModbusCollector.handle_notify` (líneas 27-43) decide si un fragmento es cabecera
mirando los dos primeros bytes:

```python
def handle_notify(self, _sender, data: bytearray) -> None:
    if len(data) >= 2 and data[0] == self.slave_addr and data[1] in (FUNC_READ, FUNC_READ | 0x80):
        self._buf = bytearray(data)      # <-- REINICIA el buffer
    elif self._buf: self._buf.extend(data)
    else: return
    ...
```

El problema: **el payload también contiene bytes que pueden coincidir con la cabecera.**
Los valores son enteros de 16 bits big-endian, así que un fragmento de continuación
puede empezar por `01 03` o `01 83` sin ser una cabecera. Cuando eso pasa, el buffer
se reinicia a mitad de frame y **la lectura entera se pierde**.

### Reproducción

Como la cabecera ocupa 3 bytes, los límites de 20 caen en offsets **impares** del payload
(17, 37, 57, 77, 97). `payload[17]` es el byte bajo del registro 8 y `payload[18]` el byte
alto del registro 9. Basta con que el registro 8 termine en `0x01` (p. ej. celda de
**3.329 V** = `0x0D01`) y el registro 9 empiece por `0x03`:

```
frag@  0: 0x1 0x3     <- cabecera, OK
frag@ 20: 0x1 0x3     <- REINICIA EL BUFFER, se pierde todo

frames ensamblados: 0   (esperado 1)
buffer residual: 103 bytes
RESULTADO: LECTURA PERDIDA -> request() agota 6s y devuelve None
```

Con datos sintéticos (payload `bytes(range(118))`) el bug **no** se reproduce. Por eso
pasa desapercibido en pruebas y aparece "a veces" en producción: depende del valor de los
registros en ese instante. Con voltajes de celda normales (3.2-3.4 V) la colisión es
frecuente.

Consecuencia en el bucle: `request()` hace `wait_for(self._event.wait(), 6.0)`, agota,
devuelve `None`, y `start_polling` sigue sin guardar nada. Como el residuo nunca se
limpia en el timeout, el bug se auto perpetúa.

## Fix propuesto

### 1. Reensamblado por máquina de estados (obligatorio)

Dejar de deducir "cabecera o continuación" por los bytes. Usar un flag explícito:

- `self._in_frame = False` inicialmente.
- Si **no** estamos en frame: exigir cabecera (`data[0] == slave_addr` y
  `data[1] in (0x03, 0x83)`), iniciar buffer, poner `_in_frame = True`.
  Si no es cabecera, descartar el fragmento.
- Si **estamos** en frame: **acumular siempre**, nunca reiniciar por coincidencia de bytes.
- Al completar (`len >= 5 + byte_count`): emitir frame, limpiar, `_in_frame = False`.
- Respuesta de excepción (`0x83`): limpiar y volver a `_in_frame = False`.

### 2. Limpiar el buffer cuando la petición expira

`request()` debe descartar el residuo en el `except asyncio.TimeoutError` para que un
frame perdido no contamine el siguiente.

### 3. MTU como optimización, con fallback

Intentar negociar MTU si el backend lo expone de algún modo, midiendo el resultado con
`mtu_size`; si no se puede (caso BlueZ actual), **continuar con fragmentación sin
fallar**. Ningún camino MTU debe poder tumbar la lectura. Comentar con claridad que en
Linux el MTU efectivo es 23 y que el diseño debe asumir fragmentación.

## Criterios de aceptación

1. Un frame de 123 bytes troceado en 7 notificaciones de 20 **se ensambla 1 vez**,
   incluso si un fragmento de continuación empieza por `01 03` o `01 83`
   (usar los valores del caso de reproducción: reg8=`0x0D01`, reg9=`0x0383`).
2. Varios frames consecutivos en el mismo canal se leen todos, sin residuo entre ellos.
3. Fragmento basura sin cabecera se descarta sin romper el estado.
4. Tras un timeout, el siguiente frame válido se ensambla igual (sin contaminación).
5. La MTU se consulta pero su fallo no rompe nada.
6. Prueba con `ModbusCollector` **sin BLE**: invocar `handle_notify` a mano con
   `bytearray`, sin hardware y sin red.

## Fuera de alcance

- No tocar `_parse_status`, `_build_read_cmd`, `_crc_modbus` ni el mapeo de registros.
- No tocar la vista Flask ni los handlers CQRS.
- No refactorizar la arquitectura.
- El RSSI de -88 dBm y la validación CRC de la respuesta Modbus son bugs separados
  (registrados como #2 y #4 del plan `adc52f07`); no mezclarlos en este fix.