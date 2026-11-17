"""Arranca KernelFlow en su version completa (la del ejecutable).

La logica del simulador esta en ``core/`` y la presentacion con colores y
graficos en ``interfaz/``. La version base se ejecuta con ``python3 -m core``.
"""

from interfaz.main import main

if __name__ == "__main__":
    raise SystemExit(main())
