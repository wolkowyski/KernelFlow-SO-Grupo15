"""Pruebas de la separacion entre el nucleo (core.py) y la interfaz."""

import ast
import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import core
import interfaz
from ayudas import simular

RAIZ = Path(__file__).resolve().parent.parent
LOTES = sorted((RAIZ / "data").glob("*.csv"))


def _resultado(clase_planificador, ruta):
    """Simula un lote y retorna (tiempos por proceso, eventos, reloj final)."""
    procesos = core.cargar_procesos(ruta)
    memoria = core.GestorMemoria()
    admision = core.Admision(procesos, memoria)
    eventos = []
    planificador = clase_planificador(admision, memoria, eventos.append)
    simular(planificador)
    tiempos = [
        (p.id, p.tiempo_inicio, p.tiempo_finalizacion, p.estado) for p in procesos
    ]
    return tiempos, eventos, planificador.reloj


class TestSeparacion(unittest.TestCase):
    def test_core_no_depende_de_la_interfaz(self):
        arbol = ast.parse((RAIZ / "core.py").read_text(encoding="utf-8"))
        modulos = set()
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import):
                modulos.update(alias.name for alias in nodo.names)
            elif isinstance(nodo, ast.ImportFrom):
                modulos.add(nodo.module)
        self.assertNotIn("interfaz", modulos)

    def test_core_muestra_texto_sin_colores(self):
        salida = io.StringIO()
        with redirect_stdout(salida):
            codigo = core.ejecutar_simulacion(
                RAIZ / "data" / "procesos_demo.csv"
            )
        self.assertEqual(codigo, 0)
        self.assertNotIn("\x1b[", salida.getvalue())
        self.assertIn("INFORME ESTADISTICO FINAL", salida.getvalue())

    def test_la_interfaz_usa_la_logica_del_nucleo(self):
        self.assertIs(interfaz.Admision, core.Admision)
        self.assertIs(interfaz.GestorMemoria, core.GestorMemoria)
        self.assertIs(interfaz.calcular_estadisticas, core.calcular_estadisticas)
        self.assertTrue(issubclass(interfaz.PlanificadorConGantt, core.PlanificadorSRTF))

    def test_planificador_con_gantt_no_cambia_la_simulacion(self):
        self.assertTrue(LOTES)
        for ruta in LOTES:
            with self.subTest(lote=ruta.name):
                self.assertEqual(
                    _resultado(core.PlanificadorSRTF, ruta),
                    _resultado(interfaz.PlanificadorConGantt, ruta),
                )


if __name__ == "__main__":
    unittest.main()
