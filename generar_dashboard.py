"""
generar_dashboard.py
----------------------
Genera dashboard.html completo a partir de garmin_historial.csv (y, si existe,
el plan de entrenamiento vigente). No hay ningún número escrito a mano -- todo
se calcula de nuevo cada vez que corre este script.

Uso: python generar_dashboard.py <ruta_historial.csv> [<ruta_plan.csv>]
Genera: dashboard.html en el directorio actual.
"""

import sys
import csv
import json
import statistics as st
from datetime import date, timedelta, datetime
from collections import defaultdict

FC_MAX_REFERENCIA = 181  # ajustar tras cada test de FC max; ver README

PIE = {"running", "trail_running", "treadmill_running", "walking", "mountaineering", "other"}
BICI = {"cycling", "indoor_cycling"}
CORRER = {"running", "trail_running", "treadmill_running"}


def f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def cargar_historial(ruta):
    with open(ruta, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def resumen_mensual(rows):
    meses = defaultdict(lambda: {"hrv": [], "fc": [], "sueno": [], "vo2max": [], "spo2": []})
    for r in rows:
        mes = r["fecha"][:7]
        if f(r.get("hrv_promedio_ms")) is not None:
            meses[mes]["hrv"].append(f(r["hrv_promedio_ms"]))
        if f(r.get("fc_reposo")) is not None:
            meses[mes]["fc"].append(f(r["fc_reposo"]))
        if f(r.get("sueno_horas")) is not None:
            meses[mes]["sueno"].append(f(r["sueno_horas"]))
        if f(r.get("vo2_max")) is not None:
            meses[mes]["vo2max"].append(f(r["vo2_max"]))
        if f(r.get("spo2_promedio_nocturno")) is not None:
            meses[mes]["spo2"].append(f(r["spo2_promedio_nocturno"]))
    salida = []
    for mes in sorted(meses):
        d = meses[mes]
        salida.append({
            "mes": mes,
            "hrv": round(st.mean(d["hrv"]), 1) if d["hrv"] else None,
            "n_hrv": len(d["hrv"]),
            "fc": round(st.mean(d["fc"]), 1) if d["fc"] else None,
            "n_fc": len(d["fc"]),
            "sueno": round(st.mean(d["sueno"]), 2) if d["sueno"] else None,
            "n_sueno": len(d["sueno"]),
            "vo2max": round(st.mean(d["vo2max"]), 1) if d["vo2max"] else None,
            "spo2": round(st.mean(d["spo2"]), 1) if d["spo2"] else None,
            "n_spo2": len(d["spo2"]),
        })
    return salida


def promedio_en_rango(rows, dias, campo):
    fecha_max = date.fromisoformat(rows[-1]["fecha"])
    fecha_min = fecha_max - timedelta(days=dias - 1)
    vals = [f(r[campo]) for r in rows if fecha_min <= date.fromisoformat(r["fecha"]) <= fecha_max and f(r.get(campo)) is not None]
    return round(st.mean(vals), 2) if vals else None


def analisis_periodo(rows, dias, etiqueta):
    fecha_max = date.fromisoformat(rows[-1]["fecha"])
    fecha_min = fecha_max - timedelta(days=dias - 1)
    fecha_min_prev = fecha_min - timedelta(days=dias)
    en_rango = [r for r in rows if fecha_min <= date.fromisoformat(r["fecha"]) <= fecha_max]
    en_rango_prev = [r for r in rows if fecha_min_prev <= date.fromisoformat(r["fecha"]) < fecha_min]

    def prom(filas, campo):
        vals = [f(r[campo]) for r in filas if f(r.get(campo)) is not None]
        return round(st.mean(vals), 1) if vals else None

    hrv, hrv_prev = prom(en_rango, "hrv_promedio_ms"), prom(en_rango_prev, "hrv_promedio_ms")
    fc, fc_prev = prom(en_rango, "fc_reposo"), prom(en_rango_prev, "fc_reposo")
    sueno, sueno_prev = prom(en_rango, "sueno_horas"), prom(en_rango_prev, "sueno_horas")

    dist = round(sum(f(r.get("actividad_distancia_km")) or 0 for r in en_rango), 1)
    desn = round(sum(f(r.get("actividad_desnivel_positivo_m")) or 0 for r in en_rango))
    dias_act = sum(1 for r in en_rango if r.get("actividad_tipo"))

    frases = []

    if hrv is not None and hrv_prev is not None:
        cambio = round((hrv - hrv_prev) / hrv_prev * 100)
        direccion = "mejoró" if cambio > 3 else ("empeoró" if cambio < -3 else "se mantuvo estable")
        frases.append(f"HRV promedio {hrv} ms ({direccion}, {cambio:+d}% vs. el período previo de {dias} días).")
    elif hrv is not None:
        frases.append(f"HRV promedio {hrv} ms (sin período previo completo para comparar).")

    if fc is not None and fc_prev is not None:
        cambio = round((fc - fc_prev) / fc_prev * 100)
        direccion = "mejoró" if cambio < -2 else ("empeoró" if cambio > 2 else "se mantuvo estable")
        frases.append(f"FC en reposo promedio {fc} lpm ({direccion}, {cambio:+d}% vs. el período previo).")

    if sueno is not None:
        alerta = " -- por debajo de la meta de 7h" if sueno < 7 else ""
        frases.append(f"Sueño promedio {sueno}h{alerta}.")

    frases.append(f"{dias_act} días con actividad, {dist} km recorridos, {desn} m de desnivel acumulado.")

    return {"titulo": etiqueta, "frases": frases}


def resumen_pmc_actual(pmc):
    if not pmc:
        return None
    ultimo = pmc[-1]
    tsb = ultimo["tsb"]
    if tsb > 5:
        lectura = "descansado, con margen para asumir carga fuerte"
    elif tsb > -10:
        lectura = "en equilibrio, carga sostenible"
    elif tsb > -30:
        lectura = "cargado -- normal en bloques de entreno duro, vigilar los próximos días"
    else:
        lectura = "muy fatigado -- riesgo elevado, considerar descanso"
    return f"TSB actual: {tsb} ({lectura})."


def carga_semanal_por_tipo(rows):
    semanas = defaultdict(lambda: {"correr": 0, "bici": 0, "fuerza": 0})
    for r in rows:
        if not r.get("actividad_tipo"):
            continue
        fecha = date.fromisoformat(r["fecha"])
        dur = f(r.get("actividad_duracion_min")) or 0
        tipo = r["actividad_tipo"]
        year, week, _ = fecha.isocalendar()
        lunes = date.fromisocalendar(year, week, 1).isoformat()
        if tipo in CORRER:
            semanas[lunes]["correr"] += dur
        elif tipo in BICI:
            semanas[lunes]["bici"] += dur
        elif tipo == "strength_training":
            semanas[lunes]["fuerza"] += dur
    return [{"semana": s, **{k: round(v) for k, v in vals.items()}} for s, vals in sorted(semanas.items())]


def cumplimiento_semanal(rows):
    semanas = defaultdict(int)
    for r in rows:
        if r.get("actividad_tipo") in PIE or r.get("actividad_tipo") in BICI:
            fecha = date.fromisoformat(r["fecha"])
            year, week, _ = fecha.isocalendar()
            lunes = date.fromisocalendar(year, week, 1).isoformat()
            semanas[lunes] += 1
    return [{"semana": s, "n": n} for s, n in sorted(semanas.items())]


def eficiencia_aerobica_mensual(rows, densidad_max=15):
    meses = defaultdict(list)
    for r in rows:
        tipo = r.get("actividad_tipo")
        dist = f(r.get("actividad_distancia_km"))
        desn = f(r.get("actividad_desnivel_positivo_m")) or 0
        fc = f(r.get("actividad_fc_promedio"))
        dur = f(r.get("actividad_duracion_min"))
        if tipo not in CORRER or not dist or not fc or not dur or dist <= 0:
            continue
        if desn / dist > densidad_max:
            continue
        velocidad_kmh = dist / (dur / 60)
        ef = velocidad_kmh / fc
        meses[r["fecha"][:7]].append(ef)
    return [{"mes": m, "ef": round(st.mean(v), 4), "n": len(v)} for m, v in sorted(meses.items())]


def exposicion_altitud_mensual(rows, umbral=2000):
    meses = defaultdict(lambda: [0, 0])
    for r in rows:
        dur = f(r.get("actividad_duracion_min"))
        alt = f(r.get("actividad_altitud_max_msnm"))
        if not dur or alt is None:
            continue
        mes = r["fecha"][:7]
        meses[mes][1] += dur
        if alt >= umbral:
            meses[mes][0] += dur
    return [{"mes": m, "pct": round(v[0] / v[1] * 100) if v[1] else 0} for m, v in sorted(meses.items())]


def carga_diaria_proxy(rows):
    """TRIMP de Banister (1991) -- la version validada cientificamente, usando
    FC de reserva (no solo %FC max). Requiere FC en reposo del dia + FC
    promedio de la actividad; ambos datos ya los capturamos.
    y = 0.64 * e^(1.92 * HRr) es la constante para hombres (Banister usa 1.67
    para mujeres). Cambiar el exponente si corresponde.
    """
    import math
    cargas = {}
    for r in rows:
        dur = f(r.get("actividad_duracion_min")) or 0
        fc_actividad = f(r.get("actividad_fc_promedio"))
        fc_reposo = f(r.get("fc_reposo"))
        if not dur or not fc_actividad or not fc_reposo:
            cargas[r["fecha"]] = 0
            continue
        hrr = (fc_actividad - fc_reposo) / (FC_MAX_REFERENCIA - fc_reposo)
        hrr = max(0, min(1, hrr))  # acotar a [0,1] por seguridad
        y = 0.64 * math.exp(1.92 * hrr)
        cargas[r["fecha"]] = dur * hrr * y
    return cargas


def ctl_atl_tsb(rows):
    cargas = carga_diaria_proxy(rows)
    fechas = sorted(cargas.keys())
    if not fechas:
        return []
    inicio = date.fromisoformat(fechas[0])
    fin = date.fromisoformat(fechas[-1])
    serie = []
    d = inicio
    ctl = atl = 0.0
    while d <= fin:
        c = cargas.get(d.isoformat(), 0)
        ctl += (c - ctl) / 42
        atl += (c - atl) / 7
        serie.append({"fecha": d.isoformat(), "ctl": round(ctl, 1), "atl": round(atl, 1), "tsb": round(ctl - atl, 1)})
        d += timedelta(days=1)
    return serie


def estado_del_dia(rows):
    ultimo = rows[-1]
    anteriores = rows[-31:-1] if len(rows) > 30 else rows[:-1]

    hrv_base = [f(r["hrv_promedio_ms"]) for r in anteriores if f(r.get("hrv_promedio_ms"))]
    fc_base = [f(r["fc_reposo"]) for r in anteriores if f(r.get("fc_reposo"))]

    hrv_hoy = f(ultimo.get("hrv_promedio_ms"))
    fc_hoy = f(ultimo.get("fc_reposo"))
    sueno_hoy = f(ultimo.get("sueno_horas"))

    hrv_prom = round(st.mean(hrv_base), 1) if hrv_base else None
    fc_prom = round(st.mean(fc_base), 1) if fc_base else None

    alertas = []
    criterios = []

    if hrv_hoy is not None and hrv_prom:
        pct = round(hrv_hoy / hrv_prom * 100)
        alerta = pct < 90
        if alerta:
            alertas.append("hrv")
        criterios.append({"label": "HRV vs. promedio 30 días",
                           "detalle": f"{hrv_hoy} ms · {pct}% del promedio ({hrv_prom})",
                           "alerta": alerta})
    if sueno_hoy is not None:
        alerta = sueno_hoy < 6.5
        if alerta:
            alertas.append("sueno")
        criterios.append({"label": "Sueño anoche", "detalle": f"{sueno_hoy}h · meta 7h", "alerta": alerta})
    if fc_hoy is not None and fc_prom:
        pct = round(fc_hoy / fc_prom * 100)
        alerta = pct > 105
        if alerta:
            alertas.append("fc")
        criterios.append({"label": "FC en reposo vs. promedio 30 días",
                           "detalle": f"{fc_hoy} lpm · {pct}% del promedio ({fc_prom})",
                           "alerta": alerta})

    n_alertas = len(alertas)
    estado = "Verde" if n_alertas == 0 else ("Amarillo" if n_alertas == 1 else "Rojo")
    return {
        "estado": estado,
        "fecha": ultimo["fecha"],
        "fc_reposo": fc_hoy,
        "criterios": criterios,
    }


def cargar_plan(ruta):
    if not ruta:
        return None
    try:
        with open(ruta, encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
    except FileNotFoundError:
        return None


AREA_POR_SESION = {
    "trote_montana": "Aeróbico",
    "fondo_plano": "Deriva del domingo",
    "ruck": "Ruck",
    "gym_A": "Gym",
    "gym_B": "Gym",
}


def semaforo_semana(rows, plan):
    if not plan:
        return None, "Sin plan cargado."

    hoy = date.fromisoformat(rows[-1]["fecha"])
    fechas_plan = sorted(p["fecha"] for p in plan)
    if hoy < fechas_plan[0]:
        return [], f"El plan todavía no empieza (arranca {fechas_plan[0]})."

    # ultima semana lunes-domingo ya completa dentro del rango del plan
    year, week, _ = hoy.isocalendar()
    lunes_actual = date.fromisocalendar(year, week, 1)
    fin_semana_revisar = lunes_actual - timedelta(days=1)  # domingo pasado
    inicio_semana_revisar = fin_semana_revisar - timedelta(days=6)

    historial_por_fecha = {r["fecha"]: r for r in rows}
    resultados = {}
    d = inicio_semana_revisar
    while d <= fin_semana_revisar:
        fila_plan = next((p for p in plan if p["fecha"] == d.isoformat()), None)
        fila_real = historial_por_fecha.get(d.isoformat())
        if fila_plan:
            sesion = fila_plan.get("sesion", "")
            area = AREA_POR_SESION.get(sesion)
            if area:
                resultados.setdefault(area, []).append((fila_plan, fila_real))
        d += timedelta(days=1)

    semaforo = []
    for area, pares in resultados.items():
        alertas = 0
        for fila_plan, fila_real in pares:
            hecho = fila_real and fila_real.get("actividad_tipo")
            if not hecho:
                alertas += 1
        estado = "verde" if alertas == 0 else ("amarillo" if alertas == 1 else "rojo")
        semaforo.append({"area": area, "estado": estado, "alertas": alertas})

    return semaforo, f"Semana revisada: {inicio_semana_revisar} a {fin_semana_revisar}"


def generar_html(datos):
    with open(__file__.replace("generar_dashboard.py", "dashboard_template.html"), encoding="utf-8") as fh:
        plantilla = fh.read()
    return plantilla.replace("__DATOS_JSON__", json.dumps(datos, ensure_ascii=False))


def main():
    ruta_historial = sys.argv[1]
    ruta_plan = sys.argv[2] if len(sys.argv) > 2 else None

    rows = cargar_historial(ruta_historial)
    plan = cargar_plan(ruta_plan)

    semaforo, nota_semaforo = semaforo_semana(rows, plan)

    pmc = ctl_atl_tsb(rows)

    analisis_4sem = analisis_periodo(rows, 28, "Últimas 4 semanas")
    analisis_6mes = analisis_periodo(rows, 182, "Últimos 6 meses")
    nota_pmc = resumen_pmc_actual(pmc)
    if nota_pmc:
        analisis_4sem["frases"].append(nota_pmc)

    datos = {
        "generado": datetime.now().isoformat(timespec="minutes"),
        "mensual": resumen_mensual(rows),
        "carga_semanal": carga_semanal_por_tipo(rows),
        "cumplimiento": cumplimiento_semanal(rows),
        "eficiencia": eficiencia_aerobica_mensual(rows),
        "altitud": exposicion_altitud_mensual(rows),
        "pmc": pmc,
        "hoy": estado_del_dia(rows),
        "semaforo": semaforo,
        "nota_semaforo": nota_semaforo,
        "analisis": [analisis_4sem, analisis_6mes],
    }

    html = generar_html(datos)
    with open("dashboard.html", "w", encoding="utf-8") as fh:
        fh.write(html)
    print("dashboard.html generado.")


if __name__ == "__main__":
    main()
