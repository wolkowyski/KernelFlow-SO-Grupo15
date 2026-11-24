# =============================================================================
#  __main__.py  -  LO QUE CORRE CUANDO SE ESCRIBE "python -m core"
# -----------------------------------------------------------------------------
#  Copia COMENTADA. El codigo es IDENTICO al entregado.
# -----------------------------------------------------------------------------
#  "python -m core" le dice a Python: "ejecuta el paquete core". Python busca
#  core/__main__.py y lo corre. Este archivo solo llama a main() de main.py.
# =============================================================================
"""Permite ejecutar la version base con ``python3 -m core``."""

from core.main import main

raise SystemExit(main())
# >> main() devuelve 0 (ok), 1 (error) o 130 (Ctrl+C) y SystemExit le pasa
#    ese numero al sistema operativo como "codigo de salida".
