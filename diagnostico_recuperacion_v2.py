"""
diagnostico_recuperacion.py
-----------------------------
Script de UN SOLO USO. Busca la FC de recuperación en el DETALLE COMPLETO
de tu actividad más reciente (no en el resumen liviano que usa el script
principal). Imprime dónde la encuentra, para poder ajustar el código real.

No modifica nada en Drive ni en el historial -- solo imprime en pantalla.
"""
import os
import json
from datetime import date, timedelta
from garminconnect import Garmin

email = os.environ["GARMIN_EMAIL"]
password = os.environ["GARMIN_PASSWORD"]

api = Garmin(email, password)
api.login()

ayer = (date.today() - timedelta(days=1)).isoformat()
actividades = api.get_activities_by_date(ayer, ayer)

if not actividades:
    print(f"No hay actividades registradas el {ayer}.")
else:
    principal = max(actividades, key=lambda a: a.get("duration", 0))
    activity_id = principal.get("activityId")
    print(f"Actividad encontrada: ID {activity_id}, tipo {principal.get('activityType')}\n")

    print("=== Buscando 'recover' en el RESUMEN liviano (lo que ya usamos) ===")
    encontrado_resumen = False
    for k, v in principal.items():
        if "recover" in k.lower():
            print(f"  {k}: {v}")
            encontrado_resumen = True
    if not encontrado_resumen:
        print("  (nada encontrado aquí, como ya sabíamos)")

    print("\n=== Consultando el DETALLE COMPLETO de la actividad ===")
    detalle = api.get_activity(activity_id)

    def buscar_recover(obj, ruta=""):
        """Busca recursivamente cualquier clave que mencione 'recover'."""
        encontrados = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                nueva_ruta = f"{ruta}.{k}" if ruta else k
                if "recover" in k.lower():
                    encontrados.append((nueva_ruta, v))
                encontrados.extend(buscar_recover(v, nueva_ruta))
        elif isinstance(obj, list):
            for i, item in enumerate(obj[:3]):  # solo primeros 3 para no saturar
                encontrados.extend(buscar_recover(item, f"{ruta}[{i}]"))
        return encontrados

    resultados = buscar_recover(detalle)
    if resultados:
        print("¡Encontrado! Estas son las rutas donde aparece 'recover':\n")
        for ruta, valor in resultados:
            print(f"  {ruta} = {valor}")
    else:
        print("No se encontró ningún campo con 'recover' en el detalle completo tampoco.")
        print("Puede que este método (get_activity) siga sin traerlo -- probemos con get_activity_details.")
        detalle2 = api.get_activity_details(activity_id)
        resultados2 = buscar_recover(detalle2)
        if resultados2:
            print("\n¡Encontrado en get_activity_details!\n")
            for ruta, valor in resultados2:
                print(f"  {ruta} = {valor}")
        else:
            print("Tampoco aparece en get_activity_details.")
