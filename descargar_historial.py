"""Descarga garmin_historial.csv desde Drive a un archivo local, para que
generar_dashboard.py lo pueda leer dentro del mismo job de GitHub Actions."""
import sys
from garmin_to_drive import obtener_credenciales_drive, buscar_archivo_en_drive, descargar_csv, CSV_COLUMNS
import os
import csv

service = obtener_credenciales_drive()
folder_id = os.environ["GDRIVE_FOLDER_ID"]
file_id = buscar_archivo_en_drive(service, folder_id, "garmin_historial.csv")
if not file_id:
    print("No se encontró garmin_historial.csv en Drive.")
    sys.exit(1)

filas = descargar_csv(service, file_id)
with open("garmin_historial_local.csv", "w", newline="", encoding="utf-8") as f:
    escritor = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
    escritor.writeheader()
    for fila in filas:
        escritor.writerow(fila)

print(f"Descargado: {len(filas)} filas.")
