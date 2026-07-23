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
import time
from datetime import date, timedelta, datetime, timezone

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
    "sueno_hora_inicio",
    "sueno_hora_fin",
    "sueno_profundo_min",
    "sueno_ligero_min",
    "sueno_rem_min",
    "sueno_despierto_min",
    "puntaje_sueno",
    "body_battery_max",
    "body_battery_min",
    "estres_promedio",
    "actividad_tipo",
    "actividad_duracion_min",
    "minutos_intensidad_semana",
    "training_readiness",
    "hrv_promedio_ms",
    "hrv_estado",
    "respiracion_promedio",
    "vo2_max",
]


def obtener_datos_garmin(api: Garmin, fecha_str: str) -> dict:
    """Arma un diccionario con los datos del día, usando una sesión ya autenticada."""
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

        # Garmin entrega "sleepStartTimestampLocal"/"sleepEndTimestampLocal" en
        # milisegundos, ya ajustados a tu hora local (aunque el formato es epoch
        # UTC, representa la hora local del reloj -- por eso los formateamos
        # como si fueran UTC, sin volver a convertir zona horaria).
        inicio_ms = dto.get("sleepStartTimestampLocal")
        fin_ms = dto.get("sleepEndTimestampLocal")
        if inicio_ms:
            fila["sueno_hora_inicio"] = datetime.fromtimestamp(
                inicio_ms / 1000, tz=timezone.utc
            ).strftime("%H:%M")
        if fin_ms:
            fila["sueno_hora_fin"] = datetime.fromtimestamp(
                fin_ms / 1000, tz=timezone.utc
            ).strftime("%H:%M")

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

    # --- Actividad registrada del día (ej. caminata, ciclismo) ---
    try:
        actividades = api.get_activities_fordate(fecha_str)
        lista = (actividades or {}).get("ActivitiesForDay", {}).get("payload", [])
        if lista:
            # Si hubo varias, sumamos duración y usamos el tipo de la más larga.
            principal = max(lista, key=lambda a: a.get("duration", 0))
            fila["actividad_tipo"] = (principal.get("activityType") or {}).get("typeKey")
            fila["actividad_duracion_min"] = round(
                sum(a.get("duration", 0) for a in lista) / 60, 1
            )
    except Exception as e:
        print(f"[aviso] No se pudo obtener actividad del día: {e}")

    # --- Minutos de intensidad de la semana (acumulado moderado/vigoroso) ---
    try:
        inicio_semana = (
            date.fromisoformat(fecha_str) - timedelta(days=date.fromisoformat(fecha_str).weekday())
        ).isoformat()
        intensidad = api.get_weekly_intensity_minutes(inicio_semana, fecha_str)
        if intensidad:
            ultimo = intensidad[-1] if isinstance(intensidad, list) else intensidad
            fila["minutos_intensidad_semana"] = (
                (ultimo.get("moderateValue") or 0) + (ultimo.get("vigorousValue") or 0) * 2
            )
    except Exception as e:
        print(f"[aviso] No se pudieron obtener minutos de intensidad: {e}")

    # --- Training Readiness (qué tan lista está tu cuerpo hoy, 0-100) ---
    try:
        readiness = api.get_training_readiness(fecha_str)
        if readiness and isinstance(readiness, list) and len(readiness) > 0:
            fila["training_readiness"] = readiness[0].get("score")
    except Exception as e:
        print(f"[aviso] No se pudo obtener Training Readiness: {e}")

    # --- HRV (Variabilidad de Frecuencia Cardiaca) ---
    try:
        hrv = api.get_hrv_data(fecha_str)
        if hrv:
            resumen = hrv.get("hrvSummary", {})
            fila["hrv_promedio_ms"] = resumen.get("lastNightAvg")
            fila["hrv_estado"] = resumen.get("status")
    except Exception as e:
        print(f"[aviso] No se pudo obtener HRV: {e}")

    # --- Frecuencia respiratoria promedio ---
    try:
        respiracion = api.get_respiration_data(fecha_str)
        fila["respiracion_promedio"] = respiracion.get("avgSleepRespirationValue") or respiracion.get(
            "avgWakingRespirationValue"
        )
    except Exception as e:
        print(f"[aviso] No se pudo obtener frecuencia respiratoria: {e}")

    # --- VO2 Max (capacidad aeróbica -- cambia lento, se revisa más bien semanal/mensual) ---
    try:
        max_metrics = api.get_max_metrics(fecha_str)
        if max_metrics and isinstance(max_metrics, list) and len(max_metrics) > 0:
            generico = max_metrics[0].get("generic", {})
            fila["vo2_max"] = generico.get("vo2MaxPreciseValue") or generico.get("vo2MaxValue")
    except Exception as e:
        print(f"[aviso] No se pudo obtener VO2 max: {e}")

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
    # Uso normal (diario):        python garmin_to_drive.py
    # Uso normal (día puntual):   python garmin_to_drive.py 2026-07-20
    # Backfill (rango de fechas): python garmin_to_drive.py 2026-07-01 2026-07-23
    if len(sys.argv) >= 3:
        fecha_inicio = date.fromisoformat(sys.argv[1])
        fecha_fin = date.fromisoformat(sys.argv[2])
    elif len(sys.argv) == 2:
        fecha_inicio = fecha_fin = date.fromisoformat(sys.argv[1])
    else:
        fecha_inicio = fecha_fin = date.today()

    print("Iniciando sesión en Garmin Connect...")
    email = os.environ["GARMIN_EMAIL"]
    password = os.environ["GARMIN_PASSWORD"]
    api = Garmin(email, password)
    api.login()

    filas_nuevas = []
    dia_actual = fecha_inicio
    while dia_actual <= fecha_fin:
        fecha_str = dia_actual.isoformat()
        print(f"Obteniendo datos de Garmin para {fecha_str}...")
        filas_nuevas.append(obtener_datos_garmin(api, fecha_str))
        dia_actual += timedelta(days=1)
        if dia_actual <= fecha_fin:
            # Pausa entre días para no disparar el límite de Garmin por
            # demasiadas solicitudes seguidas (rate limit).
            time.sleep(2)

    print("Conectando con Google Drive...")
    service = obtener_credenciales_drive()
    folder_id = os.environ["GDRIVE_FOLDER_ID"]
    file_id = buscar_archivo_en_drive(service, folder_id, CSV_FILENAME)

    filas = descargar_csv(service, file_id) if file_id else []

    # Reemplaza cualquier fila existente para esas fechas y agrega las nuevas.
    fechas_nuevas = {f["fecha"] for f in filas_nuevas}
    filas = [f for f in filas if f.get("fecha") not in fechas_nuevas]
    filas.extend(filas_nuevas)
    filas.sort(key=lambda f: f["fecha"])

    print("Actualizando historial en Drive...")
    subir_csv(service, folder_id, file_id, filas)

    print(f"Listo. {CSV_FILENAME} actualizado con {len(filas_nuevas)} día(s): {fecha_inicio} a {fecha_fin}.")


if __name__ == "__main__":
    main()
