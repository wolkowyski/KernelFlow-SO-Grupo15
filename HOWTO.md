KERNELFLOW - GUIA RAPIDA DE EJECUCION
Simulador de Asignacion de Memoria y Planificacion de Procesos
Sistemas Operativos - UTN FRRe - 2026 - Comision K 2.1 (Turno Tarde) - Grupo 15

La guia completa, con capturas, esta en HOWTO_KernelFlow_Grupo15.docx.


Para ejecutar este programa debe abrirlo desde la carpeta "ejecutable":

    Linux:    abrir una terminal en la carpeta "ejecutable" y escribir
                  ./KernelFlow
              (si no tiene permiso de ejecucion: chmod +x KernelFlow)

    Windows:  abrir la carpeta "ejecutable" y hacer doble clic en
                  KernelFlow.exe

No hace falta instalar Python ni ninguna libreria. La carpeta "data" debe
quedar junto al ejecutable: ahi estan los lotes de prueba. Se recomienda
usar la terminal maximizada.


Uso:
    [1] simula el lote de demostracion (data/procesos_demo.csv).
    [2] lista los lotes de la carpeta data para elegir uno por numero,
        o permite escribir la ruta de un CSV propio (R) o buscarlo con el
        explorador de archivos (E).
    [3] muestra la guia rapida.  [4] cambia el modo de pantalla.  [0] sale.

    Durante la simulacion:
        Espacio / Enter   avanza al siguiente cambio (llegada o finalizacion)
        B                 vuelve al paso anterior para revisarlo
        F                 alterna entre historial y pantalla fija
        Q                 vuelve al menu
        G                 (al terminar) guarda la simulacion en TXT y HTML


Consideracion sobre los archivos CSV:
    Los datos cargados en cada archivo CSV deben tener este orden
    id_proceso, tamanio, t_arribo, t_irrupcion
    Una fila por proceso, entre 1 y 10 procesos.
    Tamanio en KB (1 a 450); tiempos enteros (arribo 0 a 999,
    irrupcion 1 a 999). Separador "," o ";" (Excel). El encabezado es
    opcional.
    Ejemplo:
        P1,120,0,8
        P2,150,1,4

    Si una fila tiene un error (letras, negativos, ID repetido, mas de
    450K, a partir del proceso 11, etc.) se descarta con un aviso que
    indica la linea y el motivo, y se simulan los procesos validos.

    Los lotes enviados por la catedra estan en data/catedra_lote_1.csv
    a data/catedra_lote_6.csv.


Desde el codigo fuente (carpeta "codigo_fuente", requiere Python 3.8+):
    python3 main.py        version completa (la del ejecutable)
    python3 -m core        version base del TPI, solo texto (Enter avanza)
    En Windows usar "py" en lugar de "python3".
