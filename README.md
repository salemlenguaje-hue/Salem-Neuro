# SALEM Neurociencia V2 — Trazabilidad 0.2

Prototipo en Python 3 con biblioteca estándar; pensado para poder ejecutarse también en Termux. No es un sistema de seguridad certificado ni un experimento sobre consciencia.

## Prueba rápida

```bash
python trazas_salem.py demo --dir experimento_demo
python trazas_salem.py auditar --dir experimento_demo
python -m unittest -v test_trazas_salem.py
python -m unittest -v test_adversarial_salem.py
```

## Uso básico

```bash
python trazas_salem.py iniciar --dir corrida_001 --architecture A --task T1 --seed 123
python trazas_salem.py evento --dir corrida_001 --tipo data_generated --payload '{"dataset_id":"T1-v1","rows":1000}'
python trazas_salem.py evento --dir corrida_001 --tipo run_completed --payload '{"status":"completed"}'
python trazas_salem.py auditar --dir corrida_001
```

Después de cerrar la corrida, exportá un recibo a una ubicación separada:

```bash
python trazas_salem.py sellar --dir corrida_001 --anchor /ruta_separada/anchors/corrida_001.json
python trazas_salem.py verificar-anclaje --dir corrida_001 --anchor /ruta_separada/anchors/corrida_001.json
```

**El recibo sólo funciona como anclaje externo si se conserva independientemente y el atacante no puede reescribirlo.** Si el registro y el recibo son modificables por el mismo agente, éste puede reconstruir ambos. Copiar el recibo a otro soporte, repositorio remoto protegido o sistema de firma/tiempo confiable fortalece el modelo de confianza; la herramienta no configura automáticamente esas protecciones.

## Qué cambia en 0.2

- Normalización recursiva NFC de cadenas y claves antes de serializar; se rechazan colisiones de claves causadas por la normalización.
- `flush()` + `os.fsync()` en escrituras y sincronización de directorio de mejor esfuerzo tras reemplazos. La durabilidad final depende del sistema operativo, sistema de archivos, dispositivo y hardware.
- Comando para exportar y verificar un recibo de anclaje que cubre hash exacto del manifiesto, cantidad de eventos y hash final de la cadena.
- Suite adversarial: alteración de payload, eliminación, reordenamiento, recálculo quirúrgico y reescritura total coherente.

## Límites importantes

- `json.dumps(sort_keys=True, separators=...)` más NFC **no implementa RFC 8785/JCS**. La serialización está definida para esta implementación Python. Para intercambio verificable entre lenguajes hay que implementar/adoptar JCS o definir una especificación de datos más restrictiva.
- No se prohíben los números de punto flotante JSON. Para valores críticos que deban reproducirse entre implementaciones, preferir enteros en unidades definidas o cadenas decimales con formato especificado.
- SHA-256 y el encadenamiento detectan alteraciones bajo el modelo indicado; no prueban que los datos sean verdaderos, que un evento haya ocurrido realmente, ni quién lo escribió.
- El recibo no está firmado. No autentica autoría ni crea una marca temporal confiable.
- No hay bloqueo para escritores concurrentes, validación exhaustiva de esquema ni garantías de durabilidad absoluta. No guardar secretos ni datos personales innecesarios.
- La prueba de reescritura total que pasa la auditoría interna es intencional: documenta la frontera de v0.1/0.2, no un defecto accidental del test.

## Archivos

- `trazas_salem.py`: implementación 0.2.
- `trazas_salem_v01.py`: copia de referencia de la implementación 0.1 extraída del paquete previo.
- `test_trazas_salem.py`: pruebas funcionales, normalización y anclaje.
- `test_adversarial_salem.py`: batería de ataques reproducibles.
- `README.md`: guía y límites.
