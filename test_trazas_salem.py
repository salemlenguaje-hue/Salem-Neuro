import json
import tempfile
import unittest
import unicodedata
from pathlib import Path
import trazas_salem as ts

class Tests(unittest.TestCase):
    def make_run(self, root, name="run"):
        d = Path(root) / name
        ts.start(d, "EXP", "A", "T1", 1, "test")
        ts.append_event(d, "event_2", {"value": 2})
        ts.append_event(d, "event_3", {"value": 3, "note": "original"})
        ts.append_event(d, "event_4", {"value": 4})
        ts.append_event(d, "run_completed", {"status": "test"})
        return d

    def read_lines(self, d):
        return (d / ts.EVENTS).read_text(encoding="utf-8").splitlines()

    def write_lines(self, d, lines):
        (d / ts.EVENTS).write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_valid(self):
        with tempfile.TemporaryDirectory() as t:
            d = self.make_run(t)
            self.assertTrue(ts.audit(d)["ok"])

    def test_corruption_payload(self):
        with tempfile.TemporaryDirectory() as t:
            d = self.make_run(t)
            lines = self.read_lines(d)
            lines[2] = lines[2].replace('"value":3', '"value":33')
            self.write_lines(d, lines)
            result = ts.audit(d)
            self.assertFalse(result["ok"])
            self.assertTrue(any("Línea 3: event_hash no coincide" in x for x in result["issues"]))

    def test_event_deletion(self):
        with tempfile.TemporaryDirectory() as t:
            d = self.make_run(t)
            lines = self.read_lines(d)
            del lines[1]
            self.write_lines(d, lines)
            result = ts.audit(d)
            self.assertFalse(result["ok"])
            self.assertTrue(any("secuencia esperada 2, hallada 3" in x for x in result["issues"]))
            self.assertTrue(any("enlace al evento anterior incorrecto" in x for x in result["issues"]))

    def test_reordering(self):
        with tempfile.TemporaryDirectory() as t:
            d = self.make_run(t)
            lines = self.read_lines(d)
            lines[2], lines[3] = lines[3], lines[2]
            self.write_lines(d, lines)
            result = ts.audit(d)
            self.assertFalse(result["ok"])
            self.assertTrue(any("secuencia esperada" in x for x in result["issues"]))
            self.assertTrue(any("enlace al evento anterior incorrecto" in x for x in result["issues"]))

    def test_surgical_hash_recalculation(self):
        with tempfile.TemporaryDirectory() as t:
            d = self.make_run(t)
            lines = self.read_lines(d)
            event = json.loads(lines[2])
            event["payload"]["note"] = "altered"
            event.pop("event_hash")
            event["event_hash"] = ts.sha(ts.canonical(event))
            lines[2] = ts.canonical(event)
            self.write_lines(d, lines)
            result = ts.audit(d)
            self.assertFalse(result["ok"])
            self.assertFalse(any("Línea 3: event_hash no coincide" in x for x in result["issues"]))
            self.assertTrue(any("Línea 4: enlace al evento anterior incorrecto" in x for x in result["issues"]))

    def test_full_history_rewrite_passes_internal_audit_but_fails_external_anchor(self):
        with tempfile.TemporaryDirectory() as t:
            d = self.make_run(t)
            anchor = Path(t) / "protected" / "anchor.json"
            ts.create_anchor(d, anchor)
            lines = self.read_lines(d)
            events = [json.loads(line) for line in lines]
            previous = events[0]["event_hash"]
            for index in range(1, len(events)):
                event = events[index]
                event["payload"] = dict(event.get("payload", {}))
                event["payload"]["history_rewritten"] = True
                event["previous_event_hash"] = previous
                event.pop("event_hash", None)
                event["event_hash"] = ts.sha(ts.canonical(event))
                previous = event["event_hash"]
                events[index] = event
            self.write_lines(d, [ts.canonical(event) for event in events])
            # La cadena nueva es internamente coherente: esto demuestra el límite del auditor sin anclaje.
            self.assertTrue(ts.audit(d)["ok"])
            # El recibo preservado independientemente detecta que la historia ya no coincide.
            anchored = ts.verify_anchor(d, anchor)
            self.assertFalse(anchored["ok"])
            self.assertTrue(any("last_event_hash no coincide" in x for x in anchored["issues"]))

    def test_nfc_equivalence(self):
        composed = "café"
        decomposed = unicodedata.normalize("NFD", composed)
        self.assertEqual(ts.canonical({"text": composed}), ts.canonical({"text": decomposed}))

    def test_anchor_detects_manifest_change(self):
        with tempfile.TemporaryDirectory() as t:
            d = self.make_run(t)
            anchor = Path(t) / "anchor.json"
            ts.create_anchor(d, anchor)
            manifest = d / ts.MANIFEST
            data = json.loads(manifest.read_text(encoding="utf-8"))
            data["task_id"] = "tampered-task"
            ts.write_manifest(d, data)
            result = ts.verify_anchor(d, anchor)
            self.assertFalse(result["ok"])
            self.assertTrue(any("manifest_sha256 no coincide" in x for x in result["issues"]))

if __name__ == "__main__":
    unittest.main(verbosity=2)
