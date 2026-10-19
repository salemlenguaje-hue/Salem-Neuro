#!/usr/bin/env python3
"""SALEM Neurociencia V2: trazabilidad 0.2. Biblioteca estándar de Python."""
import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import unicodedata
from pathlib import Path

SCHEMA = "1.1"
ANCHOR_SCHEMA = "SALEM-ANCHOR-1"
MANIFEST = "manifest.json"
EVENTS = "events.jsonl"
GENESIS = "GENESIS"


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def normalize_strings(obj):
    """Normaliza recursivamente valores y claves de texto a Unicode NFC."""
    if isinstance(obj, str):
        return unicodedata.normalize("NFC", obj)
    if isinstance(obj, list):
        return [normalize_strings(x) for x in obj]
    if isinstance(obj, dict):
        out = {}
        for key, value in obj.items():
            if not isinstance(key, str):
                raise TypeError("Las claves de objetos JSON deben ser texto.")
            nk = unicodedata.normalize("NFC", key)
            if nk in out:
                raise ValueError(f"Colisión de claves después de normalizar NFC: {nk!r}")
            out[nk] = normalize_strings(value)
        return out
    if obj is None or isinstance(obj, (bool, int, float)):
        return obj
    raise TypeError(f"Tipo no serializable admitido: {type(obj).__name__}")


