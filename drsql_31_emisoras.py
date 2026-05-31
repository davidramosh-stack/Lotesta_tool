# -*- coding: utf-8 -*-
"""
DRSQL 31 - EMISORAS 1RA: DIRECTO + INVERSO + HIT RATE
Ejecutar: python drsql_31_emisoras.py
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "drlot.db"


def conectar():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"No existe la DB: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def n_int(v):
    try:
        s = "".join(c for c in str(v or "") if c.isdigit())
        return int(s[-2:]) if s else None
    except Exception:
        return None


def inverso(n):
    return int(str(n).zfill(2)[::-1])


def siguiente_fecha(fecha_str):
    d = datetime.strptime(fecha_str, "%Y-%m-%d")
    return (d + timedelta(days=1)).strftime("%Y-%m-%d")


# ─── TABLAS FEEDBACK ────────────────────────────────────────────────────────

def crear_tablas(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS historial_predicciones (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha_objetivo  TEXT NOT NULL,
            numero          INTEGER NOT NULL,
            tipo            TEXT NOT NULL,
            acierto         INTEGER DEFAULT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ranking_numeros_reales (
            numero          INTEGER PRIMARY KEY,
            veces_sugerido  INTEGER DEFAULT 0,
            veces_acierto   INTEGER DEFAULT 0,
            hit_rate        REAL DEFAULT 0
        )
    """)
    conn.commit()


# ─── VERIFICACIÓN DE PREDICCIONES ANTERIORES ────────────────────────────────

def verificar_pendientes(conn, por_fecha):
    pendientes = conn.execute("""
        SELECT id, fecha_objetivo, numero
        FROM historial_predicciones
        WHERE acierto IS NULL
    """).fetchall()

    verificados = 0
    aciertos = 0

    for row in pendientes:
        fecha_obj = row["fecha_objetivo"]
        numero = row["numero"]

        if fecha_obj not in por_fecha:
            continue

        nums_ese_dia = set(r["n1"] for r in por_fecha[fecha_obj])
        hit = 1 if numero in nums_ese_dia else 0

        conn.execute(
            "UPDATE historial_predicciones SET acierto=? WHERE id=?",
            (hit, row["id"])
        )
        verificados += 1
        aciertos += hit

    conn.commit()
    return verificados, aciertos


# ─── HIT RATE ────────────────────────────────────────────────────────────────

def recalcular_hit_rates(conn):
    filas = conn.execute("""
        SELECT numero,
               COUNT(*) AS sugerido,
               COALESCE(SUM(acierto), 0) AS aciertos
        FROM historial_predicciones
        WHERE acierto IS NOT NULL
        GROUP BY numero
    """).fetchall()

    conn.execute("DELETE FROM ranking_numeros_reales")

    for f in filas:
        hit_rate = round((f["aciertos"] / f["sugerido"]) * 100, 1) if f["sugerido"] > 0 else 0
        conn.execute("""
            INSERT INTO ranking_numeros_reales (numero, veces_sugerido, veces_acierto, hit_rate)
            VALUES (?, ?, ?, ?)
        """, (f["numero"], f["sugerido"], f["aciertos"], hit_rate))

    conn.commit()


def obtener_hit_rates(conn):
    filas = conn.execute(
        "SELECT numero, veces_sugerido, veces_acierto, hit_rate FROM ranking_numeros_reales"
    ).fetchall()
    return {f["numero"]: f for f in filas}


# ─── GUARDAR PREDICCIONES DEL DÍA ────────────────────────────────────────────

def guardar_predicciones(conn, nums_directos, nums_inversos, fecha_objetivo):
    conn.execute(
        "DELETE FROM historial_predicciones WHERE fecha_objetivo=? AND acierto IS NULL",
        (fecha_objetivo,)
    )
    for n in nums_directos:
        conn.execute(
            "INSERT INTO historial_predicciones (fecha_objetivo, numero, tipo) VALUES (?, ?, 'directo')",
            (fecha_objetivo, n)
        )
    for n in nums_inversos:
        conn.execute(
            "INSERT INTO historial_predicciones (fecha_objetivo, numero, tipo) VALUES (?, ?, 'inverso')",
            (fecha_objetivo, n)
        )
    conn.commit()


# ─── ANÁLISIS EMISORAS ───────────────────────────────────────────────────────

def obtener_datos(conn):
    rows = conn.execute("""
        SELECT s.fecha, l.nombre AS loteria, n.numero AS n1
        FROM sorteos s
        JOIN loterias l ON l.id = s.loteria_id
        JOIN numeros n ON n.sorteo_id = s.id AND n.posicion = 1
        WHERE n.numero IS NOT NULL
        ORDER BY s.fecha ASC
    """).fetchall()

    por_fecha = {}
    for r in rows:
        n1 = n_int(r["n1"])
        if n1 is None:
            continue
        fecha = str(r["fecha"])
        por_fecha.setdefault(fecha, [])
        por_fecha[fecha].append({"loteria": str(r["loteria"]), "n1": n1})

    return por_fecha


