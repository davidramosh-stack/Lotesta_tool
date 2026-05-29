# -*- coding: utf-8 -*-
"""
DRSQL 31 - EMISORAS 1RA (DIRECTO + INVERSO)
Ejecutar: python drsql_31_emisoras.py
"""

import sqlite3
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
    s = str(n).zfill(2)
    return int(s[::-1])


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
    stats = {}  # loteria -> {directo: [], inverso: []}

    for i in range(len(fechas) - 1):
        hoy = por_fecha[fechas[i]]
        manana = por_fecha[fechas[i + 1]]

        nums_manana = set(r["n1"] for r in manana)

        for r in hoy:
            lot = r["loteria"]
            n = r["n1"]
            inv = inverso(n)

            if lot not in stats:
                stats[lot] = {"directo": [], "inverso": [], "ultimo_n": n, "ultima_fecha": fechas[i]}

            stats[lot]["directo"].append(1 if n in nums_manana else 0)
            stats[lot]["inverso"].append(1 if (inv != n and inv in nums_manana) else 0)
            stats[lot]["ultimo_n"] = n
            stats[lot]["ultima_fecha"] = fechas[i]

    return stats, fechas


def racha_actual(seq):
    if not seq:
        return 0, 0
    val = seq[-1]
    count = 0
    for v in reversed(seq):
        if v == val:
            count += 1
        else:
            break
    return val, count


UMBRAL_MINIMO = 15.0  # tasa mínima para considerar que el método aplica


def calcular_fila(lot, s, tipo):
    seq = s[tipo]
    if len(seq) < 20:
        return None

    total = len(seq)
    tasa = round((sum(seq) / total) * 100, 1)
    ultimos = seq[-30:]
    tasa_reciente = round((sum(ultimos) / len(ultimos)) * 100, 1)
    val, largo = racha_actual(seq)

    return {
        "loteria": lot,
        "tasa": tasa,
        "tasa_reciente": tasa_reciente,
        "estado": val,
        "racha": largo,
        "ultimo_n": str(s["ultimo_n"]).zfill(2),
        "inv_n": str(inverso(s["ultimo_n"])).zfill(2),
        "ultima_fecha": s["ultima_fecha"],
    }


def calcular_ranking(stats, tipo):
    resultados = []

    for lot, s in stats.items():
        fila = calcular_fila(lot, s, tipo)
        if fila and fila["tasa"] >= UMBRAL_MINIMO:
            resultados.append(fila)

    resultados.sort(key=lambda x: (x["estado"], x["tasa_reciente"]), reverse=True)
    return resultados


def calcular_descartadas(stats):
    descartadas = []

    for lot, s in stats.items():
        fd = calcular_fila(lot, s, "directo")
        fi = calcular_fila(lot, s, "inverso")

        if fd is None or fi is None:
            continue

        td = fd["tasa"]
        ti = fi["tasa"]

        if td < UMBRAL_MINIMO and ti < UMBRAL_MINIMO:
            descartadas.append({
                "loteria": lot,
                "tasa_directo": td,
                "tasa_inverso": ti,
            })

    descartadas.sort(key=lambda x: x["tasa_directo"] + x["tasa_inverso"])
    return descartadas


def mostrar(ranking, tipo, ultima_fecha):
    titulo = "DIRECTOS (verde)" if tipo == "directo" else "INVERSOS (naranja)"
    print(f"\n{'='*50}")
    print(f"  TOP 5 {titulo}")
    print(f"  Fecha base: {ultima_fecha}")
    print(f"{'='*50}")
    print(f"{'#':<3} {'Lotería':<22} {'Num':<5} {'Est':<8} {'Tasa%':<8} {'Rec30%'}")
    print("-" * 50)

    for i, r in enumerate(ranking[:5], 1):
        num = r["ultimo_n"] if tipo == "directo" else f"{r['ultimo_n']}→{r['inv_n']}"
        estado = f"ON x{r['racha']}" if r["estado"] else f"OFF x{r['racha']}"
        print(f"{i:<3} {r['loteria']:<22} {num:<5} {estado:<8} {r['tasa']:<8} {r['tasa_reciente']}")


def ejecutar():
    conn = conectar()
    try:
        por_fecha = obtener_datos(conn)
        stats, fechas = analizar(por_fecha)

        ultima_fecha = fechas[-1] if fechas else "?"

        rank_directo = calcular_ranking(stats, "directo")
        rank_inverso = calcular_ranking(stats, "inverso")
        total_activas = len(set([r["loteria"] for r in rank_directo] + [r["loteria"] for r in rank_inverso]))

        print("\n" + "=" * 50)
        print("  EMISORAS 1RA - DIRECTO + INVERSO")
        print("=" * 50)
        print(f"  Loterías analizadas : {len(stats)}")
        print(f"  Con método activo   : {total_activas}")
        print(f"  Fechas en DB        : {len(fechas)}")
        print(f"  Última fecha        : {ultima_fecha}")

        mostrar(rank_directo, "directo", ultima_fecha)
        mostrar(rank_inverso, "inverso", ultima_fecha)

        print("\nNÚMEROS A VIGILAR:")
        directos = " ".join(r["ultimo_n"] for r in rank_directo[:5])
        inversos = " ".join(r["inv_n"] for r in rank_inverso[:5])
        print(f"  Directos : {directos}")
        print(f"  Inversos : {inversos}")

        descartadas = calcular_descartadas(stats)
        if descartadas:
            print(f"\n{'='*50}")
            print(f"  LOTERÍAS SIN MÉTODO (directo + inverso < {UMBRAL_MINIMO}%)")
            print(f"{'='*50}")
            print(f"{'Lotería':<28} {'Directo%':<12} {'Inverso%'}")
            print("-" * 50)
            for r in descartadas:
                print(f"  {r['loteria']:<26} {r['tasa_directo']:<12} {r['tasa_inverso']}")

        print()

    finally:
        conn.close()


if __name__ == "__main__":
    ejecutar()
