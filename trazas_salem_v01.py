#!/usr/bin/env python3
"""SALEM Neurociencia V2: registrador y auditor de trazas. Solo biblioteca estándar."""
import argparse, datetime as dt, hashlib, json, os, sys
from pathlib import Path

SCHEMA = "1.0"
MANIFEST = "manifest.json"
EVENTS = "events.jsonl"
GENESIS = "GENESIS"

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def atomic_write(path, text):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)

def load_manifest(d):
    p = d / MANIFEST
    if not p.exists():
        raise FileNotFoundError(f"No existe {p}; ejecutá iniciar primero.")
    return json.loads(p.read_text(encoding="utf-8"))

def write_manifest(d, obj):
    atomic_write(d / MANIFEST, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")

def read_events(path):
    events, issues = [], []
    if not path.exists():
        return events, [f"No existe {path.name}."]
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            issues.append(f"Línea {n}: línea vacía inesperada.")
            continue
        try:
            e = json.loads(line)
            if not isinstance(e, dict):
                raise ValueError("el evento no es un objeto")
            e["_line"] = n
            events.append(e)
        except (json.JSONDecodeError, ValueError) as exc:
            issues.append(f"Línea {n}: registro inválido: {exc}")
    return events, issues

def append_event(d, event_type, payload):
    m = load_manifest(d)
    path = d / m.get("events_file", EVENTS)
    events, issues = read_events(path)
    if issues:
        raise RuntimeError("No se agrega a un registro con errores: " + "; ".join(issues))
    prev = events[-1].get("event_hash", GENESIS) if events else GENESIS
    event = {
        "schema_version": SCHEMA, "experiment_id": m["experiment_id"],
        "run_id": m["run_id"], "sequence": len(events) + 1,
        "timestamp_utc": now(), "event_type": event_type,
        "payload": payload, "previous_event_hash": prev
    }
    event["event_hash"] = sha(canonical(event))
    with path.open("a", encoding="utf-8") as f:
        f.write(canonical(event) + "\n")
    return event

def start(d, experiment_id, architecture, task, seed, code_version):
    d.mkdir(parents=True, exist_ok=True)
    if (d / MANIFEST).exists() or (d / EVENTS).exists():
        raise FileExistsError("El directorio ya contiene archivos de ejecución; no se sobrescribe.")
    m = {
        "schema_version": SCHEMA, "experiment_id": experiment_id, "run_id": d.name,
        "created_at_utc": now(), "architecture_id": architecture, "task_id": task,
        "seed": seed, "code_version": code_version, "hash_algorithm": "SHA-256",
        "event_serialization": "UTF-8 JSON; sorted keys; compact separators",
        "events_file": EVENTS, "status": "initialized"
    }
    write_manifest(d, m)
    (d / EVENTS).write_text("", encoding="utf-8")
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
        if stored != sha(canonical(body)):
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

def demo(d):
    if d.exists() and any(d.iterdir()):
        raise FileExistsError(f"{d} existe y no está vacío; elegí otro directorio.")
    start(d, "SALEM-NEURO-M11-V2", "prototype-not-a-neural-model",
          "traceability-self-test", 12345, "trace-recorder-0.1.0")
    append_event(d, "data_generated", {
        "dataset_id": "synthetic-demo-001", "rows": 12,
        "purpose": "self-test only; not scientific evidence"
    })
    append_event(d, "intervention_requested", {
        "intervention_id": "demo-block-001", "target": "module_A_to_module_B",
        "requested": True
    })
    append_event(d, "intervention_applied", {
        "intervention_id": "demo-block-001", "target": "module_A_to_module_B",
        "applied": True, "verification": "simulated-demo-only"
    })
    append_event(d, "metric_computed", {
        "metric_name": "placeholder_metric", "value": None,
        "status": "not_computed", "reason": "schema demonstration only"
    })
    append_event(d, "run_completed", {
        "status": "completed_demo", "scientific_claims": False
    })

def main():
    p = argparse.ArgumentParser(description="SALEM Neurociencia V2: trazador y auditor")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("iniciar")
    a.add_argument("--dir", required=True); a.add_argument("--experiment-id", default="SALEM-NEURO-M11-V2")
    a.add_argument("--architecture", default="pending"); a.add_argument("--task", default="pending")
    a.add_argument("--seed", type=int, default=1); a.add_argument("--code-version", default="trace-recorder-0.1.0")
    b = sub.add_parser("evento"); b.add_argument("--dir", required=True); b.add_argument("--tipo", required=True)
    b.add_argument("--payload", default="{}")
    c = sub.add_parser("auditar"); c.add_argument("--dir", required=True)
    e = sub.add_parser("demo"); e.add_argument("--dir", required=True)
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
            demo(d)
            r = audit(d)
            print("Demo técnica creada; no contiene resultados científicos.")
            print("AUDITORÍA:", "OK" if r["ok"] else "FALLO", "| eventos:", r["event_count"])
            for issue in r["issues"]: print("-", issue)
            sys.exit(0 if r["ok"] else 2)
        else:
            r = audit(d)
            print("AUDITORÍA:", "OK" if r["ok"] else "FALLO")
            print("Eventos:", r["event_count"])
            print("Último hash:", r["last_event_hash"])
            for issue in r["issues"]: print("-", issue)
            sys.exit(0 if r["ok"] else 2)
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        print("ERROR:", exc, file=sys.stderr); sys.exit(1)

if __name__ == "__main__":
    main()
