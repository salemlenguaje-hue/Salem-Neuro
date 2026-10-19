#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Firma y verificación Ed25519 para recibos de SALEM Neurociencia.

La clave pública debe obtenerse por un canal de confianza independiente.
La firma autentica el contenido firmado; no demuestra que los datos sean
verdaderos ni acredita por sí sola la fecha de creación.
"""

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import trazas_salem as ts

ESQUEMA_FIRMA = "SALEM-ED25519-1"


def ejecutar_openssl(argumentos):
    """Ejecuta OpenSSL y explica los errores en español."""
    try:
        return subprocess.run(
            ["openssl", *argumentos],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("No se encontró OpenSSL en el sistema.") from exc
    except subprocess.CalledProcessError as exc:
        detalle = (exc.stderr or exc.stdout or "").strip()
        raise RuntimeError(
            "Falló OpenSSL" + (": " + detalle if detalle else ".")
        ) from exc


def escribir_nuevo(ruta, contenido, permisos=None):
    """Crea un archivo nuevo sin sobrescribir uno existente."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)

    # El modo exclusivo impide sobrescribir archivos existentes.
    descriptor = os.open(
        str(ruta),
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        permisos if permisos is not None else 0o644,
    )
    try:
        with os.fdopen(descriptor, "wb") as archivo:
            archivo.write(contenido)
            archivo.flush()
            os.fsync(archivo.fileno())
    except Exception:
        # Si falla la escritura, se elimina el archivo incompleto.
        try:
            ruta.unlink()
        except OSError:
            pass
        raise


def generar_claves(clave_privada, clave_publica):
    """Genera un par Ed25519 y protege la clave privada."""
    privada = Path(clave_privada)
    publica = Path(clave_publica)

    if privada.resolve() == publica.resolve():
        raise ValueError("Las rutas de las claves deben ser diferentes.")
    if privada.exists() or publica.exists():
        raise FileExistsError(
            "Una de las rutas ya existe. No se sobrescribió ningún archivo."
        )

    # Las claves se generan primero en una carpeta temporal.
    with tempfile.TemporaryDirectory(prefix="salem_claves_") as temporal:
        temporal = Path(temporal)
        priv_tmp = temporal / "privada.pem"
        pub_tmp = temporal / "publica.pem"

        ejecutar_openssl([
            "genpkey", "-algorithm", "ED25519",
            "-out", str(priv_tmp),
        ])
        ejecutar_openssl([
            "pkey", "-in", str(priv_tmp),
            "-pubout", "-out", str(pub_tmp),
        ])

        # La clave privada se crea con permisos restrictivos.
        escribir_nuevo(privada, priv_tmp.read_bytes(), 0o600)
        try:
            escribir_nuevo(publica, pub_tmp.read_bytes(), 0o644)
        except Exception:
            # Evita dejar una clave privada huérfana si falla la pública.
            privada.unlink(missing_ok=True)
            raise

    # Refuerza los permisos en sistemas que admiten chmod.
    try:
        privada.chmod(0o600)
    except OSError:
        print("ADVERTENCIA: no se pudieron reforzar los permisos de la clave.")

    print("Par de claves Ed25519 generado.")
    print("Clave privada:", privada)
    print("Clave pública:", publica)
    print("Protegé la clave privada y guardá una copia confiable de la pública.")


def cargar_recibo(ruta):
    """Lee un recibo JSON y prepara su representación canónica."""
    try:
        objeto = json.loads(Path(ruta).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"No se pudo leer el recibo: {exc}") from exc

    if not isinstance(objeto, dict):
        raise ValueError("El recibo debe ser un objeto JSON.")

    # Se reutiliza la canonicalización documentada por el proyecto.
    contenido = ts.canonical(objeto).encode("utf-8")
    return contenido


