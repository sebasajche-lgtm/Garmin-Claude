"""
garmin_to_drive.py
-------------------
Extrae datos diarios de Garmin Connect (sueño, frecuencia cardiaca, pasos,
Body Battery, estrés) y actualiza un archivo CSV histórico en Google Drive.

Pensado para correr una vez al día de forma automática (ver el workflow de
GitHub Actions incluido: .github/workflows/sync.yml), pero también podés
correrlo manualmente en tu computadora para probarlo.

Variables de entorno necesarias (ver README.md para cómo obtenerlas):
  GARMIN_EMAIL              -> el correo con el que entrás a Garmin Connect
  GARMIN_PASSWORD           -> tu contraseña de Garmin Connect
  GDRIVE_FOLDER_ID          -> el ID de la carpeta de Drive donde se guarda el historial
  GOOGLE_SERVICE_ACCOUNT_JSON -> el contenido completo del archivo JSON de la
                                  cuenta de servicio de Google (como texto)
"""

import os
import io
import csv
import json
import sys
from datetime import date, timedelta

from garminconnect import Garmin

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

CSV_FILENAME = "garmin_historial.csv"
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]

CSV_COLUMNS = [
    "fecha",
    "pasos",
    "calorias_activas",
    "fc_reposo",
    "fc_promedio",
    "fc_maxima",
    "sueno_horas",
    "sueno_profundo_min",
    "sueno_ligero_min",
    "sueno_rem_min",
    "sueno_despierto_min",
    "puntaje_sueno",
    "body_battery_max",
    "body_battery_min",
    "estres_promedio",
]


def obtener_datos_garmin(fecha_str: str) -> dict:
    """Se conecta a Garmin Connect y arma un diccionario con los datos del día."""
    email = os.environ["GARMIN_EMAIL"]
    password = os.environ["GARMIN_PASSWORD"]

    api = Garmin(email, password)
    api.login()

    fila = {"fecha": fecha_str}

    # --- Resumen diario: pasos, calorías, FC ---
    try:
        stats = api.get_stats(fecha_str)
        fila["pasos"] = stats.get("totalSteps")
        fila["calorias_activas"] = stats.get("activeKilocalories")
        fila["fc_reposo"] = stats.get("restingHeartRate")
        fila["fc_promedio"] = stats.get("averageHeartRateInBeatsPerMinute") or stats.get("lastSevenDaysAvgRestingHeartRate")
        fila["fc_maxima"] = stats.get("maxHeartRate")
    except Exception as e:
        print(f"[aviso] No se pudieron obtener estadísticas diarias: {e}")

    # --- Sueño ---
    try:
        sueno = api.get_sleep_data(fecha_str)
        dto = sueno.get("dailySleepDTO", {}) if sueno else {}
        segundos_totales = dto.get("sleepTimeSeconds")
        fila["sueno_horas"] = round(segundos_totales / 3600, 2) if segundos_totales else None
        fila["sueno_profundo_min"] = round((dto.get("deepSleepSeconds") or 0) / 60, 1)
        fila["sueno_ligero_min"] = round((dto.get("lightSleepSeconds") or 0) / 60, 1)
        fila["sueno_rem_min"] = round((dto.get("remSleepSeconds") or 0) / 60, 1)
        fila["sueno_despierto_min"] = round((dto.get("awakeSleepSeconds") or 0) / 60, 1)
        fila["puntaje_sueno"] = (dto.get("sleepScores") or {}).get("overall", {}).get("value")
    except Exception as e:
        print(f"[aviso] No se pudieron obtener datos de sueño: {e}")

    # --- Body Battery ---
    try:
        bb = api.get_body_battery(fecha_str)
        if bb and isinstance(bb, list) and len(bb) > 0:
            valores = [p[1] for p in bb[0].get("bodyBatteryValuesArray", []) if p[1] is not None]
            if valores:
                fila["body_battery_max"] = max(valores)
                fila["body_battery_min"] = min(valores)
    except Exception as e:
        print(f"[aviso] No se pudo obtener Body Battery: {e}")

    # --- Estrés ---
    try:
        fila["estres_promedio"] = stats.get("averageStressLevel")
    except Exception:
        pass

    return fila


def obtener_credenciales_drive():
    info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = service_account.Credentials.from_service_account_info(info, scopes=DRIVE_SCOPES)
    return build("drive", "v3", credentials=creds)


def buscar_archivo_en_drive(service, folder_id: str, nombre: str):
    query = f"name = '{nombre}' and '{folder_id}' in parents and trashed = false"
    resultados = service.files().list(q=query, fields="files(id, name)").execute()
    archivos = resultados.get("files", [])
    return archivos[0]["id"] if archivos else None


def descargar_csv(service, file_id: str) -> list:
    """Descarga el CSV existente y lo devuelve como lista de diccionarios."""
    request = service.files().get_media(fileId=file_id)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    listo = False
    while not listo:
        _, listo = downloader.next_chunk()
    buffer.seek(0)
    texto = buffer.read().decode("utf-8")
    lector = csv.DictReader(io.StringIO(texto))
    return list(lector)


def subir_csv(service, folder_id: str, file_id: str, filas: list):
    buffer = io.StringIO()
    escritor = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS)
    escritor.writeheader()
    for fila in filas:
        escritor.writerow(fila)

    contenido = io.BytesIO(buffer.getvalue().encode("utf-8"))
    media = MediaIoBaseUpload(contenido, mimetype="text/csv", resumable=True)

    if file_id:
        service.files().update(fileId=file_id, media_body=media).execute()
    else:
        metadata = {"name": CSV_FILENAME, "parents": [folder_id]}
        service.files().create(body=metadata, media_body=media, fields="id").execute()


def main():
    fecha_str = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()

    print(f"Obteniendo datos de Garmin para {fecha_str}...")
    fila_nueva = obtener_datos_garmin(fecha_str)

    print("Conectando con Google Drive...")
    service = obtener_credenciales_drive()
    folder_id = os.environ["GDRIVE_FOLDER_ID"]
    file_id = buscar_archivo_en_drive(service, folder_id, CSV_FILENAME)

    filas = descargar_csv(service, file_id) if file_id else []

    # Si ya existe una fila para esa fecha, la reemplaza; si no, la agrega.
    filas = [f for f in filas if f.get("fecha") != fecha_str]
    filas.append(fila_nueva)
    filas.sort(key=lambda f: f["fecha"])

    print("Actualizando historial en Drive...")
    subir_csv(service, folder_id, file_id, filas)

    print(f"Listo. {CSV_FILENAME} actualizado con los datos de {fecha_str}.")


if __name__ == "__main__":
    main()
