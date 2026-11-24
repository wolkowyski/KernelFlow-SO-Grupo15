# =============================================================================
#  __init__.py  -  CONVIERTE LA CARPETA "core" EN UN PAQUETE DE PYTHON
# -----------------------------------------------------------------------------
#  Copia COMENTADA. El codigo es IDENTICO al entregado.
# -----------------------------------------------------------------------------
#  Python trata como "paquete" a una carpeta que tiene __init__.py. Gracias a
#  eso, los otros archivos pueden escribir "from core.memoria import ...".
#  Este no tiene codigo: solo un texto (docstring) que describe la carpeta.
# =============================================================================
"""Logica del simulador KernelFlow: la version base del TPI.

    proceso.py, estados.py   modelo de proceso y transiciones de estado
    carga.py                 lectura y validacion del CSV
    memoria.py               memoria MVT con Best-Fit
    admision.py              admision, colas y multiprogramacion 5
    planificador.py          planificacion SRTF apropiativa
    estadisticas.py          informe estadistico final
    presentacion.py          salida de texto paso a paso
    main.py                  menu y ciclo de la simulacion

Se ejecuta con ``python3 -m core`` desde la raiz del proyecto.
"""
