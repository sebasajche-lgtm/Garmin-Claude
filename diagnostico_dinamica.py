"""
diagnostico_dinamica.py
-------------------------
Script de UN SOLO USO. Busca cadencia, zancada, tiempo de contacto y
oscilación vertical en el detalle completo de tu actividad más reciente
de tipo running/trail_running.

No modifica nada en Drive ni en el historial -- solo imprime en pantalla.
"""
import os
from datetime import date, timedelta
from garminconnect import Garmin

email = os.environ["GARMIN_EMAIL"]
password = os.environ["GARMIN_PASSWORD"]

api = Garmin(email, password)
api.login()

import sys
ayer = sys.argv[1] if len(sys.argv) > 1 else (date.today() - timedelta(days=1)).isoformat()
actividades = api.get_activities_by_date(ayer, ayer)

if not actividades:
    print(f"No hay actividades registradas el {ayer}.")
else:
    principal = max(actividades, key=lambda a: a.get("duration", 0))
    activity_id = principal.get("activityId")
    print(f"Actividad: ID {activity_id}, tipo {principal.get('activityType')}\n")

    detalle = api.get_activity(activity_id)

    def buscar_campos(obj, palabras, ruta=""):
        encontrados = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                nueva_ruta = f"{ruta}.{k}" if ruta else k
                if any(p in k.lower() for p in palabras):
                    encontrados.append((nueva_ruta, v))
                encontrados.extend(buscar_campos(v, palabras, nueva_ruta))
        elif isinstance(obj, list):
            for i, item in enumerate(obj[:3]):
                encontrados.extend(buscar_campos(item, palabras, f"{ruta}[{i}]"))
        return encontrados

    palabras = ["cadence", "stride", "contact", "oscillation"]
    resultados = buscar_campos(detalle, palabras)

    if resultados:
        print("¡Encontrado! Rutas relacionadas a dinámica de carrera:\n")
        for ruta, valor in resultados:
            print(f"  {ruta} = {valor}")
    else:
        print("No se encontró nada en get_activity(). Probando get_activity_details()...")
        detalle2 = api.get_activity_details(activity_id)
        resultados2 = buscar_campos(detalle2, palabras)
        if resultados2:
            print("\n¡Encontrado en get_activity_details!\n")
            for ruta, valor in resultados2:
                print(f"  {ruta} = {valor}")
        else:
            print("Tampoco aparece ahí. Probando get_activity_splits()...")
            splits = api.get_activity_splits(activity_id)
            resultados3 = buscar_campos(splits, palabras)
            if resultados3:
                print("\n¡Encontrado en get_activity_splits!\n")
                for ruta, valor in resultados3:
                    print(f"  {ruta} = {valor}")
            else:
                print("No se encontró en ninguno de los 3 lugares consultados.")