def firmar_recibo(ruta_recibo, ruta_privada, ruta_firma):
    """Firma el contenido canónico del recibo y crea una firma separada."""
    contenido = cargar_recibo(ruta_recibo)
    privada = Path(ruta_privada)

    if not privada.is_file():
        raise FileNotFoundError("No se encontró la clave privada indicada.")

    with tempfile.TemporaryDirectory(prefix="salem_firma_") as temporal:
        temporal = Path(temporal)
        mensaje = temporal / "recibo.canonico"
        firma = temporal / "firma.bin"
        mensaje.write_bytes(contenido)

        ejecutar_openssl([
            "pkeyutl", "-sign", "-rawin",
            "-inkey", str(privada),
            "-in", str(mensaje),
            "-out", str(firma),
        ])

        # El archivo lateral no contiene la clave privada.
        documento = {
            "signature_schema": ESQUEMA_FIRMA,
            "algorithm": "Ed25519",
            "signed_anchor_sha256": hashlib.sha256(contenido).hexdigest(),
            "signature_base64": base64.b64encode(
                firma.read_bytes()
            ).decode("ascii"),
        }

        salida = (
            json.dumps(
                documento, ensure_ascii=False, sort_keys=True,
                indent=2, allow_nan=False
            ) + "\n"
        ).encode("utf-8")

        escribir_nuevo(ruta_firma, salida)

    print("Firma Ed25519 creada:", ruta_firma)
    print("SHA-256 del contenido firmado:",
          hashlib.sha256(contenido).hexdigest())
    print("Guardá la firma separada del recibo y protegé la clave privada.")


def verificar_firma(ruta_recibo, ruta_publica, ruta_firma):
    """Verifica la firma usando una clave pública indicada explícitamente."""
    contenido = cargar_recibo(ruta_recibo)

    try:
        documento = json.loads(
            Path(ruta_firma).read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"No se pudo leer el archivo de firma: {exc}") from exc

    if not isinstance(documento, dict):
        raise ValueError("El archivo de firma debe ser un objeto JSON.")
    if documento.get("signature_schema") != ESQUEMA_FIRMA:
        raise ValueError("Esquema de firma desconocido.")
    if documento.get("algorithm") != "Ed25519":
        raise ValueError("El algoritmo de firma no es Ed25519.")

    resumen = hashlib.sha256(contenido).hexdigest()
    if documento.get("signed_anchor_sha256") != resumen:
        print("VERIFICACIÓN: FALLO")
        print("El contenido del recibo no coincide con el contenido firmado.")
        return False

    try:
        firma_binaria = base64.b64decode(
            documento["signature_base64"], validate=True
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise ValueError("La firma Base64 falta o no es válida.") from exc

    publica = Path(ruta_publica)
    if not publica.is_file():
        raise FileNotFoundError("No se encontró la clave pública indicada.")

    with tempfile.TemporaryDirectory(prefix="salem_verificar_") as temporal:
        temporal = Path(temporal)
        mensaje = temporal / "recibo.canonico"
        firma = temporal / "firma.bin"
        mensaje.write_bytes(contenido)
        firma.write_bytes(firma_binaria)

        try:
            ejecutar_openssl([
                "pkeyutl", "-verify", "-rawin",
                "-pubin", "-inkey", str(publica),
                "-in", str(mensaje),
                "-sigfile", str(firma),
            ])
        except RuntimeError:
            print("VERIFICACIÓN: FALLO")
            print("La firma no es válida para esta clave pública y este recibo.")
            return False

    print("VERIFICACIÓN: OK")
    print("La firma corresponde al contenido y a la clave pública indicada.")
    print("SHA-256 del contenido:", resumen)
    print("La confianza en la clave pública debe comprobarse por separado.")
    return True


def main():
    """Interfaz de comandos del módulo de firma."""
    parser = argparse.ArgumentParser(
        description="SALEM Neurociencia: firma Ed25519 de recibos"
    )
    sub = parser.add_subparsers(dest="comando", required=True)

    claves = sub.add_parser("generar-claves", help="Crear un par de claves")
    claves.add_argument("--privada", required=True, help="Ruta de la clave privada")
    claves.add_argument("--publica", required=True, help="Ruta de la clave pública")

    firmar = sub.add_parser("firmar", help="Firmar un recibo existente")
    firmar.add_argument("--recibo", required=True)
    firmar.add_argument("--privada", required=True)
    firmar.add_argument("--salida", required=True, help="Archivo de firma nuevo")

    verificar = sub.add_parser("verificar", help="Verificar una firma existente")
    verificar.add_argument("--recibo", required=True)
    verificar.add_argument("--publica", required=True)
    verificar.add_argument("--firma", required=True)

    args = parser.parse_args()

    try:
        if args.comando == "generar-claves":
            generar_claves(args.privada, args.publica)
        elif args.comando == "firmar":
            firmar_recibo(args.recibo, args.privada, args.salida)
        elif args.comando == "verificar":
            resultado = verificar_firma(
                args.recibo, args.publica, args.firma
            )
            sys.exit(0 if resultado else 2)
    except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
        print("ERROR:", exc, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
