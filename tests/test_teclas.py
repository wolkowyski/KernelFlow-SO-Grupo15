"""Pruebas de la lectura de teclas durante la simulacion."""

import os
import threading
import unittest
from unittest import mock

from interfaz.entrada import leer_tecla


@unittest.skipIf(os.name == "nt", "usa una pseudo-terminal de Linux")
class TestTeclas(unittest.TestCase):
    def setUp(self):
        self.maestro, self.esclavo = os.openpty()
        entrada = mock.Mock()
        entrada.fileno.return_value = self.esclavo
        self.parche = mock.patch("interfaz.entrada.sys.stdin", entrada)
        self.parche.start()

    def tearDown(self):
        self.parche.stop()
        os.close(self.maestro)
        os.close(self.esclavo)

    def _presionar(self, datos: bytes) -> str:
        """Simula que el usuario escribe ``datos`` mientras se espera una tecla."""
        escritura = threading.Timer(0.2, os.write, (self.maestro, datos))
        escritura.start()
        try:
            return leer_tecla()
        finally:
            escritura.join()

    def test_flecha_no_se_toma_como_salir(self):
        self.assertEqual(self._presionar(b"\x1b[A"), "")  # flecha arriba

    def test_espacio_y_q_se_leen_normalmente(self):
        self.assertEqual(self._presionar(b" "), " ")
        self.assertEqual(self._presionar(b"q"), "q")


if __name__ == "__main__":
    unittest.main()