def analizar(por_fecha):
    fechas = sorted(por_fecha.keys())
    stats = {}

    def init(lot, n, fecha):
        if lot not in stats:
            stats[lot] = {
                "directo": [], "inverso": [],
                "recibio_directo": [], "recibio_inverso": [],
                "ultimo_n": n, "ultima_fecha": fecha,
            }

    for i in range(len(fechas) - 1):
        hoy = por_fecha[fechas[i]]
        manana = por_fecha[fechas[i + 1]]

        nums_hoy = set(r["n1"] for r in hoy)
        nums_manana = set(r["n1"] for r in manana)

        for r in hoy:
            lot, n = r["loteria"], r["n1"]
            inv = inverso(n)
            init(lot, n, fechas[i])
            stats[lot]["directo"].append(1 if n in nums_manana else 0)
            stats[lot]["inverso"].append(1 if (inv != n and inv in nums_manana) else 0)
            stats[lot]["ultimo_n"] = n
            stats[lot]["ultima_fecha"] = fechas[i]

        for r in manana:
            lot, n = r["loteria"], r["n1"]
            inv = inverso(n)
            init(lot, n, fechas[i + 1])
            stats[lot]["recibio_directo"].append(1 if n in nums_hoy else 0)
            stats[lot]["recibio_inverso"].append(1 if (inv != n and inv in nums_hoy) else 0)

    return stats, fechas


def racha_actual(seq):
    if not seq:
        return 0, 0
    val = seq[-1]
    count = sum(1 for _ in iter(lambda: None, None) if False)
    count = 0
    for v in reversed(seq):
        if v == val:
            count += 1
        else:
            break
    return val, count


def calcular_fila(lot, s, tipo):
    seq = s[tipo]
    if len(seq) < 20:
        return None
    total = len(seq)
    tasa = round((sum(seq) / total) * 100, 1)
    ultimos = seq[-30:]
    tasa_rec = round((sum(ultimos) / len(ultimos)) * 100, 1)
    val, largo = racha_actual(seq)
    return {
        "loteria": lot,
        "tasa": tasa,
        "tasa_reciente": tasa_rec,
        "estado": val,
        "racha": largo,
        "ultimo_n": str(s["ultimo_n"]).zfill(2),
        "inv_n": str(inverso(s["ultimo_n"])).zfill(2),
    }


def calcular_ranking(stats, tipo):
    resultado = []
    for lot, s in stats.items():
        fila = calcular_fila(lot, s, tipo)
        if fila:
            resultado.append(fila)
    resultado.sort(key=lambda x: (x["estado"], x["tasa_reciente"]), reverse=True)
    return resultado


def calcular_no_receptoras(stats):
    todas = []
    for lot, s in stats.items():
        rd, ri = s["recibio_directo"], s["recibio_inverso"]
        if len(rd) < 20:
            continue
        td = round((sum(rd) / len(rd)) * 100, 1)
        ti = round((sum(ri) / len(ri)) * 100, 1)
        todas.append({
            "loteria": lot,
            "tasa_recibio_d": td,
            "tasa_recibio_i": ti,
            "combinada": round((td + ti) / 2, 1),
            "ultimo_n": str(s["ultimo_n"]).zfill(2),
        })
    todas.sort(key=lambda x: x["combinada"])
    return todas[:5]


def calcular_debiles(stats):
    todas = []
    for lot, s in stats.items():
        fd = calcular_fila(lot, s, "directo")
        fi = calcular_fila(lot, s, "inverso")
        if not fd or not fi:
            continue
        combinada = round((fd["tasa"] + fi["tasa"]) / 2, 1)
        todas.append({
            "loteria": lot,
            "tasa_directo": fd["tasa"],
            "tasa_inverso": fi["tasa"],
            "combinada": combinada,
        })
    todas.sort(key=lambda x: x["combinada"])
    return todas[:5]


# ─── DISPLAY ─────────────────────────────────────────────────────────────────

def fmt_hit(hr_map, numero):
    n = int(numero)
    if n not in hr_map:
        return "nuevo"
    f = hr_map[n]
    return f"hit={f['hit_rate']}% ({f['veces_acierto']}/{f['veces_sugerido']})"


