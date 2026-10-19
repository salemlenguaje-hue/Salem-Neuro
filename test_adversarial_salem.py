"""Batería adversarial. La reescritura total debe pasar la auditoría interna y fallar con anclaje preservado."""
import json
import tempfile
import unittest
from pathlib import Path
import trazas_salem as ts

class AdversarialTests(unittest.TestCase):
    def setUpRun(self, root):
        d = Path(root) / "run"
        ts.start(d, "EXP-ADV", "A", "T1", 7, "adversarial-test")
        for n in range(2, 6):
            ts.append_event(d, f"event_{n}", {"value": n, "note": f"event {n}"})
        ts.append_event(d, "run_completed", {"status": "test-complete"})
        return d

    def lines(self, d):
        return (d / ts.EVENTS).read_text(encoding="utf-8").splitlines()

    def save(self, d, lines):
        (d / ts.EVENTS).write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_1_payload_byte_change_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = self.setUpRun(tmp)
            lines = self.lines(d)
            lines[2] = lines[2].replace('"value":3', '"value":30')
            self.save(d, lines)
            r = ts.audit(d)
            self.assertFalse(r["ok"])
            self.assertTrue(any("Línea 3: event_hash no coincide" in issue for issue in r["issues"]))

    def test_2_delete_intermediate_event_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = self.setUpRun(tmp)
            lines = self.lines(d)
            del lines[1]
            self.save(d, lines)
            r = ts.audit(d)
            self.assertFalse(r["ok"])
            self.assertTrue(any("secuencia esperada 2, hallada 3" in issue for issue in r["issues"]))
            self.assertTrue(any("enlace al evento anterior incorrecto" in issue for issue in r["issues"]))

    def test_3_swap_events_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = self.setUpRun(tmp)
            lines = self.lines(d)
            lines[2], lines[3] = lines[3], lines[2]
            self.save(d, lines)
            r = ts.audit(d)
            self.assertFalse(r["ok"])
            self.assertTrue(any("secuencia esperada" in issue for issue in r["issues"]))
            self.assertTrue(any("enlace al evento anterior incorrecto" in issue for issue in r["issues"]))

    def test_4_rehash_only_changed_event_breaks_next_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = self.setUpRun(tmp)
            lines = self.lines(d)
            event = json.loads(lines[2])
            event["payload"]["note"] = "altered"
            event.pop("event_hash")
            event["event_hash"] = ts.sha(ts.canonical(event))
            lines[2] = ts.canonical(event)
            self.save(d, lines)
            r = ts.audit(d)
            self.assertFalse(r["ok"])
            self.assertFalse(any("Línea 3: event_hash no coincide" in issue for issue in r["issues"]))
            self.assertTrue(any("Línea 4: enlace al evento anterior incorrecto" in issue for issue in r["issues"]))

    def test_5_full_rewrite_passes_internal_audit_but_fails_preserved_anchor(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = self.setUpRun(tmp)
            anchor = Path(tmp) / "independent" / "anchor.json"
            ts.create_anchor(d, anchor)
            events = [json.loads(line) for line in self.lines(d)]
            previous = events[0]["event_hash"]
            for i in range(1, len(events)):
                event = events[i]
                event["payload"] = dict(event.get("payload", {}))
                event["payload"]["history_rewritten"] = True
                event["previous_event_hash"] = previous
                event.pop("event_hash", None)
                event["event_hash"] = ts.sha(ts.canonical(event))
                previous = event["event_hash"]
            self.save(d, [ts.canonical(event) for event in events])
            self.assertTrue(ts.audit(d)["ok"], "la nueva historia debería ser internamente coherente")
            anchored = ts.verify_anchor(d, anchor)
            self.assertFalse(anchored["ok"])
            self.assertTrue(any("last_event_hash no coincide" in issue for issue in anchored["issues"]))

if __name__ == "__main__":
    unittest.main(verbosity=2)
