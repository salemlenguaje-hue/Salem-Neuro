# -*- coding: utf-8 -*-
"""Pruebas adversariales de la firma Ed25519 de SALEM Neurociencia."""

import base64
import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import firma_salem as fs
import trazas_salem as ts


class PruebasFirmaSalem(unittest.TestCase):
    """Comprueba la firma digital sin modificar corridas reales."""

    def setUp(self):
        # Cada prueba recibe su propio entorno temporal aislado.
        self.temporal = tempfile.TemporaryDirectory(prefix="test_firma_salem_")
        self.raiz = Path(self.temporal.name)
        self.corrida = self.raiz / "corrida"
        self.recibo = self.raiz / "recibo.json"
        self.privada = self.raiz / "privada.pem"
        self.publica = self.raiz / "publica.pem"
        self.firma = self.raiz / "firma.json"

        # Crear una corrida sintética y un recibo válido.
        ts.demo(self.corrida)
        ts.create_anchor(self.corrida, self.recibo)

        # Generar claves exclusivas para esta prueba.
        with contextlib.redirect_stdout(io.StringIO()):
            fs.generar_claves(self.privada, self.publica)
            fs.firmar_recibo(self.recibo, self.privada, self.firma)

    def tearDown(self):
        # Eliminar los archivos temporales al terminar cada prueba.
        self.temporal.cleanup()

    def verificar_sin_ruido(self, recibo=None, publica=None, firma=None):
        """Ejecuta la verificación sin llenar la salida de mensajes."""
        with contextlib.redirect_stdout(io.StringIO()):
            return fs.verificar_firma(
                recibo or self.recibo,
                publica or self.publica,
                firma or self.firma,
            )

    def leer_recibo(self):
        return json.loads(self.recibo.read_text(encoding="utf-8"))

    def guardar_recibo(self, objeto):
        self.recibo.write_text(
            json.dumps(objeto, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def test_1_firma_original_valida(self):
        """El recibo intacto debe verificarse correctamente."""
        self.assertTrue(self.verificar_sin_ruido())

    def test_2_recibo_alterado_rechazado(self):
        """Cambiar el recibo sin cambiar la firma debe fallar."""
        recibo = self.leer_recibo()
        recibo["anchored_at_utc"] = "2000-01-01T00:00:00Z"
        self.guardar_recibo(recibo)

        self.assertFalse(self.verificar_sin_ruido())

    def test_3_hash_recalculado_sin_refirmar_rechazado(self):
        """Recalcular el hash publicado no debe falsificar la firma."""
        recibo = self.leer_recibo()
        recibo["anchored_at_utc"] = "2000-01-01T00:00:00Z"
        self.guardar_recibo(recibo)

        # El atacante actualiza el hash, pero no puede crear la firma privada.
        contenido = ts.canonical(recibo).encode("utf-8")
        documento = json.loads(self.firma.read_text(encoding="utf-8"))
        documento["signed_anchor_sha256"] = hashlib.sha256(
            contenido
        ).hexdigest()
        self.firma.write_text(
            json.dumps(documento, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        self.assertFalse(self.verificar_sin_ruido())

    def test_4_clave_publica_incorrecta_rechazada(self):
        """Una clave pública distinta no debe validar la firma."""
        otra_privada = self.raiz / "otra_privada.pem"
        otra_publica = self.raiz / "otra_publica.pem"

        with contextlib.redirect_stdout(io.StringIO()):
            fs.generar_claves(otra_privada, otra_publica)

        self.assertFalse(self.verificar_sin_ruido(publica=otra_publica))

    def test_5_firma_existente_no_se_sobrescribe(self):
        """Firmar hacia una ruta existente debe fallar sin reemplazarla."""
        contenido_original = self.firma.read_bytes()

        with self.assertRaises(FileExistsError):
            with contextlib.redirect_stdout(io.StringIO()):
                fs.firmar_recibo(
                    self.recibo, self.privada, self.firma
                )

        self.assertEqual(self.firma.read_bytes(), contenido_original)


if __name__ == "__main__":
    unittest.main(verbosity=2)