def mostrar_top(ranking, tipo, ultima_fecha, hr_map):
    titulo = "DIRECTOS (verde)" if tipo == "directo" else "INVERSOS (naranja)"
    print(f"\n{'='*55}")
    print(f"  TOP 5 {titulo}  |  base: {ultima_fecha}")
    print(f"{'='*55}")
    print(f"  {'#':<3} {'Lotería':<22} {'Num':<6} {'Estado':<9} {'Rec30%':<8} {'HitRate'}")
    print(f"  {'-'*53}")
    for i, r in enumerate(ranking[:5], 1):
        num = r["ultimo_n"] if tipo == "directo" else f"{r['ultimo_n']}→{r['inv_n']}"
        n_buscar = r["ultimo_n"] if tipo == "directo" else r["inv_n"]
        estado = f"ON x{r['racha']}" if r["estado"] else f"OFF x{r['racha']}"
        hit = fmt_hit(hr_map, n_buscar)
        print(f"  {i:<3} {r['loteria']:<22} {num:<6} {estado:<9} {r['tasa_reciente']:<8} {hit}")


# ─── MAIN ────────────────────────────────────────────────────────────────────

def ejecutar():
    conn = conectar()
    try:
        crear_tablas(conn)

        por_fecha = obtener_datos(conn)
        stats, fechas = analizar(por_fecha)
        ultima_fecha = fechas[-1] if fechas else "?"
        fecha_objetivo = siguiente_fecha(ultima_fecha)

        # 1. Verificar predicciones anteriores
        verificados, aciertos = verificar_pendientes(conn, por_fecha)

        # 2. Recalcular hit rates
        recalcular_hit_rates(conn)
        hr_map = obtener_hit_rates(conn)

        # 3. Rankings
        rank_d = calcular_ranking(stats, "directo")
        rank_i = calcular_ranking(stats, "inverso")
        no_rec = calcular_no_receptoras(stats)
        debiles = calcular_debiles(stats)

        # 4. Guardar predicciones de hoy
        nums_d = [int(r["ultimo_n"]) for r in rank_d[:5]]
        nums_i = [int(r["inv_n"]) for r in rank_i[:5]]
        guardar_predicciones(conn, nums_d, nums_i, fecha_objetivo)

        # ─── OUTPUT ──────────────────────────────────────────────────────────
        print("\n" + "=" * 55)
        print("  EMISORAS 1RA — DIRECTO + INVERSO + HIT RATE")
        print("=" * 55)
        print(f"  Última fecha DB     : {ultima_fecha}")
        print(f"  Prediciendo para    : {fecha_objetivo}")
        print(f"  Loterías analizadas : {len(stats)}")
        if verificados:
            print(f"  Verificados hoy     : {verificados} predicciones → {aciertos} aciertos")

        mostrar_top(rank_d, "directo", ultima_fecha, hr_map)
        mostrar_top(rank_i, "inverso", ultima_fecha, hr_map)

        print(f"\n  NÚMEROS A VIGILAR PARA {fecha_objetivo}")
        print(f"  Directos : {' '.join(str(n).zfill(2) for n in nums_d)}")
        print(f"  Inversos : {' '.join(str(n).zfill(2) for n in nums_i)}")

        print(f"\n{'='*55}")
        print(f"  NO RECIBEN DEL DÍA ANTERIOR (número fresco)")
        print(f"{'='*55}")
        print(f"  {'Lotería':<26} {'n1':<5} {'RecD%':<8} {'RecI%'}")
        print(f"  {'-'*45}")
        for r in no_rec:
            print(f"  {r['loteria']:<26} {r['ultimo_n']:<5} {r['tasa_recibio_d']:<8} {r['tasa_recibio_i']}")

        print(f"\n{'='*55}")
        print(f"  LOTERÍAS MÁS DÉBILES (emiten menos)")
        print(f"{'='*55}")
        print(f"  {'Lotería':<26} {'Dir%':<8} {'Inv%':<8} {'Prom%'}")
        print(f"  {'-'*45}")
        for r in debiles:
            print(f"  {r['loteria']:<26} {r['tasa_directo']:<8} {r['tasa_inverso']:<8} {r['combinada']}")

        if hr_map:
            top_hr = sorted(hr_map.values(), key=lambda x: x["hit_rate"], reverse=True)[:5]
            print(f"\n{'='*55}")
            print(f"  TOP NÚMEROS POR HIT RATE HISTÓRICO")
            print(f"{'='*55}")
            print(f"  {'Num':<6} {'Sugerido':<10} {'Aciertos':<10} {'HitRate%'}")
            print(f"  {'-'*40}")
            for f in top_hr:
                print(f"  {str(f['numero']).zfill(2):<6} {f['veces_sugerido']:<10} {f['veces_acierto']:<10} {f['hit_rate']}")

        print()

    finally:
        conn.close()


if __name__ == "__main__":
    ejecutar()