def canonical(obj):
    """Serialización determinista dentro de esta implementación Python; no declara JCS/RFC 8785."""
    return json.dumps(normalize_strings(obj), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha(text):
    return sha_bytes(text.encode("utf-8"))


def fsync_directory(directory):
    """Mejor esfuerzo: algunos sistemas/plataformas no permiten fsync de directorios."""
    flags = getattr(os, "O_RDONLY", 0) | getattr(os, "O_DIRECTORY", 0)
    fd = None
    try:
        fd = os.open(str(directory), flags)
        os.fsync(fd)
        return True
    except (OSError, AttributeError):
        return False
    finally:
        if fd is not None:
            os.close(fd)


def durable_write(path, text, append=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    with path.open(mode, encoding="utf-8", newline="\n") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    fsync_directory(path.parent)


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with tmp.open("w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        fsync_directory(path.parent)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def load_manifest(d):
    p = d / MANIFEST
    if not p.exists():
        raise FileNotFoundError(f"No existe {p}; ejecutá iniciar primero.")
    return json.loads(p.read_text(encoding="utf-8"))


def write_manifest(d, obj):
    atomic_write(d / MANIFEST, json.dumps(normalize_strings(obj), ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def read_events(path):
    events, issues = [], []
    if not path.exists():
        return events, [f"No existe {path.name}."]
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        return [], [f"No se pudo leer {path.name}: {exc}"]
    for n, line in enumerate(lines, 1):
        if not line.strip():
            issues.append(f"Línea {n}: línea vacía inesperada.")
            continue
        try:
            e = json.loads(line)
            if not isinstance(e, dict):
                raise ValueError("el evento no es un objeto")
            e = normalize_strings(e)
            e["_line"] = n
            events.append(e)
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            issues.append(f"Línea {n}: registro inválido: {exc}")
    return events, issues


def append_event(d, event_type, payload):
    m = load_manifest(d)
    path = d / m.get("events_file", EVENTS)
    events, issues = read_events(path)
    if issues:
        raise RuntimeError("No se agrega a un registro con errores: " + "; ".join(issues))
    # No se permite continuar silenciosamente después de un evento de cierre.
    if events and events[-1].get("event_type") == "run_completed":
        raise RuntimeError("La corrida está cerrada con run_completed; no se agregan más eventos.")
    payload = normalize_strings(payload)
    prev = events[-1].get("event_hash", GENESIS) if events else GENESIS
    event = {
        "schema_version": SCHEMA, "experiment_id": m["experiment_id"],
        "run_id": m["run_id"], "sequence": len(events) + 1,
        "timestamp_utc": now(), "event_type": normalize_strings(event_type),
        "payload": payload, "previous_event_hash": prev
    }
    event["event_hash"] = sha(canonical(event))
    durable_write(path, canonical(event) + "\n", append=True)
    return event


def start(d, experiment_id, architecture, task, seed, code_version):
    d.mkdir(parents=True, exist_ok=True)
    if (d / MANIFEST).exists() or (d / EVENTS).exists():
        raise FileExistsError("El directorio ya contiene archivos de ejecución; no se sobrescribe.")
    m = {
        "schema_version": SCHEMA, "experiment_id": normalize_strings(experiment_id), "run_id": d.name,
        "created_at_utc": now(), "architecture_id": normalize_strings(architecture), "task_id": normalize_strings(task),
        "seed": seed, "code_version": normalize_strings(code_version), "hash_algorithm": "SHA-256",
        "event_serialization": "Python JSON sorted keys + compact separators; NFC strings; UTF-8",
        "unicode_normalization": "NFC", "events_file": EVENTS, "status": "initialized",
        "durability": "file fsync + best-effort parent-directory fsync; platform dependent"
    }
    write_manifest(d, m)
    durable_write(d / EVENTS, "")
    append_event(d, "run_started", {
        "architecture_id": architecture, "task_id": task,
        "seed": seed, "code_version": code_version
    })
    return m


def audit(d):
    m = load_manifest(d)
    events, issues = read_events(d / m.get("events_file", EVENTS))
    prev, seq = GENESIS, 1
    for e in events:
        line = e.pop("_line")
        if e.get("schema_version") != SCHEMA:
            issues.append(f"Línea {line}: schema_version inesperada.")
        if e.get("sequence") != seq:
            issues.append(f"Línea {line}: secuencia esperada {seq}, hallada {e.get('sequence')}.")
        if e.get("previous_event_hash") != prev:
            issues.append(f"Línea {line}: enlace al evento anterior incorrecto.")
        stored = e.get("event_hash")
        body = dict(e)
        body.pop("event_hash", None)
        try:
            calculated = sha(canonical(body))
        except (TypeError, ValueError) as exc:
            calculated = None
            issues.append(f"Línea {line}: no se pudo calcular hash: {exc}")
        if stored != calculated:
            issues.append(f"Línea {line}: event_hash no coincide; registro modificado o corrupto.")
        if e.get("experiment_id") != m.get("experiment_id"):
            issues.append(f"Línea {line}: experiment_id no coincide con el manifiesto.")
        if e.get("run_id") != m.get("run_id"):
            issues.append(f"Línea {line}: run_id no coincide con el manifiesto.")
        prev, seq = stored, seq + 1
    if not events:
        issues.append("No hay eventos registrados.")
    return {"ok": not issues, "event_count": len(events),
            "last_event_hash": events[-1].get("event_hash") if events else None,
            "issues": issues}


def anchor_core(d, audit_result):
    manifest_bytes = (d / MANIFEST).read_bytes()
    return {
        "anchor_schema": ANCHOR_SCHEMA,
        "run_id": load_manifest(d)["run_id"],
        "manifest_sha256": sha_bytes(manifest_bytes),
        "events_file": load_manifest(d).get("events_file", EVENTS),
        "event_count": audit_result["event_count"],
        "last_event_hash": audit_result["last_event_hash"],
        "anchored_at_utc": now()
    }


def create_anchor(d, anchor_path):
    result = audit(d)
    if not result["ok"]:
        raise RuntimeError("No se sella una corrida cuya auditoría interna falla: " + "; ".join(result["issues"]))
    core = anchor_core(d, result)
    core["integrity_root"] = sha(canonical(core))
    atomic_write(anchor_path, json.dumps(core, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    return core


def verify_anchor(d, anchor_path):
    issues = []
    try:
        anchor = json.loads(anchor_path.read_text(encoding="utf-8"))
        if not isinstance(anchor, dict):
            raise ValueError("el anclaje no es un objeto JSON")
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        return {"ok": False, "issues": [f"No se pudo leer el anclaje: {exc}"]}
    stored_root = anchor.get("integrity_root")
    core = dict(anchor)
    core.pop("integrity_root", None)
    if stored_root != sha(canonical(core)):
        issues.append("El integrity_root del anclaje no coincide; el recibo fue alterado o está corrupto.")
    internal = audit(d)
    if not internal["ok"]:
        issues.append("La auditoría interna falla: " + "; ".join(internal["issues"]))
    try:
        current_manifest_hash = sha_bytes((d / MANIFEST).read_bytes())
        m = load_manifest(d)
        if anchor.get("run_id") != m.get("run_id"):
            issues.append("run_id no coincide con el anclaje.")
        if anchor.get("manifest_sha256") != current_manifest_hash:
            issues.append("manifest_sha256 no coincide con el anclaje.")
        if anchor.get("events_file") != m.get("events_file", EVENTS):
            issues.append("events_file no coincide con el anclaje.")
        if anchor.get("event_count") != internal["event_count"]:
            issues.append("event_count no coincide con el anclaje.")
        if anchor.get("last_event_hash") != internal["last_event_hash"]:
            issues.append("last_event_hash no coincide con el anclaje.")
    except (OSError, ValueError, KeyError) as exc:
        issues.append(f"No se pudo comparar el anclaje: {exc}")
    return {"ok": not issues, "issues": issues, "internal_audit_ok": internal["ok"]}


def demo(d):
    if d.exists() and any(d.iterdir()):
        raise FileExistsError(f"{d} existe y no está vacío; elegí otro directorio.")
    start(d, "SALEM-NEURO-M11-V2", "prototype-not-a-neural-model",
          "traceability-self-test", 12345, "trace-recorder-0.2.0")
    append_event(d, "data_generated", {
        "dataset_id": "synthetic-demo-001", "rows": 12,
        "purpose": "self-test only; not scientific evidence"
    })
    append_event(d, "intervention_requested", {
        "intervention_id": "demo-block-001", "target": "module_A_to_module_B", "requested": True
    })
    append_event(d, "intervention_applied", {
        "intervention_id": "demo-block-001", "target": "module_A_to_module_B",
        "applied": True, "verification": "simulated-demo-only"
    })
    append_event(d, "metric_computed", {
        "metric_name": "placeholder_metric", "value": None,
        "status": "not_computed", "reason": "schema demonstration only"
    })
    append_event(d, "run_completed", {"status": "completed_demo", "scientific_claims": False})


def main():
    p = argparse.ArgumentParser(description="SALEM Neurociencia V2: trazador y auditor 0.2")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("iniciar")
    a.add_argument("--dir", required=True); a.add_argument("--experiment-id", default="SALEM-NEURO-M11-V2")
    a.add_argument("--architecture", default="pending"); a.add_argument("--task", default="pending")
    a.add_argument("--seed", type=int, default=1); a.add_argument("--code-version", default="trace-recorder-0.2.0")
    b = sub.add_parser("evento"); b.add_argument("--dir", required=True); b.add_argument("--tipo", required=True)
    b.add_argument("--payload", default="{}")
    c = sub.add_parser("auditar"); c.add_argument("--dir", required=True)
    e = sub.add_parser("demo"); e.add_argument("--dir", required=True)
    s = sub.add_parser("sellar"); s.add_argument("--dir", required=True); s.add_argument("--anchor", required=True)
    v = sub.add_parser("verificar-anclaje"); v.add_argument("--dir", required=True); v.add_argument("--anchor", required=True)
    x = p.parse_args(); d = Path(x.dir)
    try:
        if x.cmd == "iniciar":
            m = start(d, x.experiment_id, x.architecture, x.task, x.seed, x.code_version)
            print("Ejecución iniciada:", m["experiment_id"], "/", m["run_id"])
        elif x.cmd == "evento":
            payload = json.loads(x.payload)
            if not isinstance(payload, dict): raise ValueError("--payload debe ser un objeto JSON.")
            ev = append_event(d, x.tipo, payload)
            print("Evento agregado:", ev["sequence"], ev["event_type"], "hash:", ev["event_hash"])
        elif x.cmd == "demo":
            demo(d); r = audit(d)
            print("Demo técnica creada; no contiene resultados científicos.")
            print("AUDITORÍA:", "OK" if r["ok"] else "FALLO", "| eventos:", r["event_count"])
            for issue in r["issues"]: print("-", issue)
            sys.exit(0 if r["ok"] else 2)
        elif x.cmd == "sellar":
            a = create_anchor(d, Path(x.anchor))
            print("Recibo de anclaje exportado:", x.anchor)
            print("Raíz de integridad:", a["integrity_root"])
            print("IMPORTANTE: guardá el recibo fuera del directorio de corrida y protegelo independientemente.")
        elif x.cmd == "verificar-anclaje":
            r = verify_anchor(d, Path(x.anchor))
            print("VERIFICACIÓN DE ANCLAJE:", "OK" if r["ok"] else "FALLO")
            print("Auditoría interna:", "OK" if r.get("internal_audit_ok") else "FALLO")
            for issue in r["issues"]: print("-", issue)
            sys.exit(0 if r["ok"] else 2)
        else:
            r = audit(d)
            print("AUDITORÍA:", "OK" if r["ok"] else "FALLO")
            print("Eventos:", r["event_count"])
            print("Último hash:", r["last_event_hash"])
            for issue in r["issues"]: print("-", issue)
            sys.exit(0 if r["ok"] else 2)
    except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
        print("ERROR:", exc, file=sys.stderr); sys.exit(1)

if __name__ == "__main__":
    main()
