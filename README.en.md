# SALEM Neuroscience V2 — Traceability 0.2

A Python 3 prototype designed to run on environments such as Android
with Termux. The traceability implementation uses the Python standard
library. The optional Ed25519 signing utility requires the OpenSSL
command-line tool.

This is not a certified security system or an experiment on consciousness.

## Quick start

Create a demonstration run, audit it, and execute the test suites:

```bash
python trazas_salem.py demo --dir experiment_demo
python trazas_salem.py auditar --dir experiment_demo
python -m unittest -v test_trazas_salem.py
python -m unittest -v test_adversarial_salem.py
python -m unittest -v test_firma_salem.py
```

## Basic usage

Create a run, append events, and audit the resulting record:

```bash
python trazas_salem.py iniciar --dir run_001 --architecture A --task T1 --seed 123

python trazas_salem.py evento --dir run_001 --tipo data_generated --payload '{"dataset_id":"T1-v1","rows":1000}'

python trazas_salem.py evento --dir run_001 --tipo run_completed --payload '{"status":"completed"}'

python trazas_salem.py auditar --dir run_001
```

After the run is complete, export an anchor receipt to a separate location:

```bash
python trazas_salem.py sellar --dir run_001 --anchor /separate/path/anchors/run_001.json

python trazas_salem.py verificar-anclaje --dir run_001 --anchor /separate/path/anchors/run_001.json
```

**The receipt acts as an external anchor only if it is preserved independently and the attacker cannot rewrite it.** If the same actor can modify both the event log and the receipt, that actor may reconstruct both. Keeping the receipt on a separately controlled medium or service can strengthen the trust model. The tool does not configure those protections automatically.

## Ed25519 signatures

The optional `firma_salem.py` utility signs the canonicalized receipt content with Ed25519 through OpenSSL.

Generate a key pair. Choose paths that do not already exist:

```bash
python firma_salem.py generar-claves --privada keys/salem_private.pem --publica keys/salem_public.pem
```

Create an anchor receipt first, then sign it:

```bash
python trazas_salem.py sellar --dir run_001 --anchor anchors/run_001.json

python firma_salem.py firmar --recibo anchors/run_001.json --privada keys/salem_private.pem --salida anchors/run_001.signature.json
```

Verify the signature using a public key obtained through an independently trusted channel:

```bash
python firma_salem.py verificar --recibo anchors/run_001.json --publica keys/salem_public.pem --firma anchors/run_001.signature.json
```

Protect the private key and keep it separate from public artifacts. The signing utility refuses to overwrite existing output files. A signature can authenticate receipt contents against a trusted public key, but it does not prove that the scientific data are true, that the recorded events actually occurred, or that the receipt existed at a particular time.

Do not trust a public key merely because it is distributed alongside the receipt it verifies. Public-key authenticity and private-key protection are part of the trust model.

## Changes in version 0.2

- Recursive NFC normalization of strings and keys before serialization; collisions caused by normalization are rejected.
- `flush()` and `os.fsync()` for writes, plus best-effort directory synchronization after replacements. Actual durability depends on the operating system, filesystem, device, and hardware.
- Commands to export and verify an anchor receipt covering the exact manifest hash, event count, and final chain hash.
- Adversarial tests for payload modification, event deletion, reordering, selective hash recalculation, and a complete internally consistent rewrite.

## Important limitations

- `json.dumps(sort_keys=True, separators=...)` combined with NFC normalization **does not implement RFC 8785/JCS**. Serialization is defined by this Python implementation. Cross-language verification requires adopting JCS or specifying a more restrictive data format.
- JSON floating-point numbers are not prohibited. For critical values that must be reproduced across implementations, prefer integers with defined units or decimal strings with a specified format.
- SHA-256 and hash chaining can detect alterations under the stated trust model. They do not establish data truth, prove that an event occurred, or identify its author.
- An unsigned anchor receipt does not authenticate authorship or provide a trusted timestamp.
- An Ed25519 signature verifies content against a trusted public key; it does not prove scientific validity or establish when the signed content existed. Independent timestamping or external anchoring may be needed for stronger evidence of existence at a particular time.
- There is no concurrent-writer locking, exhaustive schema validation, or absolute durability guarantee. Avoid storing secrets or unnecessary personal data.
- The test in which a complete rewritten history passes the internal audit is intentional. It documents the trust boundary of versions 0.1 and 0.2; it is not an accidental test failure.

## Files

- `trazas_salem.py`: version 0.2 traceability implementation.
- `trazas_salem_v01.py`: reference copy of the earlier version 0.1 implementation.
- `trazas_salem_v02.py`: additional version 0.2 source copy.
- `firma_salem.py`: Ed25519 receipt-signing and verification utility.
- `test_trazas_salem.py`: functional, normalization, and anchoring tests.
- `test_adversarial_salem.py`: reproducible adversarial test suite.
- `test_firma_salem.py`: signature verification and tampering tests.
- `README.md`: documentation in Spanish.
- `README.en.md`: English documentation.
