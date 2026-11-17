"""Pruebas de la separacion entre core/ (logica) e interfaz/ (presentacion)."""

import ast
import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from core.admision import Admision
from core.carga import cargar_lote
from core.memoria import GestorMemoria
from core.main import ejecutar_simulacion
from core.planificador import PlanificadorSRTF
from interfaz import panel
from ayudas import simular

RAIZ = Path(__file__).resolve().parent.parent
LOTES = sorted((RAIZ / "data").glob("*.csv"))
ARCHIVOS_CORE = sorted((RAIZ / "core").glob("*.py"))


def _modulos_importados(ruta: Path) -> set:
    modulos = set()
    for nodo in ast.walk(ast.parse(ruta.read_text(encoding="utf-8"))):
        if isinstance(nodo, ast.Import):
            modulos.update(alias.name for alias in nodo.names)
        elif isinstance(nodo, ast.ImportFrom):
            modulos.add(nodo.module)
    return modulos


def _resultado(clase_planificador, ruta):
    """Simula un lote y retorna (tiempos por proceso, eventos, reloj final)."""
    procesos = cargar_lote(ruta).procesos
    memoria = GestorMemoria()
    admision = Admision(procesos, memoria)
    eventos = []
    planificador = clase_planificador(admision, memoria, eventos.append)
    simular(planificador)
    tiempos = [
        (p.id, p.tiempo_inicio, p.tiempo_finalizacion, p.estado) for p in procesos
    ]
    return tiempos, eventos, planificador.reloj


class TestSeparacion(unittest.TestCase):
    def test_core_no_depende_de_la_interfaz(self):
        self.assertTrue(ARCHIVOS_CORE)
        for ruta in ARCHIVOS_CORE:
            with self.subTest(archivo=ruta.name):
                importados = _modulos_importados(ruta)
                self.assertFalse(
                    any(m == "interfaz" or m.startswith("interfaz.") for m in importados)
                )

    def test_core_muestra_texto_sin_colores(self):
        salida = io.StringIO()
        with redirect_stdout(salida):
            codigo = ejecutar_simulacion(RAIZ / "data" / "procesos_demo.csv")
        self.assertEqual(codigo, 0)
        self.assertNotIn("\x1b[", salida.getvalue())
        self.assertIn("INFORME ESTADISTICO FINAL", salida.getvalue())

    def test_la_interfaz_usa_los_mismos_modulos(self):
        self.assertIs(panel.Admision, Admision)
        self.assertIs(panel.GestorMemoria, GestorMemoria)
        self.assertTrue(issubclass(panel.PlanificadorConGantt, PlanificadorSRTF))

    def test_planificador_con_gantt_no_cambia_la_simulacion(self):
        self.assertTrue(LOTES)
        for ruta in LOTES:
            with self.subTest(lote=ruta.name):
                self.assertEqual(
                    _resultado(PlanificadorSRTF, ruta),
                    _resultado(panel.PlanificadorConGantt, ruta),
                )


if __name__ == "__main__":
    unittest.main()
