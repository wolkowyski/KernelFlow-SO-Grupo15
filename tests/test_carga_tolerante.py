"""Pruebas de la carga tolerante: entradas raras o con errores.

Cada fila con un problema se descarta con un aviso que indica la linea y el
motivo; los procesos validos se simulan. Nunca se corrigen ni se inventan
datos, y nada debe colgar ni cortar el programa con un error no controlado.
"""

import tempfile
import time
import unittest
from pathlib import Path

from core.admision import Admision
from core.carga import (
    MAX_TIEMPO,
    ErrorCargaProcesos,
    cargar_lote,
    cargar_procesos_desde_csv,
)
from core.memoria import GestorMemoria
from core.planificador import PlanificadorSRTF
from ayudas import simular

DATA = Path(__file__).resolve().parent.parent / "data"


class TestCargaTolerante(unittest.TestCase):
    def setUp(self):
        self._carpeta = tempfile.TemporaryDirectory()
        self.addCleanup(self._carpeta.cleanup)

    def _archivo(self, contenido, nombre="lote.csv"):
        ruta = Path(self._carpeta.name) / nombre
        if isinstance(contenido, str):
            contenido = contenido.encode("utf-8")
        ruta.write_bytes(contenido)
        return ruta

    def _ids(self, resultado):
        return [p.id for p in resultado.procesos]

    def test_lote_5_de_la_catedra_descarta_el_proceso_de_451k(self):
        resultado = cargar_lote(DATA / "catedra_lote_5.csv")
        self.assertEqual(self._ids(resultado), ["P1", "P3"])
        self.assertEqual(len(resultado.avisos), 1)
        self.assertIn("Linea 2", resultado.avisos[0])
        self.assertIn("451K", resultado.avisos[0])

    def test_lote_6_de_la_catedra_toma_los_primeros_10(self):
        resultado = cargar_lote(DATA / "catedra_lote_6.csv")
        self.assertEqual(self._ids(resultado), [f"P{i}" for i in range(1, 11)])
        self.assertEqual(len(resultado.avisos), 2)
        self.assertTrue(all("maximo de 10 procesos" in a for a in resultado.avisos))

    def test_formato_de_excel_en_espanol(self):
        # Encabezado, separador ';', columnas vacias al final y codificacion
        # de Windows (cp1252), como guarda Excel.
        contenido = "Proceso;Tamaño;Arribo;Irrupcion;;\r\nP1;100;0;3;;\r\nPÑ;50;1;2;;\r\n"
        resultado = cargar_lote(self._archivo(contenido.encode("cp1252")))
        self.assertEqual(self._ids(resultado), ["P1", "PÑ"])
        self.assertEqual(len(resultado.avisos), 1)
        self.assertIn("encabezado", resultado.avisos[0])

    def test_tabulacion_comentarios_espacios_y_lineas_vacias(self):
        contenido = "# lote de prueba\n\n P1 \t 10 \t 0 \t 2 \n\n\"P2\",\"20\",\"1\",\"3\"\n"
        resultado = cargar_lote(self._archivo(contenido))
        self.assertEqual(self._ids(resultado), ["P1", "P2"])
        self.assertEqual(resultado.avisos, [])

    def test_filas_invalidas_se_descartan_con_su_linea_y_motivo(self):
        contenido = (
            "P1,100,0,5\n"
            "P2,abc,0,5\n"      # letras
            "P3,10.5,0,5\n"     # decimal
            "P4,100,-1,5\n"     # negativo
            "P5,100,0,0\n"      # irrupcion cero
            "P6,0,0,5\n"        # tamanio cero
            "P7,100,0\n"        # faltan columnas
            "P1,50,2,2\n"       # ID repetido
            ",50,2,2\n"         # sin ID
            "P 8,50,2,2\n"      # ID con espacio
            "P9,50,2,2\n"
        )
        resultado = cargar_lote(self._archivo(contenido))
        self.assertEqual(self._ids(resultado), ["P1", "P9"])
        self.assertEqual(len(resultado.avisos), 9)
        for linea, aviso in zip(range(2, 11), resultado.avisos):
            self.assertTrue(aviso.startswith(f"Linea {linea}:"), aviso)
            self.assertTrue(aviso.endswith("Se descarta."), aviso)

    def test_tiempos_enormes_se_rechazan_y_no_cuelgan(self):
        contenido = f"P1,10,999999999,2\nP2,10,0,{MAX_TIEMPO + 1}\nP3,10,0,2\n"
        resultado = cargar_lote(self._archivo(contenido))
        self.assertEqual(self._ids(resultado), ["P3"])
        self.assertEqual(len(resultado.avisos), 2)

    def test_tiempos_maximos_permitidos_terminan_rapido(self):
        contenido = "".join(f"P{i},45,{MAX_TIEMPO},{MAX_TIEMPO}\n" for i in range(1, 11))
        procesos = cargar_lote(self._archivo(contenido)).procesos
        memoria = GestorMemoria()
        admision = Admision(procesos, memoria)
        planificador = PlanificadorSRTF(admision, memoria)
        inicio = time.time()
        simular(planificador)
        self.assertEqual(planificador.reloj, MAX_TIEMPO * 11)
        self.assertLess(time.time() - inicio, 10)

    def test_archivos_sin_procesos_validos_explican_el_motivo(self):
        for contenido in ("", "  \n\n", "P1,abc,0,2\n", "id,tamanio,arribo,irrupcion\n"):
            with self.subTest(contenido=contenido):
                with self.assertRaises(ErrorCargaProcesos) as ctx:
                    cargar_lote(self._archivo(contenido))
                self.assertIn("ningun proceso valido", str(ctx.exception))
        with self.assertRaises(ErrorCargaProcesos) as ctx:
            cargar_lote(self._archivo("P1,abc,0,2\n"))
        self.assertIn("Linea 1", str(ctx.exception))

    def test_archivos_que_no_son_csv(self):
        with self.assertRaises(ErrorCargaProcesos):
            cargar_lote(self._archivo(bytes(range(256)) * 4, "binario.csv"))
        with self.assertRaises(ErrorCargaProcesos):
            cargar_lote(self._carpeta.name)
        with self.assertRaises(ErrorCargaProcesos):
            cargar_lote(Path(self._carpeta.name) / "no_existe.csv")
        with self.assertRaises(ErrorCargaProcesos):
            cargar_lote("")

    def test_version_estricta_rechaza_el_archivo_completo(self):
        with self.assertRaises(ErrorCargaProcesos) as ctx:
            cargar_procesos_desde_csv(DATA / "catedra_lote_6.csv")
        self.assertIn("contiene 12 procesos", str(ctx.exception))
        with self.assertRaises(ErrorCargaProcesos):
            cargar_procesos_desde_csv(DATA / "catedra_lote_5.csv")


if __name__ == "__main__":
    unittest.main()
