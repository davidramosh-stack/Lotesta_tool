#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DR001 ANGUILA 10AM — Motor especializado con IA V5 + Gráfica Dinámica
Ruta Android: /storage/emulated/0/Download/DR001_PRO
"""

import os, json, re, time, signal, threading, requests, math
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from flask import Flask, jsonify, request, render_template_string

app = Flask(__name__)

# ══════════════════════════════════════════════════════════
# CONFIGURACIÓN — solo Anguilla 10AM
# ══════════════════════════════════════════════════════════
LOTERIA_OBJETIVO = "Anguilla 10AM"
ALIAS_10AM = [
    "anguilla 10am","anguila 10am","anguilla 10 am","anguila 10 am",
    "anguilla 10:00","anguila 10:00","anguilla10am","anguila10am",
]

def es_objetivo(nombre):
    n=(nombre or "").lower().strip()
    n=n.replace("á","a").replace("é","e").replace("í","i").replace("ó","o").replace("ú","u")
    for a in ALIAS_10AM:
        if a in n: return True
    return False

def nombre_objetivo_en_biblia(registros):
    for r in registros:
        if es_objetivo(r.get("loteria","")):
            return r["loteria"]
    return None

# ══════════════════════════════════════════════════════════
# RUTAS
# ══════════════════════════════════════════════════════════
BASE = "/storage/emulated/0/Download/DR001_PRO"
REPOSITORIO = os.path.join(BASE,"repositorio")
MEMORIA     = os.path.join(BASE,"memoria")
REPORTES    = os.path.join(BASE,"reportes")
BACKUPS     = os.path.join(BASE,"backups")
CORE        = os.path.join(BASE,"core")
MEM_LOTERIAS= os.path.join(MEMORIA,"loterias")
for d in [BASE,REPOSITORIO,MEMORIA,MEM_LOTERIAS,REPORTES,BACKUPS,CORE]:
    os.makedirs(d,exist_ok=True)

HEADERS={"User-Agent":"Mozilla/5.0"}

progreso={"corriendo":False,"log":[],"ok":0,"err":0,"archivo_actual":"","ultimo_guardado":"","modo":"idle"}
aprendizaje={"corriendo":False,"log":[],"loteria_actual":"","loteria_index":0,"loterias_total":0,"eventos":0,"eventos_total":0,"ultimo_guardado":"","inicio":"","fin":"","estado":"idle"}

# ══════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════
def log(msg):
    ts=datetime.now().strftime("%H:%M:%S")
    linea=f"[{ts}] {msg}"
    progreso["log"].append(linea); print(linea)
    if len(progreso["log"])>500: progreso["log"]=progreso["log"][-500:]

def log_ap(msg):
    ts=datetime.now().strftime("%H:%M:%S")
    linea=f"[{ts}] {msg}"
    aprendizaje["log"].append(linea); print(linea)
    if len(aprendizaje["log"])>800: aprendizaje["log"]=aprendizaje["log"][-800:]

def safe_name(nombre):
    s=re.sub(r"[^A-Za-z0-9_-]+","_",nombre.strip())
    return s[:80] if s else "sin_nombre"

def inverso(n):
    n=str(n).zfill(2)[-2:]
    return n[::-1]

def limpiar_numero(n):
    n=str(n).strip()
    if not n.isdigit(): return ""
    return n.zfill(2)[-2:]

# ══════════════════════════════════════════════════════════
# CARGADOR
# ══════════════════════════════════════════════════════════
def descargar_dia(fecha_str):
    url=f"https://enloteria.com/resultados-loterias-{fecha_str}"
    try:
        r=requests.get(url,headers=HEADERS,timeout=20)
        if r.status_code!=200: return []
        blocks=re.findall(r'<script type="application/ld\+json">(.*?)</script>',r.text,re.DOTALL)
        resultados=[]
        for b in blocks:
            try:
                d=json.loads(b)
                for item in d.get("@graph",[]):
                    if item.get("@type")!="Event": continue
                    nombre=item.get("name","").strip()
                    props={p.get("name",""):p.get("value","") for p in item.get("additionalProperty",[])}
                    p1=limpiar_numero(props.get("Primer Premio",""))
                    p2=limpiar_numero(props.get("Segundo Premio",""))
                    p3=limpiar_numero(props.get("Tercer Premio",""))
                    if not p1: continue
                    numeros=[p1]
                    if p2: numeros.append(p2)
                    if p3: numeros.append(p3)
                    if len(numeros)>=3:
                        resultados.append({"fecha":fecha_str,"loteria":nombre,"numeros":numeros[:3]})
            except: pass
        return resultados
    except: return []

def guardar_mes(anio,mes,registros):
    archivo=os.path.join(REPOSITORIO,f"{anio}_{str(mes).zfill(2)}.json")
    existentes=[]
    if os.path.exists(archivo):
        try:
            with open(archivo,"r",encoding="utf-8") as f: existentes=json.load(f)
        except: existentes=[]
    indice={}
    for r in existentes: indice[(r.get("fecha"),r.get("loteria"))]=r
    for r in registros:  indice[(r.get("fecha"),r.get("loteria"))]=r
    final=sorted(indice.values(),key=lambda x:(x.get("fecha",""),x.get("loteria","")))
    with open(archivo,"w",encoding="utf-8") as f: json.dump(final,f,ensure_ascii=False,indent=2)
    progreso["ultimo_guardado"]=archivo
    return len(final)

def correr_carga(anio,mes_ini,mes_fin):
    progreso["corriendo"]=True; progreso["modo"]="carga"
    progreso["log"]=[]; progreso["ok"]=0; progreso["err"]=0
    log("🚀 INICIANDO CARGA")
    for mes in range(mes_ini,mes_fin+1):
        try:
            inicio=datetime(anio,mes,1)
            fin=datetime(anio,mes+1,1)-timedelta(days=1) if mes<12 else datetime(anio+1,1,1)-timedelta(days=1)
            hoy=datetime.now().replace(hour=0,minute=0,second=0,microsecond=0)
            if fin>hoy: fin=hoy
            buffer=[]; fecha=inicio
            log(f"📅 Cargando {anio}-{str(mes).zfill(2)}")
            while fecha<=fin:
                fs=fecha.strftime("%Y-%m-%d"); progreso["archivo_actual"]=fs
                data=descargar_dia(fs)
                if data: buffer.extend(data); progreso["ok"]+=1; log(f"✅ {fs}: {len(data)}")
                else: progreso["err"]+=1; log(f"⚠️ {fs}: sin datos")
                fecha+=timedelta(days=1); time.sleep(0.35)
            if buffer:
                total=guardar_mes(anio,mes,buffer)
                log(f"💾 Guardado {anio}_{str(mes).zfill(2)}.json: {total} registros")
        except Exception as e: log(f"❌ Error mes {mes}: {e}"); progreso["err"]+=1
    log("✨ CARGA TERMINADA"); progreso["corriendo"]=False; progreso["modo"]="idle"

# ══════════════════════════════════════════════════════════
# BIBLIA
# ══════════════════════════════════════════════════════════
def leer_toda_biblia():
    registros=[]; archivos=sorted([f for f in os.listdir(REPOSITORIO) if f.endswith(".json")]); errores=[]
    for archivo in archivos:
        ruta=os.path.join(REPOSITORIO,archivo)
        try:
            with open(ruta,"r",encoding="utf-8") as f: data=json.load(f)
            if isinstance(data,list):
                for r in data:
                    rr=dict(r); rr["_archivo"]=archivo
                    if rr.get("fecha") and rr.get("loteria") and isinstance(rr.get("numeros"),list):
                        rr["numeros"]=[limpiar_numero(x) for x in rr.get("numeros",[]) if limpiar_numero(x)]
                        if len(rr["numeros"])>=3: registros.append(rr)
        except Exception as e: errores.append(f"{archivo}: {e}")
    return archivos,registros,errores

def preparar_indices(registros):
    por_loteria=defaultdict(list); por_fecha=defaultdict(list)
    for r in registros: por_loteria[r["loteria"]].append(r); por_fecha[r["fecha"]].append(r)
    for lot in por_loteria: por_loteria[lot].sort(key=lambda x:x["fecha"])
    return por_loteria,por_fecha,sorted(por_fecha.keys())

# ══════════════════════════════════════════════════════════
# MOTOR DE SCORE
# ══════════════════════════════════════════════════════════
def calcular_score_candidatos(hist_lot,fecha_actual,por_fecha):
    candidatos={}; nums=[str(i).zfill(2) for i in range(100)]
    prev=[r for r in hist_lot if r["fecha"]<fecha_actual]
    if not prev: return {n:0.0 for n in nums}
    primeras=[r["numeros"][0] for r in prev if r.get("numeros")]
    segundas=[r["numeros"][1] for r in prev if len(r.get("numeros",[]))>1]
    terceras=[r["numeros"][2] for r in prev if len(r.get("numeros",[]))>2]
    c1=Counter(primeras); c2=Counter(segundas); c3=Counter(terceras)
    ultimo_idx={}
    for idx,r in enumerate(prev):
        if r.get("numeros"): ultimo_idx[r["numeros"][0]]=idx
    total_prev=len(prev); media_freq=total_prev/100 if total_prev else 1
    try:
        d_actual=datetime.strptime(fecha_actual,"%Y-%m-%d")
        ayer=(d_actual-timedelta(days=1)).strftime("%Y-%m-%d")
    except: ayer=""
    nums_ayer=[]; 
    for rr in por_fecha.get(ayer,[]): nums_ayer.extend(rr.get("numeros",[]))
    conteo_ayer=Counter(nums_ayer)
    ult7=prev[-7:]; ult15=prev[-15:]
    nums_ult7=[]; nums_ult15=[]
    for r in ult7: nums_ult7.extend(r.get("numeros",[]))
    for r in ult15: nums_ult15.extend(r.get("numeros",[]))
    c7=Counter(nums_ult7); c15=Counter(nums_ult15)
    T=max(total_prev,1)  # normalizador — escala fija sin importar cuántos datos
    for n in nums:
        score=0.0; inv=inverso(n)
        # ── Frecuencia NORMALIZADA por total (escala siempre igual) ──────────
        score+=(c1[n]/T)*1000.0+(c2[n]/T)*400.0+(c3[n]/T)*250.0
        score+=(c1[inv]/T)*350.0+(c2[inv]/T)*150.0+(c3[inv]/T)*100.0
        # ── Recencia (ventanas fijas 7/15 — no crece con el tiempo) ──────────
        score+=c7[n]*8.0+c15[n]*4.0+c7[inv]*3.0
        # ── Ayer global (acotado por cantidad de loterías del día) ────────────
        score+=conteo_ayer[n]*12.0+conteo_ayer[inv]*5.0
        # ── Atraso (bonus/penalidad fija) ─────────────────────────────────────
        atraso=(total_prev-1)-ultimo_idx[n] if n in ultimo_idx else total_prev+20
        if 5<=atraso<=28: score+=35.0
        elif 29<=atraso<=60: score+=18.0
        elif atraso<=2: score-=18.0
        elif atraso>160: score-=10.0
        # ── Quemado: más del doble de frecuencia esperada y muy reciente ──────
        freq_rate=c1[n]/T
        if freq_rate>0.028 and atraso<=7: score-=25.0  # 2.8× la freq esperada (1/100=0.01)
        candidatos[n]=round(score,4)
    return candidatos

MIN_WARMUP = 50  # sorteos mínimos antes de que el score se estabiliza

# ══════════════════════════════════════════════════════════
# APRENDIZAJE
# ══════════════════════════════════════════════════════════
def cargar_estado_aprendizaje():
    ruta=os.path.join(MEMORIA,"estado_aprendizaje_total_pro.json")
    if os.path.exists(ruta):
        try:
            with open(ruta,"r",encoding="utf-8") as f: return json.load(f)
        except: pass
    return {"completadas":[],"actual":"","fecha_inicio":"","fecha_fin":"","ultima_actualizacion":""}

def guardar_estado_aprendizaje(estado):
    ruta=os.path.join(MEMORIA,"estado_aprendizaje_total_pro.json")
    estado["ultima_actualizacion"]=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(ruta,"w",encoding="utf-8") as f: json.dump(estado,f,ensure_ascii=False,indent=2)

def analizar_loteria_total_pro(loteria,registros_loteria,por_fecha):
    eventos=[]; scores_ganadores=[]; rankings_ganadores=[]
    aciertos_top5=0; aciertos_top10=0; total_eval=0
    frecuencia_ganadora=Counter(); atraso_ganador=[]; score_por_fecha=[]
    registros_loteria=sorted(registros_loteria,key=lambda x:x["fecha"])
    for i,r in enumerate(registros_loteria):
        fecha=r["fecha"]; real=r["numeros"][0]
        if i==0: continue
        scores=calcular_score_candidatos(registros_loteria[:i],fecha,por_fecha)
        ranking=sorted(scores.items(),key=lambda x:x[1],reverse=True)
        rank_real=None; score_real=scores.get(real,0)
        for pos,(num,sc) in enumerate(ranking,start=1):
            if num==real: rank_real=pos; break
        top5=[n for n,s in ranking[:5]]; top10=[n for n,s in ranking[:10]]
        hit5=real in top5; hit10=real in top10
        if hit5: aciertos_top5+=1
        if hit10: aciertos_top10+=1
        total_eval+=1; frecuencia_ganadora[real]+=1
        scores_ganadores.append(score_real); rankings_ganadores.append(rank_real or 100)
        prev=registros_loteria[:i]; ult=None
        for j in range(len(prev)-1,-1,-1):
            if prev[j]["numeros"][0]==real: ult=j; break
        atraso=i if ult is None else (i-1-ult); atraso_ganador.append(atraso)
        eventos.append({"fecha":fecha,"real_1ra":real,"score_real":round(score_real,4),"rank_real":rank_real,"hit_top5":hit5,"hit_top10":hit10,"top5":top5,"top10":top10,"atraso_real":atraso})
        score_por_fecha.append({"fecha":fecha,"score_ganador":round(score_real,4),"rank_ganador":rank_real or 100,"numero":real})
    # ── Rango ganador: SOLO fase estable (post-calentamiento) ─────────────
    # Los primeros MIN_WARMUP sorteos tienen score bajo/ruidoso porque no hay
    # suficiente historia — incluirlos contamina el rango y lo hace inexacto.
    scores_estables=scores_ganadores[MIN_WARMUP:] if len(scores_ganadores)>MIN_WARMUP else scores_ganadores
    warmup_fecha=score_por_fecha[MIN_WARMUP]["fecha"] if len(score_por_fecha)>MIN_WARMUP else (score_por_fecha[0]["fecha"] if score_por_fecha else "")
    base_rango=scores_estables if scores_estables else scores_ganadores
    if base_rango:
        sc_sorted=sorted(base_rango)
        q25=sc_sorted[int(len(sc_sorted)*0.25)]; q50=sc_sorted[int(len(sc_sorted)*0.50)]; q75=sc_sorted[int(len(sc_sorted)*0.75)]
        score_min=min(base_rango); score_max=max(base_rango); score_prom=sum(base_rango)/len(base_rango)
    else: score_min=score_max=score_prom=q25=q50=q75=0
    atraso_prom=sum(atraso_ganador)/len(atraso_ganador) if atraso_ganador else 0
    resumen={"loteria":loteria,"eventos_historicos":len(registros_loteria),"eventos_evaluados":total_eval,
        "primer_dia":registros_loteria[0]["fecha"] if registros_loteria else "","ultimo_dia":registros_loteria[-1]["fecha"] if registros_loteria else "",
        "top5_hits":aciertos_top5,"top10_hits":aciertos_top10,
        "top5_pct":round((aciertos_top5/total_eval)*100,2) if total_eval else 0,
        "top10_pct":round((aciertos_top10/total_eval)*100,2) if total_eval else 0,
        "score_ganador":{"min":round(score_min,4),"max":round(score_max,4),"promedio":round(score_prom,4),
            "q25":round(q25,4),"q50":round(q50,4),"q75":round(q75,4),
            "rango_min":round(q25*0.85,4),"rango_max":round(q75*1.20,4)},
        "warmup_n":MIN_WARMUP,"warmup_fecha":warmup_fecha,
        "atraso_ganador_promedio":round(atraso_prom,2),
        "numeros_ganadores_frecuencia":dict(frecuencia_ganadora.most_common()),
        "score_por_fecha":score_por_fecha,"eventos":eventos[-500:],
        "generado":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),"nota":"Solo lectura Biblia."}
    ruta=os.path.join(MEM_LOTERIAS,f"{safe_name(loteria)}.json")
    with open(ruta,"w",encoding="utf-8") as f: json.dump(resumen,f,ensure_ascii=False,indent=2)
    return resumen,ruta

def correr_aprendizaje_anguila():
    if aprendizaje["corriendo"]: return
    aprendizaje["corriendo"]=True; aprendizaje["estado"]="corriendo"; aprendizaje["log"]=[]
    aprendizaje["inicio"]=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_ap(f"🧠 APRENDIZAJE ANGUILLA 10AM")
    archivos,registros,errores=leer_toda_biblia()
    if errores: log_ap(f"⚠️ {len(errores)} errores Biblia")
    nombre_obj=nombre_objetivo_en_biblia(registros)
    if not nombre_obj:
        log_ap("❌ No se encontró Anguilla 10AM en la Biblia"); aprendizaje["corriendo"]=False; aprendizaje["estado"]="error"; return
    log_ap(f"✅ Nombre en Biblia: {nombre_obj}")
    por_loteria,por_fecha,fechas=preparar_indices(registros)
    regs_lot=por_loteria.get(nombre_obj,[])
    aprendizaje["loterias_total"]=1; aprendizaje["loteria_actual"]=nombre_obj; aprendizaje["loteria_index"]=1
    aprendizaje["eventos_total"]=len(regs_lot)
    log_ap(f"🎰 Aprendiendo {nombre_obj} ({len(regs_lot)} eventos)")
    try:
        resumen,ruta=analizar_loteria_total_pro(nombre_obj,regs_lot,por_fecha)
        ruta_global=os.path.join(MEMORIA,"memoria_total_pro.json")
        global_mem={}
        if os.path.exists(ruta_global):
            try:
                with open(ruta_global,"r",encoding="utf-8") as f: global_mem=json.load(f)
            except: global_mem={}
        if "loterias" not in global_mem: global_mem["loterias"]={}
        global_mem["loterias"][nombre_obj]={"eventos_evaluados":resumen["eventos_evaluados"],"top5_pct":resumen["top5_pct"],"top10_pct":resumen["top10_pct"],"rango_min":resumen["score_ganador"]["rango_min"],"rango_max":resumen["score_ganador"]["rango_max"],"ultimo_dia":resumen["ultimo_dia"],"archivo":ruta}
        global_mem["generado"]=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(ruta_global,"w",encoding="utf-8") as f: json.dump(global_mem,f,ensure_ascii=False,indent=2)
        aprendizaje["ultimo_guardado"]=ruta
        log_ap(f"✅ Top5:{resumen['top5_pct']}% Top10:{resumen['top10_pct']}%")
    except Exception as e: log_ap(f"❌ Error: {e}")
    aprendizaje["fin"]=datetime.now().strftime("%Y-%m-%d %H:%M:%S"); aprendizaje["estado"]="completado"; aprendizaje["corriendo"]=False
    log_ap("🏁 APRENDIZAJE COMPLETADO")

# ══════════════════════════════════════════════════════════
# IA V5 — MOTOR COMPLETO
# ══════════════════════════════════════════════════════════
def _percentil(valores,pct):
    if not valores: return 0.0
    vals=sorted(float(x) for x in valores)
    if len(vals)==1: return vals[0]
    k=(len(vals)-1)*pct; f=int(math.floor(k)); c=int(math.ceil(k))
    if f==c: return vals[f]
    return vals[f]+(vals[c]-vals[f])*(k-f)

def _pendiente_lineal(valores):
    if len(valores)<2: return 0.0
    n=len(valores); x_mean=(n-1)/2; y_mean=sum(valores)/n
    den=sum((i-x_mean)**2 for i in range(n)) or 1
    return sum((i-x_mean)*(valores[i]-y_mean) for i in range(n))/den

def _normalizar_forma(seq):
    if not seq: return []
    vals=[float(x) for x in seq]; prom=sum(vals)/len(vals)
    var=sum((x-prom)**2 for x in vals)/len(vals); sd=math.sqrt(var)
    if sd<1e-9: return [0.0]*len(vals)
    return [(x-prom)/sd for x in vals]

def _distancia_forma(seq_a,seq_b):
    if len(seq_a)!=len(seq_b) or not seq_a: return 999999.0
    na=_normalizar_forma(seq_a); nb=_normalizar_forma(seq_b)
    dist_forma=sum((na[i]-nb[i])**2 for i in range(len(na)))/len(na)
    prom_a=sum(seq_a)/len(seq_a); prom_b=sum(seq_b)/len(seq_b)
    dist_nivel=abs(prom_a-prom_b)/80.0
    slope_a=_pendiente_lineal(seq_a); slope_b=_pendiente_lineal(seq_b)
    dist_pendiente=abs(slope_a-slope_b)/18.0
    return (dist_forma*0.58)+(dist_nivel*0.27)+(dist_pendiente*0.15)

def _buscar_contextos_similares(valores,ventana=7,limite=18):
    if len(valores)<ventana+12: return []
    actual=[float(x) for x in valores[-ventana:]]; matches=[]
    max_i=len(valores)-ventana-1
    for i in range(0,max_i):
        seq=[float(x) for x in valores[i:i+ventana]]; siguiente=float(valores[i+ventana])
        dist=_distancia_forma(actual,seq)
        if dist<999999: matches.append({"inicio":i,"fin":i+ventana-1,"distancia":dist,"secuencia":seq,"siguiente":siguiente,"peso":1.0/(dist+0.08)})
    matches.sort(key=lambda x:x["distancia"])
    return matches[:limite]

def _resumen_contextual(valores,ventana=7):
    matches=_buscar_contextos_similares(valores,ventana=ventana,limite=18)
    if not matches: return {"ventana":ventana,"matches":0,"proyeccion":0.0,"min":0.0,"max":0.0,"confianza_bonus":0.0,"ejemplos":[]}
    siguientes=[m["siguiente"] for m in matches]; pesos=[m["peso"] for m in matches]
    total_peso=sum(pesos) or 1.0
    proy=sum(matches[i]["siguiente"]*pesos[i] for i in range(len(matches)))/total_peso
    p25=_percentil(siguientes,0.25); p75=_percentil(siguientes,0.75)
    p15=_percentil(siguientes,0.15); p85=_percentil(siguientes,0.85)
    prom=sum(siguientes)/len(siguientes); var=sum((x-prom)**2 for x in siguientes)/len(siguientes); sd=math.sqrt(var)
    ancho_contexto=max(1.0,p85-p15); confianza_bonus=max(0.0,min(18.0,18.0-(ancho_contexto/7.0)))
    margen=max(10.0,sd*0.55); rmin=max(0.0,min(p25,p15)-margen); rmax=max(p75,p85)+margen
    return {"ventana":ventana,"matches":len(matches),"proyeccion":round(proy,4),"min":round(rmin,4),"max":round(rmax,4),"confianza_bonus":round(confianza_bonus,4),"siguientes_prom":round(prom,4),"siguientes_sd":round(sd,4),"ejemplos":[{"distancia":round(m["distancia"],4),"siguiente":round(m["siguiente"],4)} for m in matches[:5]]}

def _expandir_rango_para_minimo_candidatos(candidatos,rango_min,rango_max,minimo=10,maximo=25):
    try: rmin=float(rango_min); rmax=float(rango_max)
    except: return rango_min,rango_max,[],0
    if rmin>rmax: rmin,rmax=rmax,rmin
    centro=(rmin+rmax)/2; ancho=max(8.0,rmax-rmin); pasos=0
    def filtrar(a,b):
        salida=[]
        for x in candidatos:
            try: sc=float(x.get("score",0) or 0)
            except: sc=0.0
            if a<=sc<=b:
                y=dict(x); y["distancia_centro_ia"]=round(abs(sc-((a+b)/2)),4); salida.append(y)
        salida.sort(key=lambda x:(0 if x.get("quemado") else 1,1 if x.get("dentro_brecha") else 0,-float(x.get("distancia_centro_ia",999999)),float(x.get("prioridad",0) or 0)),reverse=True)
        return salida
    filtrados=filtrar(rmin,rmax)
    while len(filtrados)<minimo and pasos<8:
        pasos+=1; ancho*=1.28; rmin=max(0.0,centro-(ancho/2)); rmax=centro+(ancho/2); filtrados=filtrar(rmin,rmax)
    return round(rmin,4),round(rmax,4),filtrados[:maximo],pasos

def casa_loteria(nombre):
    n=(nombre or "").lower().replace("á","a").replace("é","e").replace("í","i").replace("ó","o").replace("ú","u")
    if "anguilla" in n or "anguila" in n: return "ANGUILLA"
    if "haiti" in n: return "HAITI"
    if "florida" in n: return "FLORIDA"
    if "new york" in n: return "NEW YORK"
    if "new jersey" in n: return "NEW JERSEY"
    if "georgia" in n: return "GEORGIA"
    return (nombre or "SIN CASA").strip().upper()

def hora_loteria_minutos(nombre):
    n=(nombre or "").lower().replace("í","i").replace("á","a").replace("é","e").replace("ó","o").replace("ú","u")
    reglas=[("8am",480),("9am",540),("9:30",570),("10am",600),("10 am",600),("10:30",630),("11am",660),("12pm",720),("1pm",780),("2pm",840),("3pm",900),("4pm",960),("5pm",1020),("6pm",1080),("7pm",1140)]
    for token,mins in reglas:
        if token in n: return mins
    return 1440+999

def numeros_primera_historicos_desde_puntos(puntos):
    nums=set()
    for p in puntos or []:
        n=str(p.get("numero","")).zfill(2)[-2:]
        if n.isdigit(): nums.add(n)
    return nums

def eventos_casa_mismo_dia(loteria,fecha_objetivo,registros_biblia):
    casa=casa_loteria(loteria); h_obj=hora_loteria_minutos(loteria); eventos=[]
    for r in registros_biblia or []:
        lot=r.get("loteria","")
        if casa_loteria(lot)!=casa: continue
        if str(r.get("fecha",""))!=str(fecha_objetivo): continue
        if lot==loteria: continue
        if hora_loteria_minutos(lot)<=h_obj: eventos.append(r)
    eventos.sort(key=lambda x:hora_loteria_minutos(x.get("loteria","")))
    liberados={}
    for r in eventos:
        lot=r.get("loteria","")
        for pos,n in enumerate(r.get("numeros",[])[:3],start=1):
            n=str(n).zfill(2)[-2:]; liberados.setdefault(n,[]).append(f"{lot} {pos}ra")
    return liberados

def contexto_numeros_por_score(puntos,rmin,rmax,centro,tolerancia_extra=18):
    zona=Counter(); cercana=Counter(); total_zona=0; total_cercana=0
    a=max(0.0,float(rmin)-tolerancia_extra); b=float(rmax)+tolerancia_extra
    for p in puntos or []:
        try: sc=float(p.get("score",0) or 0); n=str(p.get("numero","")).zfill(2)[-2:]
        except: continue
        if not n.isdigit(): continue
        if a<=sc<=b: zona[n]+=1; total_zona+=1
        if abs(sc-centro)<=max(12.0,tolerancia_extra): cercana[n]+=1; total_cercana+=1
    return zona,cercana,total_zona,total_cercana

def intercalar_candidatos_v4(candidatos,rmin,rmax,proyeccion,maximo=35):
    if not candidatos: return []
    rmin=float(rmin); rmax=float(rmax)
    if rmin>rmax: rmin,rmax=rmax,rmin
    ancho=max(1.0,rmax-rmin); centro=float(proyeccion) if proyeccion is not None else (rmin+rmax)/2
    centro=min(max(centro,rmin),rmax); nucleo_lim=max(8.0,ancho*0.18)
    bajo=[]; nucleo=[]; alto=[]
    for x in candidatos:
        sc=float(x.get("score",0) or 0); y=dict(x); dist=abs(sc-centro); y["distancia_centro_ia"]=round(dist,4)
        if dist<=nucleo_lim: y["zona_ia"]="NUCLEO IA"; nucleo.append(y)
        elif sc<centro: y["zona_ia"]="BORDE BAJO"; bajo.append(y)
        else: y["zona_ia"]="BORDE ALTO"; alto.append(y)
    def key(y): return (float(y.get("prioridad_v4",y.get("prioridad",0)) or 0),-float(y.get("distancia_centro_ia",999999) or 999999))
    for g in [nucleo,alto,bajo]: g.sort(key=key,reverse=True)
    salida=[]; usados=set(); grupos=[nucleo,alto,nucleo,bajo]; idxs=[0,0,0,0]
    while len(salida)<maximo:
        avanzo=False
        for gi,g in enumerate(grupos):
            while idxs[gi]<len(g) and g[idxs[gi]].get("numero") in usados: idxs[gi]+=1
            if idxs[gi]<len(g):
                item=g[idxs[gi]]; idxs[gi]+=1
                if item.get("numero") not in usados:
                    salida.append(item); usados.add(item.get("numero")); avanzo=True
                    if len(salida)>=maximo: break
        if not avanzo: break
    return salida

# ══════════════════════════════════════════════════════════
# MOTOR SUCESOR — patrones de transición histórica
# ══════════════════════════════════════════════════════════
def construir_matrices_transicion(primeras):
    """
    Lee toda la secuencia histórica de 1ras y construye:
    - trans[lag][n] = Counter de sucesores a ese lag
    - trans_dec[dec_n] = Counter de decenas sucesoras (lag-1)
    """
    T=len(primeras)
    trans={1:defaultdict(Counter),2:defaultdict(Counter),
           3:defaultdict(Counter),5:defaultdict(Counter)}
    trans_dec=defaultdict(Counter)
    for i in range(T):
        n=primeras[i]
        dec=str(int(n)//10)
        for lag in [1,2,3,5]:
            if i+lag<T:
                suc=primeras[i+lag]
                trans[lag][n][suc]+=1
        if i+1<T:
            suc1=primeras[i+1]
            trans_dec[dec][str(int(suc1)//10)]+=1
    return trans,trans_dec

def predecir_sucesor(hist_lot_sorted,ventana=8):
    """
    Dado el historial ordenado, analiza los últimos `ventana` ganadores
    y predice sucesores basándose en frecuencias históricas.
    Retorna lista ordenada de candidatos con detalles de patrón.
    """
    nums=[str(i).zfill(2) for i in range(100)]
    primeras=[r["numeros"][0] for r in hist_lot_sorted if r.get("numeros")]
    T=len(primeras)
    if T<20: return []

    trans,trans_dec=construir_matrices_transicion(primeras)
    ultimos=primeras[-ventana:]
    ultimo=ultimos[-1]
    scores=Counter()

    # Pesos por lag: cuanto más reciente el "disparador", mayor peso
    pesos_lag={1:1.0, 2:0.50, 3:0.25, 5:0.10}

    for pos_back,num in enumerate(reversed(ultimos)):
        lag_aplicado=pos_back+1  # este número está a lag_aplicado sorteos del próximo
        if lag_aplicado>5: break
        peso_recencia=1.0/(2**pos_back)  # 1, 0.5, 0.25 ...

        for lag_hist,[lag_key,w_lag] in enumerate([[lag_aplicado,pesos_lag.get(lag_aplicado,0.05)]]):
            total_t=sum(trans[lag_key][num].values()) or 1
            for suc,freq in trans[lag_key][num].items():
                scores[suc]+=( freq/total_t)*w_lag*peso_recencia*100

        # Patrón de decena (solo lag-1 del número más reciente)
        if pos_back==0:
            dec=str(int(num)//10)
            total_dec=sum(trans_dec[dec].values()) or 1
            for dec_suc,freq_dec in trans_dec[dec].items():
                prob_dec=(freq_dec/total_dec)*0.40*100
                for j in range(10):
                    cand=str(int(dec_suc)*10+j).zfill(2)
                    scores[cand]+=prob_dec/10

    if not scores: return []
    max_sc=max(scores.values()) or 1

    resultado=[]
    for n in nums:
        sc=scores.get(n,0)
        if sc<=0: continue
        # Detalle lag-1 directo del último número
        total_lag1=sum(trans[1][ultimo].values()) or 1
        freq_lag1=trans[1][ultimo].get(n,0)
        pct_lag1=round(freq_lag1/total_lag1*100,1)
        # Detalle decena
        dec_ult=str(int(ultimo)//10)
        dec_cand=str(int(n)//10)
        total_dec_ult=sum(trans_dec[dec_ult].values()) or 1
        freq_dec=trans_dec[dec_ult].get(dec_cand,0)
        pct_dec=round(freq_dec/total_dec_ult*100,1)
        # Cuántos sorteos atrás fue la última vez que N siguió al patrón
        contexto_str=[]
        for lag in [1,2,3]:
            f=trans[lag][ultimo].get(n,0)
            if f: contexto_str.append(f"L{lag}:{f}x")
        resultado.append({
            "numero":n,
            "score_suc":round((sc/max_sc)*100,2),
            "score_raw":round(sc,4),
            "freq_lag1":freq_lag1,
            "pct_lag1":pct_lag1,
            "pct_dec":pct_dec,
            "decena":dec_cand,
            "patron":"+".join(contexto_str) if contexto_str else "DEC"
        })
    resultado.sort(key=lambda x:x["score_suc"],reverse=True)
    return resultado[:30]

def estadisticas_1ra_v5(loteria,registros_biblia):
    regs=[r for r in (registros_biblia or []) if r.get("loteria")==loteria]
    regs.sort(key=lambda x:x.get("fecha",""))
    nums=[str(i).zfill(2) for i in range(100)]
    stats={n:{"freq_1ra":0,"freq_2da":0,"freq_3ra":0,"rec_1ra_15":0,"rec_1ra_30":0,"rec_1ra_60":0,"rec_2da_30":0,"rec_3ra_30":0,"share_1ra":0.0,"total_pos":0,"atraso_1ra":9999,"ultima_1ra":"","score_1ra_puro":0.0,"nunca_1ra":True} for n in nums}
    for idx,r in enumerate(regs):
        ns=r.get("numeros",[]) or []
        for pos in range(3):
            if len(ns)<=pos: continue
            n=str(ns[pos]).zfill(2)[-2:]
            if not n.isdigit(): continue
            if pos==0: stats[n]["freq_1ra"]+=1; stats[n]["ultima_1ra"]=r.get("fecha",""); stats[n]["nunca_1ra"]=False
            elif pos==1: stats[n]["freq_2da"]+=1
            elif pos==2: stats[n]["freq_3ra"]+=1
    ult15=regs[-15:]; ult30=regs[-30:]; ult60=regs[-60:]
    for r in ult15:
        ns=r.get("numeros",[]) or []
        if ns:
            n=str(ns[0]).zfill(2)[-2:]
            if n.isdigit(): stats[n]["rec_1ra_15"]+=1
    for r in ult30:
        ns=r.get("numeros",[]) or []
        if len(ns)>=1:
            n=str(ns[0]).zfill(2)[-2:]
            if n.isdigit(): stats[n]["rec_1ra_30"]+=1
        if len(ns)>=2:
            n=str(ns[1]).zfill(2)[-2:]
            if n.isdigit(): stats[n]["rec_2da_30"]+=1
        if len(ns)>=3:
            n=str(ns[2]).zfill(2)[-2:]
            if n.isdigit(): stats[n]["rec_3ra_30"]+=1
    for r in ult60:
        ns=r.get("numeros",[]) or []
        if ns:
            n=str(ns[0]).zfill(2)[-2:]
            if n.isdigit(): stats[n]["rec_1ra_60"]+=1
    total_regs=len(regs)
    for n,st in stats.items():
        f1,f2,f3=st["freq_1ra"],st["freq_2da"],st["freq_3ra"]
        total=f1+f2+f3; share=(f1/total) if total else 0.0
        st["total_pos"]=total; st["share_1ra"]=round(share,4)
        if f1>0:
            last_idx=None
            for i in range(len(regs)-1,-1,-1):
                ns=regs[i].get("numeros",[]) or []
                if ns and str(ns[0]).zfill(2)[-2:]==n: last_idx=i; break
            st["atraso_1ra"]=(total_regs-1-last_idx) if last_idx is not None else 9999
        else: st["atraso_1ra"]=9999
        # f1 normalizado: (f1/total_regs)*220 → escala ~2.2 sin importar cuántos datos
        score=0.0; score+=(f1/max(total_regs,1))*220.0; score+=st["rec_1ra_15"]*22.0; score+=st["rec_1ra_30"]*12.0; score+=st["rec_1ra_60"]*5.0; score+=share*55.0
        atraso=st["atraso_1ra"]
        if 5<=atraso<=32: score+=38.0
        elif 33<=atraso<=75: score+=24.0
        elif 76<=atraso<=140: score+=10.0
        elif atraso<=2: score-=28.0
        elif atraso>220: score-=16.0
        if f1>0:
            score+=min(14.0,(f2*0.15)+(f3*0.10)); score+=min(12.0,(st["rec_2da_30"]*1.2)+(st["rec_3ra_30"]*0.8))
        if (f2+f3)>=12 and share<0.24: score-=36.0
        if f1==0: score=-9999.0
        st["score_1ra_puro"]=round(score,4)
    return stats

def cargar_memoria_loteria(loteria):
    ruta_global=os.path.join(MEMORIA,"memoria_total_pro.json")
    ruta_lot=os.path.join(MEM_LOTERIAS,f"{safe_name(loteria)}.json")
    if not os.path.exists(ruta_global): raise Exception("No existe memoria. Ejecuta el aprendizaje primero.")
    if not os.path.exists(ruta_lot): raise Exception(f"No existe memoria individual para: {loteria}")
    with open(ruta_global,"r",encoding="utf-8") as f: global_mem=json.load(f)
    with open(ruta_lot,"r",encoding="utf-8") as f: lot_mem=json.load(f)
    return global_mem,lot_mem

def ia_score_ganador_loteria(loteria):
    global_mem,lot_mem=cargar_memoria_loteria(loteria)
    puntos_raw=lot_mem.get("score_por_fecha",[]) or []
    puntos=[]; fechas_ya=set()
    for p in puntos_raw:
        try:
            fp=str(p.get("fecha",""))
            if not fp: continue
            puntos.append({"fecha":fp,"score":float(p.get("score_ganador",0) or 0),"rank":int(p.get("rank_ganador",100) or 100),"numero":str(p.get("numero","")).zfill(2)[-2:],"pendiente_memoria":False})
            fechas_ya.add(fp)
        except: pass
    puntos_agregados_biblia=0; registros_biblia_cache=[]; por_fecha_biblia_cache={}; regs_lot_biblia=[]; fecha_objetivo=""
    try:
        _,registros_biblia_cache,_=leer_toda_biblia()
        por_loteria_biblia,por_fecha_biblia_cache,fechas_biblia=preparar_indices(registros_biblia_cache)
        regs_lot_biblia=por_loteria_biblia.get(loteria,[])
        nuevos=[r for r in regs_lot_biblia if str(r.get("fecha","")) not in fechas_ya]
        nuevos.sort(key=lambda x:x.get("fecha",""))
        for rnew in nuevos:
            fecha_new=rnew.get("fecha",""); real_new=(rnew.get("numeros") or [""])[0]
            hist_prev=[r for r in regs_lot_biblia if r.get("fecha","")<fecha_new]
            if not hist_prev: continue
            scores_new=calcular_score_candidatos(hist_prev,fecha_new,por_fecha_biblia_cache)
            ranking_new=sorted(scores_new.items(),key=lambda x:x[1],reverse=True)
            score_real_new=float(scores_new.get(real_new,0) or 0); rank_real_new=100
            for pos,(num,sc) in enumerate(ranking_new,start=1):
                if num==real_new: rank_real_new=pos; break
            puntos.append({"fecha":fecha_new,"score":round(score_real_new,4),"rank":rank_real_new,"numero":str(real_new).zfill(2)[-2:],"pendiente_memoria":True})
            puntos_agregados_biblia+=1
    except: pass
    puntos.sort(key=lambda x:x.get("fecha",""))
    if len(puntos)<30: raise Exception("Memoria insuficiente (necesita 30+ puntos). Primero aprende la lotería.")
    valores=[float(p["score"]) for p in puntos]
    ultimo_score=valores[-1]
    def _prom(xs): return sum(xs)/len(xs) if xs else 0.0
    ultimos_7=valores[-7:]; ultimos_15=valores[-15:]; ultimos_30=valores[-30:]
    ultimos_60=valores[-60:] if len(valores)>=60 else valores
    ultimos_120=valores[-120:] if len(valores)>=120 else valores
    prom_7=_prom(ultimos_7); prom_15=_prom(ultimos_15); prom_30=_prom(ultimos_30); prom_60=_prom(ultimos_60)
    slope_7=_pendiente_lineal(ultimos_7); slope_15=_pendiente_lineal(ultimos_15); slope_30=_pendiente_lineal(ultimos_30)
    diffs=[abs(ultimos_30[i]-ultimos_30[i-1]) for i in range(1,len(ultimos_30))]
    media_mov=_prom(diffs) if diffs else 10.0
    vol_30=(sum((x-prom_30)**2 for x in ultimos_30)/len(ultimos_30))**0.5 if ultimos_30 else 0.0
    contexto=_resumen_contextual(valores,ventana=7)
    proyeccion_contexto=float(contexto.get("proyeccion",0) or 0)
    slope_mix=(slope_7*0.20)+(slope_15*0.35)+(slope_30*0.45)
    proyeccion_pendiente=ultimo_score+(slope_mix*2.2)
    if contexto.get("encontrados",0)>=6 or contexto.get("matches",0)>=6:
        proyeccion=(proyeccion_contexto*0.62)+(proyeccion_pendiente*0.23)+(ultimo_score*0.15)
    else:
        proyeccion=(proyeccion_pendiente*0.55)+(ultimo_score*0.30)+(prom_30*0.15)
    if slope_mix>2.8: tendencia="ASCENDENTE"
    elif slope_mix<-2.8: tendencia="DESCENDENTE"
    else: tendencia="ESTABLE"
    fuerza=abs(slope_mix); ancho_base=max(18.0,media_mov*1.35,vol_30*0.72)
    if contexto.get("matches",0)>=6:
        cmin=float(contexto.get("min",0) or 0); cmax=float(contexto.get("max",0) or 0)
        rango_min=min(cmin,proyeccion-(ancho_base*0.55),ultimo_score-(ancho_base*0.60))
        rango_max=max(cmax,proyeccion+(ancho_base*0.70),ultimo_score+(ancho_base*0.75))
    else:
        rango_min=proyeccion-(ancho_base*0.85); rango_max=proyeccion+(ancho_base*0.85)
    p05_120=_percentil(ultimos_120,0.05); p10_60=_percentil(ultimos_60,0.10)
    p90_60=_percentil(ultimos_60,0.90); p95_120=_percentil(ultimos_120,0.95)
    rango_min=max(0.0,max(rango_min,p05_120-(media_mov*0.35)))
    rango_max=min(max(rango_max,p10_60+10),p95_120+(media_mov*0.40))
    if rango_min>rango_max: rango_min,rango_max=rango_max,rango_min
    if not registros_biblia_cache: _,registros_biblia_cache,_=leer_toda_biblia()
    if not regs_lot_biblia:
        regs_lot_biblia=[r for r in registros_biblia_cache if r.get("loteria")==loteria]
        regs_lot_biblia.sort(key=lambda x:x.get("fecha",""))
    ultimo_dia=max([r.get("fecha","") for r in registros_biblia_cache if r.get("fecha")],default=puntos[-1]["fecha"])
    try: fecha_objetivo=(datetime.strptime(ultimo_dia,"%Y-%m-%d")+timedelta(days=1)).strftime("%Y-%m-%d")
    except: fecha_objetivo=ultimo_dia
    scores_actuales=calcular_score_candidatos(regs_lot_biblia,fecha_objetivo,por_fecha_biblia_cache)
    stats=estadisticas_1ra_v5(loteria,registros_biblia_cache)
    centro_ia=float(proyeccion)
    zona_freq,zona_cercana,total_zona_freq,total_zona_cercana=contexto_numeros_por_score(puntos,rango_min,rango_max,centro_ia,tolerancia_extra=max(12,media_mov*0.35))
    liberados_casa=eventos_casa_mismo_dia(loteria,ultimo_dia,registros_biblia_cache)
    rminf=float(rango_min); rmaxf=float(rango_max); expansiones=0
    nums=[str(i).zfill(2) for i in range(100)]
    def contar_en_rango(a,b): return [n for n in nums if stats.get(n,{}).get("freq_1ra",0)>0 and a<=float(scores_actuales.get(n,0) or 0)<=b]
    vivos=contar_en_rango(rminf,rmaxf)
    while len(vivos)<20 and expansiones<8:
        ancho=max(10.0,rmaxf-rminf); rminf=max(0.0,rminf-ancho*0.16); rmaxf=rmaxf+ancho*0.18; expansiones+=1; vivos=contar_en_rango(rminf,rmaxf)
    candidatos_v5=[]; excluidos_sin_historia_1ra=0
    numeros_hist_1ra=numeros_primera_historicos_desde_puntos(puntos)
    for n in nums:
        st=stats.get(n,{})
        if int(st.get("freq_1ra",0) or 0)<=0: excluidos_sin_historia_1ra+=1; continue
        if n not in numeros_hist_1ra: excluidos_sin_historia_1ra+=1; continue
        sc_total=float(scores_actuales.get(n,0) or 0)
        if not (rminf<=sc_total<=rmaxf): continue
        inv=inverso(n); dist=abs(sc_total-centro_ia)
        score_1ra=float(st.get("score_1ra_puro",0) or 0)
        freq_zona=int(zona_freq.get(n,0) or 0); freq_cercana=int(zona_cercana.get(n,0) or 0)
        freq_inv_zona=int(zona_freq.get(inv,0) or 0)
        liberado=liberados_casa.get(n,[]); liberado_inv=liberados_casa.get(inv,[])
        atraso=int(st.get("atraso_1ra",9999) or 9999); share=float(st.get("share_1ra",0) or 0)
        prioridad=0.0
        prioridad+=score_1ra*1.00; prioridad+=freq_zona*15.0; prioridad+=freq_cercana*22.0; prioridad+=freq_inv_zona*5.0
        prioridad+=max(0.0,42.0-(dist*0.42)); prioridad+=min(24.0,float(st.get("freq_1ra",0) or 0)*0.85)
        if 5<=atraso<=32: prioridad+=28.0
        elif 33<=atraso<=75: prioridad+=16.0
        elif atraso<=2: prioridad-=24.0
        if share>=0.42: prioridad+=22.0
        elif share<0.24: prioridad-=20.0
        if liberado: prioridad-=34.0
        if liberado_inv: prioridad-=10.0
        razones=[]
        if freq_zona: razones.append("GANADOR HIST EN RANGO")
        if freq_cercana: razones.append("GANADOR CERCA CENTRO")
        if share>=0.42: razones.append("FIRMA FUERTE 1RA")
        elif share>=0.30: razones.append("FIRMA MEDIA 1RA")
        else: razones.append("FIRMA BAJA 1RA")
        if 5<=atraso<=32: razones.append("ATRASO IDEAL")
        elif 33<=atraso<=75: razones.append("ATRASO BUENO")
        elif atraso<=2: razones.append("MUY RECIENTE")
        if liberado: razones.append("LIBERADO CASA")
        zona="NUCLEO IA"
        ancho_final=max(1.0,rmaxf-rminf)
        if abs(sc_total-centro_ia)<=max(8.0,ancho_final*0.18): zona="NUCLEO IA"
        elif sc_total<centro_ia: zona="BORDE BAJO"
        else: zona="BORDE ALTO"
        item={"numero":n,"score":round(sc_total,4),"prioridad":round(prioridad,4),"prioridad_v4":round(prioridad,4),"prioridad_v5":round(prioridad,4),"score_1ra_v5":round(score_1ra,4),"score_1ra_v4":round(score_1ra,4),"zona_ia":zona,"distancia_centro_ia":round(dist,4),"estado":"DENTRO RANGO IA","quemado":False,"atraso":atraso,"liberado_casa":liberado[:4],"liberado_inverso_casa":liberado_inv[:4],"freq_score_contextual":freq_zona,"freq_score_cercana":freq_cercana,"firma_1ra":{"freq_1ra":int(st.get("freq_1ra",0) or 0),"freq_2da":int(st.get("freq_2da",0) or 0),"freq_3ra":int(st.get("freq_3ra",0) or 0),"rec_1ra":int(st.get("rec_1ra_30",0) or 0),"share_1ra":round(share,4),"zona_1ra_score":freq_zona,"centro_1ra_score":freq_cercana},"razones":razones[:10],"emisores":[]}
        candidatos_v5.append(item)
    candidatos_v5.sort(key=lambda x:x.get("prioridad_v5",0),reverse=True)
    top_intercalado=intercalar_candidatos_v4(candidatos_v5,rminf,rmaxf,centro_ia,maximo=35)
    if len(top_intercalado)<min(35,len(candidatos_v5)):
        usados={x["numero"] for x in top_intercalado}
        for x in candidatos_v5:
            if x["numero"] not in usados: top_intercalado.append(x); usados.add(x["numero"])
            if len(top_intercalado)>=35: break
    estabilidad=max(0,100-min(100,vol_30/max(1,prom_30)*100)) if prom_30>0 else 40
    confianza=35+(estabilidad*0.25)+float(contexto.get("confianza_bonus",0) or 0)
    if contexto.get("matches",0)>=10: confianza+=8
    if len(puntos)>=800: confianza+=8
    confianza=round(max(5,min(95,confianza)),2)
    return {"loteria":loteria,"modo":"IA V5 ANGUILLA 10AM","ultimo_punto_memoria":puntos[-1]["fecha"],"ultimo_score_ganador":round(ultimo_score,4),"ultimo_numero_ganador":puntos[-1]["numero"],"puntos_agregados_biblia":puntos_agregados_biblia,"tendencia_ia":tendencia,"fuerza_tendencia":round(fuerza,4),"proyeccion_score":round(proyeccion,4),"proyeccion_contexto":round(proyeccion_contexto,4),"rango_ia":{"min":round(rminf,4),"max":round(rmaxf,4),"centro":round(centro_ia,4),"ancho":round(rmaxf-rminf,4),"expansiones":expansiones},"contexto_historico":contexto,"confianza":confianza,"metricas":{"puntos_memoria":len(puntos),"prom_7":round(prom_7,4),"prom_15":round(prom_15,4),"prom_30":round(prom_30,4),"prom_60":round(prom_60,4),"vol_30":round(vol_30,4),"media_mov_30":round(media_mov,4),"slope_7":round(slope_7,4),"slope_15":round(slope_15,4),"slope_30":round(slope_30,4),"p10_60":round(p10_60,4),"p90_60":round(p90_60,4),"p05_120":round(p05_120,4),"p95_120":round(p95_120,4)},"top_ia":top_intercalado,"top_ia_seguro":top_intercalado[:10],"top100_actual":sorted(candidatos_v5,key=lambda x:x.get("prioridad_v5",0),reverse=True),"candidatos_en_rango":len(top_intercalado),"excluidos_sin_historia_1ra":excluidos_sin_historia_1ra,"casa":casa_loteria(loteria),"liberados_casa":liberados_casa,"analisis_base":{"ultimo_dato":ultimo_dia,"prediccion_para":fecha_objetivo},"generado":datetime.now().strftime("%Y-%m-%d %H:%M:%S")}


# ══════════════════════════════════════════════════════════
# RUTAS FLASK
# ══════════════════════════════════════════════════════════
@app.route("/")
def index(): return render_template_string(HTML)

@app.route("/iniciar",methods=["POST"])
def iniciar():
    if progreso["corriendo"]: return jsonify({"error":"Ya hay carga corriendo"})
    if aprendizaje["corriendo"]: return jsonify({"error":"Hay aprendizaje corriendo"})
    data=request.json or {}
    anio=int(data.get("anio",2026)); mes_ini=int(data.get("mes_ini",5)); mes_fin=int(data.get("mes_fin",5))
    if mes_ini>mes_fin: return jsonify({"error":"Mes inicio > mes fin"})
    t=threading.Thread(target=correr_carga,args=(anio,mes_ini,mes_fin)); t.daemon=True; t.start()
    return jsonify({"ok":True})

@app.route("/estado")
def estado(): return jsonify(progreso)

@app.route("/aprender_anguila",methods=["POST"])
def aprender_anguila():
    if progreso["corriendo"]: return jsonify({"error":"Hay carga corriendo"})
    if aprendizaje["corriendo"]: return jsonify({"error":"Aprendizaje ya corriendo"})
    t=threading.Thread(target=correr_aprendizaje_anguila); t.daemon=True; t.start()
    return jsonify({"ok":True})

@app.route("/estado_aprendizaje")
def estado_aprendizaje(): return jsonify(aprendizaje)

@app.route("/ia_anguila",methods=["POST"])
def ia_anguila():
    if aprendizaje["corriendo"]: return jsonify({"error":"Hay aprendizaje corriendo"})
    if progreso["corriendo"]: return jsonify({"error":"Hay carga corriendo"})
    try:
        _,registros,_=leer_toda_biblia()
        nombre_obj=nombre_objetivo_en_biblia(registros)
        if not nombre_obj: return jsonify({"error":"No se encontró Anguilla 10AM en la Biblia. Carga datos primero."})
        return jsonify(ia_score_ganador_loteria(nombre_obj))
    except Exception as e: return jsonify({"error":str(e)})

@app.route("/grafica_anguila")
def grafica_anguila():
    try:
        _,registros,_=leer_toda_biblia()
        nombre_obj=nombre_objetivo_en_biblia(registros)
        if not nombre_obj: return jsonify({"error":"No hay datos de Anguilla 10AM"})
        global_mem,lot_mem=cargar_memoria_loteria(nombre_obj)
        score_info=lot_mem.get("score_ganador",{}) or {}
        puntos=list(lot_mem.get("score_por_fecha",[]) or [])
        if not puntos: return jsonify({"error":"No hay score_por_fecha"})
        regs_lot_biblia=[]; por_loteria_biblia=defaultdict(list); por_fecha_biblia=defaultdict(list)
        try:
            ultima_fecha_mem=max([str(p.get("fecha","")) for p in puntos if p.get("fecha")])
            por_loteria_biblia,por_fecha_biblia,_=preparar_indices(registros)
            regs_lot_biblia=por_loteria_biblia.get(nombre_obj,[])
            fechas_ya=set(str(p.get("fecha","")) for p in puntos)
            nuevos=[r for r in regs_lot_biblia if str(r.get("fecha",""))>ultima_fecha_mem and str(r.get("fecha","")) not in fechas_ya]
            nuevos.sort(key=lambda x:x.get("fecha",""))
            for rnew in nuevos:
                fecha_new=rnew.get("fecha",""); real_new=(rnew.get("numeros") or [""])[0]
                hist_prev=[r for r in regs_lot_biblia if r.get("fecha","")<fecha_new]
                scores_new=calcular_score_candidatos(hist_prev,fecha_new,por_fecha_biblia)
                ranking_new=sorted(scores_new.items(),key=lambda x:x[1],reverse=True)
                score_real_new=float(scores_new.get(real_new,0) or 0); rank_real_new=100
                for pos,(num,sc) in enumerate(ranking_new,start=1):
                    if num==real_new: rank_real_new=pos; break
                puntos.append({"fecha":fecha_new,"score_ganador":round(score_real_new,4),"rank_ganador":rank_real_new,"numero":real_new,"pendiente_memoria":True})
        except: pass
        # ── Agregar numero_int (0-99) a cada punto ────────────────────────────
        for p in puntos:
            try: p["numero_int"]=int(str(p.get("numero","0") or "0").zfill(2)[-2:])
            except: p["numero_int"]=0
        # ── Umbrales de score (para colorear puntos: ¿la IA lo predijo?) ──────
        score_rango_min=float(score_info.get("rango_min",0) or 0)
        score_rango_max=float(score_info.get("rango_max",100) or 100)
        # ── Zona reciente: IQR de los últimos 30 números ganadores ────────────
        num_vals=[p["numero_int"] for p in puntos]
        rec30=num_vals[-30:] if len(num_vals)>=30 else num_vals
        if rec30:
            rs=sorted(rec30)
            nq25=rs[int(len(rs)*0.25)]; nq75=rs[int(len(rs)*0.75)]
            num_zona_min=max(0,nq25-5); num_zona_max=min(99,nq75+5)
        else: num_zona_min=25; num_zona_max=75
        # ── Candidatos IA actuales (números cuyo score está en rango) ──────────
        candidatos_ia_nums=[]
        try:
            if regs_lot_biblia:
                ultimo_dia=max((r.get("fecha","") for r in regs_lot_biblia if r.get("fecha")),default="")
                fecha_obj=(datetime.strptime(ultimo_dia,"%Y-%m-%d")+timedelta(days=1)).strftime("%Y-%m-%d")
                scores_act=calcular_score_candidatos(regs_lot_biblia,fecha_obj,por_fecha_biblia)
                candidatos_ia_nums=sorted(
                    [int(n) for n,sc in scores_act.items() if score_rango_min<=sc<=score_rango_max],
                    key=lambda x:-float(scores_act.get(str(x).zfill(2),0))
                )[:20]
        except: pass
        # ── Tendencia del NÚMERO (no del score) ───────────────────────────────
        tendencia="ESTABLE"; proyeccion_num=num_vals[-1] if num_vals else 50; media_mov_num=0
        if len(num_vals)>=2:
            rm=num_vals[-18:] if len(num_vals)>=18 else num_vals
            diffs=[abs(rm[i]-rm[i-1]) for i in range(1,len(rm))]
            media_mov_num=sum(diffs)/len(diffs) if diffs else 0
        if len(num_vals)>=8:
            rec=num_vals[-8:]; xm=(len(rec)-1)/2; ym=sum(rec)/len(rec)
            den=sum((i-xm)**2 for i in range(len(rec))) or 1
            slope=sum((i-xm)*(rec[i]-ym) for i in range(len(rec)))/den
            proyeccion_num=int(max(0,min(99,rec[-1]+(slope*4))))
            if slope>2.5: tendencia="ASCENDENTE"
            elif slope<-2.5: tendencia="DESCENDENTE"
        warmup_n=int(lot_mem.get("warmup_n",MIN_WARMUP) or MIN_WARMUP)
        warmup_fecha=str(lot_mem.get("warmup_fecha","") or "")
        return jsonify({"loteria":nombre_obj,"puntos":puntos,"total":len(puntos),
            "escala_min":-3,"escala_max":102,
            "niveles":[0,10,20,30,40,50,60,70,80,90,99],
            "num_zona_min":num_zona_min,"num_zona_max":num_zona_max,
            "score_rango_min":round(score_rango_min,4),"score_rango_max":round(score_rango_max,4),
            "candidatos_ia_nums":candidatos_ia_nums,
            "tendencia":tendencia,"proyeccion_num":proyeccion_num,"media_mov_num":round(media_mov_num,2),
            "warmup_n":warmup_n,"warmup_fecha":warmup_fecha})
    except Exception as e: return jsonify({"error":str(e)})

@app.route("/sucesor_anguila")
def sucesor_anguila():
    try:
        _,registros,_=leer_toda_biblia()
        nombre_obj=nombre_objetivo_en_biblia(registros)
        if not nombre_obj: return jsonify({"error":"No hay datos de Anguilla 10AM"})
        regs=[r for r in registros if r.get("loteria")==nombre_obj]
        regs.sort(key=lambda x:x.get("fecha",""))
        if len(regs)<20: return jsonify({"error":"Insuficientes datos históricos (min 20 sorteos)"})
        primeras=[r["numeros"][0] for r in regs if r.get("numeros")]
        ultimos=primeras[-8:]
        top=predecir_sucesor(regs,ventana=8)
        # También construir tabla de decenas para mostrar en UI
        trans,trans_dec=construir_matrices_transicion(primeras)
        ultimo=primeras[-1] if primeras else "00"
        dec_ult=str(int(ultimo)//10)
        total_dec=sum(trans_dec[dec_ult].values()) or 1
        tabla_decenas=[{"decena":d,"freq":f,"pct":round(f/total_dec*100,1)}
            for d,f in sorted(trans_dec[dec_ult].items(),key=lambda x:-x[1])]
        return jsonify({"loteria":nombre_obj,"total_hist":len(regs),
            "ultimo_numero":ultimo,"ultimos_8":ultimos,"top_sucesor":top,
            "tabla_decenas":tabla_decenas,"generado":datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
    except Exception as e: return jsonify({"error":str(e)})

@app.route("/combo_anguila",methods=["POST"])
def combo_anguila():
    try:
        _,registros,_=leer_toda_biblia()
        nombre_obj=nombre_objetivo_en_biblia(registros)
        if not nombre_obj: return jsonify({"error":"No hay datos de Anguilla 10AM"})
        if aprendizaje["corriendo"]: return jsonify({"error":"Aprendizaje corriendo"})
        # ── Motor V5 ──────────────────────────────────────────────────────────
        ia_data=ia_score_ganador_loteria(nombre_obj)
        top100_v5=ia_data.get("top100_actual",[]) or []
        max_prio=max((float(x.get("prioridad_v5",0) or 0) for x in top100_v5),default=1) or 1
        v5_dict={x["numero"]:x for x in top100_v5}
        top_v5_set={x["numero"] for x in ia_data.get("top_ia",[])[:20]}
        # ── Motor Sucesor ─────────────────────────────────────────────────────
        regs=[r for r in registros if r.get("loteria")==nombre_obj]
        regs.sort(key=lambda x:x.get("fecha",""))
        top_suc=predecir_sucesor(regs,ventana=8)
        max_suc=max((float(x.get("score_suc",0) or 0) for x in top_suc),default=1) or 1
        suc_dict={x["numero"]:x for x in top_suc}
        top_suc_set={x["numero"] for x in top_suc[:20]}
        # ── Fusión ────────────────────────────────────────────────────────────
        nums=[str(i).zfill(2) for i in range(100)]
        combo=[]
        for n in nums:
            v5=v5_dict.get(n,{}); suc=suc_dict.get(n,{})
            prio=float(v5.get("prioridad_v5",0) or 0)
            sc_suc=float(suc.get("score_suc",0) or 0)
            v5_norm=(prio/max_prio)*100
            suc_norm=sc_suc  # ya 0-100
            in_both=n in top_v5_set and n in top_suc_set
            bonus=22 if in_both else 0
            combo_score=v5_norm*0.55+suc_norm*0.45+bonus
            if combo_score<=0.5: continue
            fuente="🎯COMBO" if in_both else ("V5" if n in top_v5_set else ("SUC" if n in top_suc_set else "BASE"))
            combo.append({
                "numero":n,"combo_score":round(combo_score,4),
                "score_v5":round(v5_norm,2),"score_suc":round(suc_norm,2),
                "fuente":fuente,"in_rango_v5":n in top_v5_set,"in_top_suc":n in top_suc_set,
                "zona_ia":v5.get("zona_ia",""),"atraso":v5.get("atraso",9999),
                "razones":v5.get("razones",[])[:4],
                "freq_lag1":suc.get("freq_lag1",0),"pct_lag1":suc.get("pct_lag1",0),
                "patron":suc.get("patron","")})
        combo.sort(key=lambda x:x["combo_score"],reverse=True)
        primeras=[r["numeros"][0] for r in regs if r.get("numeros")]
        return jsonify({"loteria":nombre_obj,"top_combo":combo[:30],
            "ultimo_numero":ia_data.get("ultimo_numero_ganador",""),
            "ultimos_5":primeras[-5:] if primeras else [],
            "tendencia":ia_data.get("tendencia_ia",""),"confianza":ia_data.get("confianza",0),
            "metricas":ia_data.get("metricas",{}),"rango_ia":ia_data.get("rango_ia",{}),
            "generado":datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
    except Exception as e: return jsonify({"error":str(e)})

@app.route("/heatmap_anguila")
def heatmap_anguila():
    try:
        _,registros,_=leer_toda_biblia()
        nombre_obj=nombre_objetivo_en_biblia(registros)
        if not nombre_obj: return jsonify({"error":"No hay datos de Anguilla 10AM"})
        regs=[r for r in registros if r.get("loteria")==nombre_obj]
        regs.sort(key=lambda x:x.get("fecha",""))
        total=len(regs)
        freq={str(i).zfill(2):{"total":0,"pos1":0,"pos2":0,"pos3":0,"atraso":total} for i in range(100)}
        for idx,r in enumerate(regs):
            for pos,n in enumerate((r.get("numeros") or [])[:3]):
                n=str(n).zfill(2)[-2:]
                if n.isdigit() and int(n)<=99:
                    freq[n]["total"]+=1
                    if pos==0: freq[n]["pos1"]+=1
                    elif pos==1: freq[n]["pos2"]+=1
                    elif pos==2: freq[n]["pos3"]+=1
        for n in freq:
            for i in range(len(regs)-1,-1,-1):
                nums=regs[i].get("numeros") or []
                found=False
                for nn in nums:
                    if str(nn).zfill(2)[-2:]==n: found=True; break
                if found: freq[n]["atraso"]=total-1-i; break
        max_pos1=max((freq[n]["pos1"] for n in freq),default=1) or 1
        cells=[{"numero":n,"total":freq[n]["total"],"pos1":freq[n]["pos1"],"pos2":freq[n]["pos2"],"pos3":freq[n]["pos3"],"atraso":freq[n]["atraso"],"calor":round(freq[n]["pos1"]/max_pos1,4)} for n in sorted(freq.keys())]
        return jsonify({"total_sorteos":total,"loteria":nombre_obj,"cells":cells})
    except Exception as e: return jsonify({"error":str(e)})

@app.route("/cerrar")
def cerrar():
    def apagar(): time.sleep(0.5); os.kill(os.getpid(),signal.SIGTERM)
    threading.Thread(target=apagar,daemon=True).start()
    return "Cerrado"


# ══════════════════════════════════════════════════════════
# HTML — DASHBOARD ANGUILLA 10AM
# ══════════════════════════════════════════════════════════
HTML = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<title>🎯 Anguilla 10AM — IA PRO</title>
<style>
*{box-sizing:border-box;margin:0;padding:0;}
body{background:#060b14;color:#e0ecff;font-family:Arial,sans-serif;padding:12px;-webkit-tap-highlight-color:transparent;}
h1{font-size:20px;color:#00d4ff;text-align:center;margin-bottom:4px;letter-spacing:1px;}
.subtitle{text-align:center;color:#4a7fa0;font-size:12px;margin-bottom:14px;letter-spacing:2px;}
.card{background:#0b1624;border:1px solid #1e3350;border-radius:14px;padding:14px;margin-bottom:12px;}
.card-title{color:#00d4ff;font-weight:bold;font-size:15px;margin-bottom:10px;display:flex;align-items:center;gap:6px;}
label{display:block;margin-top:8px;color:#6ab0d0;font-size:13px;font-weight:bold;}
select,input{width:100%;padding:11px;margin-top:4px;border-radius:8px;border:1px solid #1e3350;font-size:15px;background:#05090f;color:#00d4ff;}
button{width:100%;padding:13px;margin-top:8px;border-radius:9px;border:none;font-size:15px;font-weight:bold;cursor:pointer;transition:all .2s;}
.btn-main{background:linear-gradient(135deg,#0090ff,#0050cc);color:#fff;}
.btn-green{background:linear-gradient(135deg,#00c97a,#007a45);color:#fff;}
.btn-purple{background:linear-gradient(135deg,#7c3aed,#4c1d95);color:#fff;}
.btn-red{background:linear-gradient(135deg,#dc2626,#991b1b);color:#fff;}
.btn-sm{padding:9px 14px;width:auto;font-size:13px;margin-top:4px;}
.log{background:#03070e;color:#00e090;padding:10px;border-radius:8px;height:200px;overflow:auto;white-space:pre-wrap;font-family:monospace;font-size:12px;margin-top:8px;}
.badge-row{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px;}
.badge{display:inline-block;background:#0d1e32;color:#00d4ff;padding:6px 11px;border-radius:18px;font-size:12px;font-weight:bold;border:1px solid #1e3350;}
.badge.green{color:#00e090;border-color:#00804a;}
.badge.orange{color:#ffaa00;border-color:#806000;}
.badge.red{color:#ff4466;border-color:#801020;}

/* ── PREDICCIONES ── */
.pred-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;margin-top:10px;}
.pred-card{background:#04090f;border:2px solid #1e3350;border-radius:13px;padding:13px;text-align:center;cursor:pointer;transition:border-color .2s,transform .2s;position:relative;overflow:hidden;}
.pred-card:hover,.pred-card:active{transform:scale(1.03);}
.pred-card.nucleo{border-color:#00b7ff;}
.pred-card.borde-alto{border-color:#9c4fff;}
.pred-card.borde-bajo{border-color:#ffaa00;}
.pred-card.quemado{opacity:.45;}
.pred-rank{position:absolute;top:7px;left:9px;font-size:11px;color:#4a7fa0;font-weight:bold;}
.pred-rank.gold{color:#ffd700;}
.pred-rank.silver{color:#b0c4de;}
.pred-rank.bronze{color:#cd7f32;}
.pred-num{font-size:48px;font-weight:bold;line-height:1.1;color:#fff;margin:8px 0 4px;}
.pred-zona{font-size:9px;letter-spacing:1.5px;font-weight:bold;margin-bottom:6px;}
.pred-zona.nucleo{color:#00b7ff;}
.pred-zona.alto{color:#9c4fff;}
.pred-zona.bajo{color:#ffaa00;}
.pred-score{font-size:11px;color:#4a9fa0;margin-bottom:6px;}
.pred-bar-bg{height:4px;background:#0d1e32;border-radius:2px;margin:6px 0;}
.pred-bar{height:100%;border-radius:2px;transition:width .7s ease;}
.pred-bar.nucleo{background:#00b7ff;}
.pred-bar.alto{background:#9c4fff;}
.pred-bar.bajo{background:#ffaa00;}
.pred-atraso{font-size:10px;margin-top:6px;}
.atraso-ideal{color:#00e090;}
.atraso-bueno{color:#ffaa00;}
.atraso-largo{color:#ff4466;}
.pred-razones{display:flex;flex-wrap:wrap;gap:3px;justify-content:center;margin-top:7px;}
.razon{background:#0a1525;border:1px solid #1e3350;border-radius:10px;font-size:8px;padding:2px 5px;color:#6ab0d0;}
.razon.firma{color:#00e090;border-color:#00804a;}
.razon.hist{color:#9c4fff;border-color:#4c1d95;}
.pred-firma{font-size:9px;color:#4a7fa0;margin-top:5px;}

/* ── GRÁFICA ── */
.grafica-wrap{background:#03050a;border:1px solid #1e3350;border-radius:10px;overflow:hidden;position:relative;}
.grafica-toolbar{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-bottom:8px;}
.grafica-toolbar button{padding:8px 12px;width:auto;font-size:12px;margin:0;}
.btn-toggle{background:#0d1e32;color:#6ab0d0;border:1px solid #1e3350;border-radius:7px;padding:7px 11px;font-size:12px;cursor:pointer;transition:all .2s;}
.btn-toggle.active{background:#1e3350;color:#00d4ff;border-color:#00d4ff;}
.y-axis{position:absolute;left:0;top:0;width:48px;height:280px;background:#07101b;border-right:1px solid #1e3350;z-index:2;pointer-events:none;}
.chart-scroll{overflow-x:auto;overflow-y:hidden;width:100%;height:280px;padding-left:48px;}
.chart-canvas{display:block;height:280px;}
.grafica-tip{background:#0b1624;border:1px solid #1e3350;border-radius:8px;padding:10px;font-family:monospace;font-size:12px;margin-top:8px;white-space:pre-wrap;color:#b0cce0;min-height:44px;}
.grafica-info{font-size:11px;color:#2a4a60;margin-bottom:6px;}

/* ── HEATMAP ── */
.heatmap-grid{display:grid;grid-template-columns:repeat(10,1fr);gap:2px;margin-top:8px;}
.hm-cell{aspect-ratio:1;border-radius:4px;display:flex;align-items:center;justify-content:center;font-size:9px;font-weight:bold;cursor:pointer;transition:transform .1s;color:#fff;position:relative;}
.hm-cell:hover,.hm-cell:active{transform:scale(1.3);z-index:10;}
.hm-tip{background:#0b1624;border:1px solid #1e3350;border-radius:8px;padding:8px;font-size:12px;margin-top:6px;color:#b0cce0;display:none;}

/* ── MÉTRICAS ── */
.metricas-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin-top:10px;}
.metrica{background:#05090f;border:1px solid #1e3350;border-radius:10px;padding:12px;text-align:center;}
.metrica-val{font-size:26px;font-weight:bold;color:#00d4ff;line-height:1;}
.metrica-lbl{font-size:10px;color:#4a7fa0;margin-top:4px;letter-spacing:1px;}

.hidden{display:none!important;}
.err{color:#ff4466;font-size:13px;margin-top:6px;}
.success-msg{color:#00e090;font-size:13px;margin-top:6px;}
</style>
</head>
<body>
<h1>🎯 ANGUILLA 10AM</h1>
<div class="subtitle">IA SCORE GANADOR V5 · PREDICCIONES EN VIVO</div>

<!-- DATOS -->
<div class="card">
  <div class="card-title">📥 Cargar Biblia (datos históricos)</div>
  <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;">
    <div>
      <label>Año</label>
      <select id="anio"><option value="2023">2023</option><option value="2024">2024</option><option value="2025">2025</option><option value="2026" selected>2026</option></select>
    </div>
    <div>
      <label>Mes ini</label>
      <select id="mes_ini"></select>
    </div>
    <div>
      <label>Mes fin</label>
      <select id="mes_fin"></select>
    </div>
  </div>
  <button class="btn-main" onclick="iniciar()">🚀 CARGAR DATA</button>
  <div class="badge-row hidden" id="carga-badges">
    <span class="badge" id="carga-estado">Listo</span>
    <span class="badge green" id="carga-ok">OK: 0</span>
    <span class="badge red" id="carga-err">ERR: 0</span>
  </div>
  <div class="log hidden" id="carga-log">Esperando...</div>
</div>

<!-- APRENDIZAJE -->
<div class="card">
  <div class="card-title">🧠 Aprendizaje Anguilla 10AM</div>
  <p style="font-size:12px;color:#4a7fa0;margin-bottom:8px;">Lee la Biblia y aprende solo Anguilla 10AM. No modifica datos.</p>
  <button class="btn-purple" onclick="aprender()">🧠 APRENDER ANGUILLA 10AM</button>
  <div class="badge-row hidden" id="ap-badges">
    <span class="badge" id="ap-estado">Listo</span>
    <span class="badge" id="ap-eventos">0 eventos</span>
  </div>
  <div class="log hidden" id="ap-log">Esperando aprendizaje...</div>
</div>

<!-- BOTONES ACCIÓN -->
<button onclick="analizarCombo()" style="width:100%;background:linear-gradient(135deg,#f59e0b,#d97706,#b45309);color:#fff;border:none;border-radius:10px;font-size:17px;font-weight:900;padding:17px;cursor:pointer;letter-spacing:.5px;margin-bottom:8px;box-shadow:0 0 18px #f59e0b44;">🎯 COMBO IA + SUCESOR</button>
<div style="display:flex;gap:8px;margin-bottom:12px;">
  <button class="btn-green" onclick="analizar()" style="flex:1;border-radius:9px;border:none;font-size:13px;font-weight:bold;padding:12px;">⚡ Solo V5</button>
  <button style="flex:1;background:linear-gradient(135deg,#7c3aed,#4f46e5);color:#fff;border:none;border-radius:9px;font-size:13px;font-weight:bold;padding:12px;cursor:pointer;" onclick="analizarSucesor()">🔄 Solo Sucesor</button>
</div>
<div id="msg-analizar" class="err hidden"></div>

<!-- MÉTRICAS -->
<div class="card hidden" id="card-metricas">
  <div class="card-title">📊 Estado Actual</div>
  <div class="metricas-grid">
    <div class="metrica"><div class="metrica-val" id="met-puntos">—</div><div class="metrica-lbl">PUNTOS MEMORIA</div></div>
    <div class="metrica"><div class="metrica-val" id="met-confianza" style="color:#00e090;">—</div><div class="metrica-lbl">CONFIANZA IA %</div></div>
    <div class="metrica"><div class="metrica-val" id="met-tendencia">—</div><div class="metrica-lbl">TENDENCIA</div></div>
    <div class="metrica"><div class="metrica-val" id="met-score" style="color:#ffaa00;">—</div><div class="metrica-lbl">ÚLTIMO SCORE</div></div>
  </div>
  <div class="badge-row" id="met-badges"></div>
</div>

<!-- GRÁFICA -->
<div class="card hidden" id="card-grafica">
  <div class="card-title">📈 Gráfica Histórica</div>
  <div class="grafica-toolbar">
    <button class="btn-toggle active" id="tog-ma7"  onclick="toggleMA('ma7')">MA7</button>
    <button class="btn-toggle active" id="tog-ma15" onclick="toggleMA('ma15')">MA15</button>
    <button class="btn-toggle active" id="tog-ma30" onclick="toggleMA('ma30')">MA30</button>
    <button class="btn-toggle active" id="tog-nums" onclick="toggleMA('nums')">Nums</button>
    <button class="btn-sm btn-main" onclick="cambiarEsp(-2)">−</button>
    <button class="btn-sm btn-main" onclick="cambiarEsp(2)">+</button>
  </div>
  <div class="grafica-info" id="grafica-info">—</div>
  <div class="grafica-wrap" id="grafica-wrap" style="position:relative;">
    <div class="y-axis" id="y-axis"></div>
    <div class="chart-scroll" id="chart-scroll">
      <canvas id="chart-canvas" class="chart-canvas"></canvas>
    </div>
  </div>
  <div class="grafica-tip" id="grafica-tip">Toca un punto para ver detalle.</div>
</div>

<!-- PREDICCIONES -->
<div class="card hidden" id="card-pred">
  <div class="card-title">🏆 Top Predicciones IA</div>
  <div style="font-size:11px;color:#4a7fa0;margin-bottom:6px;" id="pred-meta">—</div>
  <div id="pred-grid" class="pred-grid"></div>
</div>

<!-- COMBO -->
<div class="card hidden" id="card-combo">
  <div class="card-title" style="color:#f59e0b;">🎯 COMBO IA + SUCESOR</div>
  <div style="font-size:11px;color:#4a7fa0;margin-bottom:6px;" id="combo-meta">—</div>
  <div style="display:flex;gap:6px;margin-bottom:8px;flex-wrap:wrap;" id="combo-badges"></div>
  <div id="combo-grid" class="pred-grid"></div>
</div>

<!-- SUCESOR PATRÓN -->
<div class="card hidden" id="card-sucesor">
  <div class="card-title">🔄 Patrón Sucesor — Histórico Completo</div>
  <div style="font-size:11px;color:#4a7fa0;margin-bottom:6px;" id="suc-meta">—</div>
  <div style="margin-bottom:10px;">
    <div style="font-size:11px;color:#6a8fa0;margin-bottom:4px;">CADENA RECIENTE (8 sorteos):</div>
    <div id="suc-cadena" style="display:flex;gap:4px;flex-wrap:wrap;"></div>
  </div>
  <div style="margin-bottom:10px;">
    <div style="font-size:11px;color:#6a8fa0;margin-bottom:4px;">DECENAS QUE SIGUIERON AL ÚLTIMO:</div>
    <div id="suc-decenas" style="display:flex;gap:4px;flex-wrap:wrap;"></div>
  </div>
  <div style="font-size:11px;color:#6a8fa0;margin-bottom:6px;">TOP PROBABLES SEGÚN PATRONES HISTÓRICOS:</div>
  <div id="suc-grid" style="display:grid;grid-template-columns:repeat(4,1fr);gap:6px;"></div>
</div>

<!-- HEATMAP -->
<div class="card hidden" id="card-heatmap">
  <div class="card-title">🗺️ Mapa de Calor 1RA (00–99)</div>
  <div style="font-size:11px;color:#4a7fa0;margin-bottom:4px;">Color = frecuencia en 1ra posición. Toca para ver detalle.</div>
  <div id="heatmap-grid" class="heatmap-grid"></div>
  <div class="hm-tip" id="hm-tip"></div>
</div>

<!-- CONTROL -->
<div class="card">
  <div class="card-title">⚙️ Control</div>
  <button class="btn-red" onclick="cerrar()">🛑 CERRAR SERVIDOR</button>
</div>

<script>
// ═══════════════════════════════════════════
// ESTADO
// ═══════════════════════════════════════════
let graficaData=null, espacioPuntos=7, animFrame=null, animProg=0;
let mostrarMAs={ma7:true,ma15:true,ma30:true,nums:true};
let pollCarga=null, pollAp=null;

// ═══════════════════════════════════════════
// MESES
// ═══════════════════════════════════════════
(function(){
  const meses=[["1","Enero"],["2","Febrero"],["3","Marzo"],["4","Abril"],["5","Mayo"],["6","Junio"],["7","Julio"],["8","Agosto"],["9","Septiembre"],["10","Octubre"],["11","Noviembre"],["12","Diciembre"]];
  let a="";
  meses.forEach(m=>{ let sel=m[0]=="5"?"selected":""; a+=`<option value="${m[0]}" ${sel}>${m[1]}</option>`; });
  document.getElementById("mes_ini").innerHTML=a;
  document.getElementById("mes_fin").innerHTML=a;
})();

// ═══════════════════════════════════════════
// CARGA
// ═══════════════════════════════════════════
function iniciar(){
  document.getElementById("carga-badges").classList.remove("hidden");
  document.getElementById("carga-log").classList.remove("hidden");
  fetch("/iniciar",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({
    anio:parseInt(document.getElementById("anio").value),
    mes_ini:parseInt(document.getElementById("mes_ini").value),
    mes_fin:parseInt(document.getElementById("mes_fin").value)
  })}).then(r=>r.json()).then(d=>{
    if(d.error){alert(d.error);return;}
    if(pollCarga) clearInterval(pollCarga);
    pollCarga=setInterval(pollearCarga,1500); pollearCarga();
  });
}

function pollearCarga(){
  fetch("/estado").then(r=>r.json()).then(d=>{
    document.getElementById("carga-estado").innerText=d.corriendo?"⏳ DESCARGANDO":"✅ LISTO";
    document.getElementById("carga-ok").innerText="OK: "+d.ok;
    document.getElementById("carga-err").innerText="ERR: "+d.err;
    document.getElementById("carga-log").innerText=d.log.join("\n");
    document.getElementById("carga-log").scrollTop=9999;
    if(!d.corriendo&&pollCarga){clearInterval(pollCarga);pollCarga=null;}
  });
}

// ═══════════════════════════════════════════
// APRENDIZAJE
// ═══════════════════════════════════════════
function aprender(){
  if(!confirm("¿Aprender Anguilla 10AM? Esto puede tardar varios minutos.")) return;
  document.getElementById("ap-badges").classList.remove("hidden");
  document.getElementById("ap-log").classList.remove("hidden");
  fetch("/aprender_anguila",{method:"POST"}).then(r=>r.json()).then(d=>{
    if(d.error){alert(d.error);return;}
    if(pollAp) clearInterval(pollAp);
    pollAp=setInterval(pollearAp,1500); pollearAp();
  });
}

function pollearAp(){
  fetch("/estado_aprendizaje").then(r=>r.json()).then(d=>{
    document.getElementById("ap-estado").innerText=d.corriendo?"🧠 APRENDIENDO":d.estado.toUpperCase();
    document.getElementById("ap-eventos").innerText=d.eventos_total+" eventos";
    document.getElementById("ap-log").innerText=d.log.join("\n");
    document.getElementById("ap-log").scrollTop=9999;
    if(!d.corriendo&&pollAp){clearInterval(pollAp);pollAp=null;}
  });
}

// ═══════════════════════════════════════════
// ANALIZAR — CARGA GRÁFICA + PREDICCIONES + HEATMAP
// ═══════════════════════════════════════════
async function analizar(){
  const msg=document.getElementById("msg-analizar");
  msg.classList.add("hidden");
  msg.className="success-msg";
  msg.textContent="⏳ Analizando..."; msg.classList.remove("hidden");

  try {
    // 1. IA Score
    const r=await fetch("/ia_anguila",{method:"POST",headers:{"Content-Type":"application/json"}});
    const d=await r.json();
    if(d.error){msg.className="err"; msg.textContent="❌ "+d.error; return;}

    pintarMetricas(d);
    pintarPredicciones(d);
    msg.textContent="✅ Análisis completado · "+d.generado;

    // 2. Gráfica
    const rg=await fetch("/grafica_anguila");
    const dg=await rg.json();
    if(!dg.error){graficaData=dg; document.getElementById("card-grafica").classList.remove("hidden"); animarGrafica();}

    // 3. Heatmap
    const rh=await fetch("/heatmap_anguila");
    const dh=await rh.json();
    if(!dh.error){pintarHeatmap(dh);}

  } catch(e){msg.className="err"; msg.textContent="❌ "+e;}
}

// ═══════════════════════════════════════════
// COMBO IA + SUCESOR
// ═══════════════════════════════════════════
async function analizarCombo(){
  const msg=document.getElementById("msg-analizar");
  msg.className="success-msg"; msg.textContent="⏳ Fusionando V5 + Sucesor..."; msg.classList.remove("hidden");
  try{
    const r=await fetch("/combo_anguila",{method:"POST",headers:{"Content-Type":"application/json"}});
    const d=await r.json();
    if(d.error){msg.className="err"; msg.textContent="❌ "+d.error; return;}
    pintarCombo(d);
    // También mostrar gráfica si no está visible
    const rg=await fetch("/grafica_anguila");
    const dg=await rg.json();
    if(!dg.error){graficaData=dg; document.getElementById("card-grafica").classList.remove("hidden"); animarGrafica();}
    msg.textContent="✅ COMBO listo · "+d.generado;
  }catch(e){msg.className="err"; msg.textContent="❌ "+e;}
}

function pintarCombo(d){
  const card=document.getElementById("card-combo");
  card.classList.remove("hidden");
  const m=d.metricas||{};
  document.getElementById("combo-meta").textContent=
    `${m.puntos_memoria||"?"} memoria · Confianza: ${d.confianza||"?"}% · Último: ${d.ultimo_numero||"?"} · tend:${d.tendencia||""}`;
  // Badges últimos 5
  const bRow=document.getElementById("combo-badges");
  bRow.innerHTML="";
  (d.ultimos_5||[]).forEach((n,i)=>{
    const sp=document.createElement("span");
    sp.className="badge";
    sp.style.cssText=i===d.ultimos_5.length-1?"background:#f59e0b22;border-color:#f59e0b;color:#f59e0b;":"";
    sp.textContent=n;
    bRow.appendChild(sp);
  });
  const grid=document.getElementById("combo-grid");
  grid.innerHTML="";
  (d.top_combo||[]).slice(0,20).forEach((c,i)=>{
    const isCombo=c.fuente==="🎯COMBO";
    const rankColor=i===0?"#ffd700":i<3?"#f59e0b":isCombo?"#00d4ff":i<10?"#00e090":"#4a7fa0";
    const borderStyle=isCombo?"2px solid #f59e0b":"1.5px solid "+rankColor+"55";
    const el=document.createElement("div");
    el.style.cssText=`background:#060b14;border:${borderStyle};border-radius:10px;padding:10px 6px;text-align:center;position:relative;${isCombo?"box-shadow:0 0 10px #f59e0b44;":""}`;
    const barV=Math.round(c.score_v5);
    const barS=Math.round(c.score_suc);
    // Doble barra de progreso V5 vs SUC
    el.innerHTML=`
      ${isCombo?'<div style="position:absolute;top:-1px;left:0;right:0;height:2px;background:linear-gradient(90deg,#f59e0b,#fbbf24);border-radius:10px 10px 0 0;"></div>':''}
      <div style="font-size:9px;color:${rankColor};margin-bottom:1px;">#${i+1} ${c.fuente}</div>
      <div style="font-size:28px;font-weight:bold;color:#e8f4ff;font-family:monospace;line-height:1.1;">${c.numero}</div>
      <div style="font-size:9px;color:#f59e0b;margin:2px 0;">${c.combo_score.toFixed(1)}pts</div>
      <div style="display:flex;gap:2px;margin:3px 0;height:4px;border-radius:3px;overflow:hidden;">
        <div style="flex:${barV};background:#00d4ff;opacity:.8;"></div>
        <div style="flex:${barS};background:#f59e0b;opacity:.8;"></div>
      </div>
      <div style="display:flex;justify-content:center;gap:4px;font-size:8px;color:#4a7fa0;">
        <span style="color:#00d4ff;">V5:${c.score_v5.toFixed(0)}</span>
        <span style="color:#f59e0b;">SUC:${c.score_suc.toFixed(0)}</span>
      </div>
      ${c.pct_lag1>0?`<div style="font-size:8px;color:#2a4a60;margin-top:2px;">L1:${c.pct_lag1}%</div>`:""}
    `;
    grid.appendChild(el);
  });
  card.scrollIntoView({behavior:"smooth",block:"start"});
}

// ═══════════════════════════════════════════
// PATRÓN SUCESOR
// ═══════════════════════════════════════════
async function analizarSucesor(){
  const msg=document.getElementById("msg-analizar");
  msg.className="success-msg"; msg.textContent="⏳ Buscando patrones sucesores..."; msg.classList.remove("hidden");
  try{
    const r=await fetch("/sucesor_anguila");
    const d=await r.json();
    if(d.error){msg.className="err"; msg.textContent="❌ "+d.error; return;}
    pintarSucesor(d);
    msg.textContent="✅ Patrón sucesor listo · "+d.generado;
  }catch(e){msg.className="err"; msg.textContent="❌ "+e;}
}

function pintarSucesor(d){
  const card=document.getElementById("card-sucesor");
  card.classList.remove("hidden");
  document.getElementById("suc-meta").textContent=
    `${d.total_hist} sorteos históricos · Último ganador: ${d.ultimo_numero} · ${d.generado}`;

  // Cadena de últimos 8
  const cadena=document.getElementById("suc-cadena");
  cadena.innerHTML="";
  (d.ultimos_8||[]).forEach((n,i)=>{
    const isLast=i===d.ultimos_8.length-1;
    const el=document.createElement("div");
    el.style.cssText=`background:${isLast?"#00d4ff22":"#1e3350"};border:1px solid ${isLast?"#00d4ff":"#2a4a70"};border-radius:6px;padding:6px 10px;font-family:monospace;font-size:15px;font-weight:bold;color:${isLast?"#00d4ff":"#b0cce0"};`;
    el.textContent=n;
    cadena.appendChild(el);
    if(!isLast){const arr=document.createElement("span");arr.textContent="→";arr.style.cssText="color:#2a4a70;line-height:30px;font-size:14px;";cadena.appendChild(arr);}
  });
  // Flecha final
  const fq=document.createElement("span");fq.textContent="→ ?";fq.style.cssText="color:#00d4ff;line-height:30px;font-size:15px;font-weight:bold;";cadena.appendChild(fq);

  // Tabla de decenas
  const decDiv=document.getElementById("suc-decenas");
  decDiv.innerHTML="";
  (d.tabla_decenas||[]).slice(0,10).forEach(td=>{
    const el=document.createElement("div");
    const dec=Number(td.decena)*10;
    el.style.cssText=`background:#0b1624;border:1px solid #1e3350;border-radius:6px;padding:5px 8px;text-align:center;min-width:52px;`;
    el.innerHTML=`<div style="font-size:13px;font-weight:bold;color:#00d4ff;font-family:monospace;">${String(dec).padStart(2,"0")}s</div><div style="font-size:10px;color:#ffaa00;">${td.pct}%</div><div style="font-size:9px;color:#4a7fa0;">${td.freq}x</div>`;
    decDiv.appendChild(el);
  });

  // Grid de candidatos
  const grid=document.getElementById("suc-grid");
  grid.innerHTML="";
  (d.top_sucesor||[]).slice(0,20).forEach((c,i)=>{
    const el=document.createElement("div");
    const rankColor=i<3?"#ffd700":i<7?"#00d4ff":i<12?"#00e090":"#4a7fa0";
    el.style.cssText=`background:#060b14;border:1.5px solid ${rankColor}44;border-radius:9px;padding:10px 6px;text-align:center;position:relative;`;
    const barW=Math.max(4,c.score_suc);
    el.innerHTML=`
      <div style="position:absolute;top:0;left:0;width:${barW}%;height:3px;background:${rankColor};border-radius:9px 9px 0 0;opacity:.7;"></div>
      <div style="font-size:9px;color:${rankColor};margin-bottom:2px;">#${i+1}</div>
      <div style="font-size:26px;font-weight:bold;color:#e8f4ff;font-family:monospace;line-height:1.1;">${c.numero}</div>
      <div style="font-size:9px;color:#ffaa00;margin-top:2px;">${c.score_suc}pts</div>
      <div style="font-size:9px;color:#4a7fa0;margin-top:2px;">L1:${c.pct_lag1}% DEC:${c.pct_dec}%</div>
      <div style="font-size:8px;color:#2a4a60;margin-top:1px;">${c.patron||""}</div>`;
    grid.appendChild(el);
  });
  grid.scrollIntoView({behavior:"smooth",block:"start"});
}

// ═══════════════════════════════════════════
// MÉTRICAS
// ═══════════════════════════════════════════
function pintarMetricas(d){
  const m=d.metricas||{};
  document.getElementById("met-puntos").textContent=m.puntos_memoria||"—";
  document.getElementById("met-confianza").textContent=(d.confianza||"—")+"%";
  const tend=d.tendencia_ia||"ESTABLE";
  const tendEl=document.getElementById("met-tendencia");
  tendEl.textContent=tend==="ASCENDENTE"?"↑":tend==="DESCENDENTE"?"↓":"→";
  tendEl.style.color=tend==="ASCENDENTE"?"#00e090":tend==="DESCENDENTE"?"#ff4466":"#ffaa00";
  document.getElementById("met-score").textContent=d.ultimo_score_ganador||"—";
  const bRow=document.getElementById("met-badges");
  bRow.innerHTML=`
    <span class="badge">📅 ${d.ultimo_punto_memoria||""}</span>
    <span class="badge">#${d.ultimo_numero_ganador||""} último</span>
    <span class="badge orange">Score→ ${d.proyeccion_score||""}</span>
    <span class="badge">${d.candidatos_en_rango||0} candidatos</span>
    <span class="badge">${d.contexto_historico?.matches||0} contextos</span>
  `;
  document.getElementById("card-metricas").classList.remove("hidden");
}

// ═══════════════════════════════════════════
// PREDICCIONES
// ═══════════════════════════════════════════
function pintarPredicciones(d){
  const top=d.top_ia||[];
  const maxPr=Math.max(...top.map(x=>x.prioridad||0),1);
  const grid=document.getElementById("pred-grid");
  grid.innerHTML="";
  top.slice(0,20).forEach((x,i)=>{
    const zona=x.zona_ia||"NUCLEO IA";
    const cls=zona.includes("BAJO")?"borde-bajo":zona.includes("ALTO")?"borde-alto":"nucleo";
    const rankCls=i===0?"gold":i===1?"silver":i===2?"bronze":"";
    const rankLabel=i===0?"🥇":i===1?"🥈":i===2?"🥉":`#${i+1}`;
    const atraso=x.atraso||9999;
    const atrCls=atraso<=32?"atraso-ideal":atraso<=75?"atraso-bueno":"atraso-largo";
    const atrLabel=atraso<=32?"✅ ATRASO IDEAL":atraso<=75?"⚡ ATRASO BUENO":"⚠️ ATRASO "+atraso;
    const barPct=Math.min(100,Math.round((x.prioridad||0)/maxPr*100));
    const firma=x.firma_1ra||{};
    const razones=(x.razones||[]).map(r=>{
      const rc=r.includes("GANADOR")?"hist":r.includes("FIRMA")?"firma":"";
      return `<span class="razon ${rc}">${r}</span>`;
    }).join("");
    const card=document.createElement("div");
    card.className=`pred-card ${cls}${x.quemado?" quemado":""}`;
    card.innerHTML=`
      <div class="pred-rank ${rankCls}">${rankLabel}</div>
      <div class="pred-num">${x.numero}</div>
      <div class="pred-zona ${cls.replace("borde-","")}">${zona}</div>
      <div class="pred-score">Score: ${x.score}</div>
      <div class="pred-bar-bg"><div class="pred-bar ${cls}" style="width:${barPct}%"></div></div>
      <div class="pred-atraso ${atrCls}">${atrLabel}</div>
      <div class="pred-firma">1ra: ${firma.freq_1ra||0}× · share: ${Math.round((firma.share_1ra||0)*100)}%</div>
      <div class="pred-razones">${razones}</div>
    `;
    grid.appendChild(card);
  });
  document.getElementById("pred-meta").textContent=
    `${top.length} candidatos · Rango IA: ${d.rango_ia?.min||""} – ${d.rango_ia?.max||""} · ${d.generado||""}`;
  document.getElementById("card-pred").classList.remove("hidden");
}

// ═══════════════════════════════════════════
// GRÁFICA DINÁMICA CON MAs
// ═══════════════════════════════════════════
function toggleMA(key){
  mostrarMAs[key]=!mostrarMAs[key];
  const el=document.getElementById("tog-"+key);
  if(el) el.classList.toggle("active",mostrarMAs[key]);
  if(graficaData) dibujarGrafica(1.0);
}

function cambiarEsp(d){ espacioPuntos=Math.max(3,Math.min(30,espacioPuntos+d)); if(graficaData) dibujarGrafica(1.0); }

function animarGrafica(){
  if(animFrame) cancelAnimationFrame(animFrame);
  animProg=0;
  function frame(){
    animProg=Math.min(1,animProg+0.03);
    dibujarGrafica(animProg);
    if(animProg<1) animFrame=requestAnimationFrame(frame);
  }
  animFrame=requestAnimationFrame(frame);
}

function calcMA(valores,ventana){
  return valores.map((_,i)=>{
    if(i<ventana-1) return null;
    const sl=valores.slice(i-ventana+1,i+1);
    return sl.reduce((a,b)=>a+b,0)/ventana;
  });
}

function numColor(score,srmin,srmax,warmup){
  // Verde = IA lo predijo (score en rango), Amarillo = frío, Rojo = quemado
  if(warmup) return "rgba(130,130,160,.55)";
  if(score>=srmin&&score<=srmax) return "rgba(0,210,120,1)";
  if(score<srmin) return "rgba(255,190,30,1)";
  return "rgba(255,60,60,1)";
}

function dibujarGrafica(prog){
  if(!graficaData) return;
  prog=prog==null?1.0:prog;
  const puntos=graficaData.puntos||[];
  const canvas=document.getElementById("chart-canvas");
  const yAxis=document.getElementById("y-axis");
  const scroll=document.getElementById("chart-scroll");
  const ctx=canvas.getContext("2d");
  const h=300, padTop=18, padBottom=28, padRight=54, usableH=h-padTop-padBottom;

  // Escala FIJA 0-99 (espacio de números)
  const minY=-3, maxY=102, rango=maxY-minY;
  const espacioFuturo=Math.max(140,espacioPuntos*16);
  const w=Math.max(scroll.clientWidth-48,80+puntos.length*espacioPuntos+espacioFuturo);
  canvas.width=w; canvas.height=h; canvas.style.width=w+"px"; canvas.style.height=h+"px";

  function yp(n){ return padTop+((maxY-n)/rango)*usableH; }
  function xp(i){ return 10+i*espacioPuntos; }

  ctx.clearRect(0,0,w,h);

  const warmupN=Number(graficaData.warmup_n||50);
  const warmupX=puntos.length>warmupN?xp(warmupN):-1;
  const fondoX=Math.max(0,warmupX);

  // ── Zona calentamiento (gris) ─────────────────────────────────────────────
  if(warmupX>0){
    ctx.fillStyle="rgba(70,70,90,.20)";
    ctx.fillRect(0,padTop,warmupX,usableH);
  }

  // ── Zona reciente de números (IQR últimos 30 — banda verde tenue) ─────────
  const nzMin=Number(graficaData.num_zona_min??25);
  const nzMax=Number(graficaData.num_zona_max??75);
  ctx.fillStyle="rgba(0,200,120,.09)";
  ctx.fillRect(fondoX,yp(nzMax),w-fondoX-padRight,Math.max(2,yp(nzMin)-yp(nzMax)));

  // ── Cuadrícula horizontal cada 10 números ─────────────────────────────────
  ctx.strokeStyle="rgba(200,230,255,.13)"; ctx.lineWidth=1; ctx.setLineDash([4,6]);
  (graficaData.niveles||[]).forEach(n=>{
    const yy=yp(n); ctx.beginPath(); ctx.moveTo(0,yy); ctx.lineTo(w-padRight,yy); ctx.stroke();
  });
  ctx.setLineDash([]);

  // ── Líneas de zona IQR reciente ───────────────────────────────────────────
  [nzMin,nzMax].forEach(n=>{
    const yy=yp(n); ctx.strokeStyle="rgba(0,200,120,.40)"; ctx.lineWidth=1;
    ctx.setLineDash([5,5]); ctx.beginPath(); ctx.moveTo(fondoX,yy); ctx.lineTo(w-padRight,yy); ctx.stroke(); ctx.setLineDash([]);
  });

  // ── Separador calentamiento ───────────────────────────────────────────────
  if(warmupX>0){
    ctx.strokeStyle="rgba(200,200,80,.55)"; ctx.lineWidth=1.5; ctx.setLineDash([4,4]);
    ctx.beginPath(); ctx.moveTo(warmupX,padTop); ctx.lineTo(warmupX,h-padBottom); ctx.stroke(); ctx.setLineDash([]);
    ctx.font="bold 9px monospace"; ctx.textAlign="left";
    ctx.fillStyle="rgba(5,7,10,.75)"; ctx.fillRect(warmupX+2,padTop+1,88,14);
    ctx.fillStyle="rgba(200,200,80,.90)"; ctx.fillText("◀ CALENTAM.",warmupX+4,padTop+12);
  }

  const drawCount=Math.max(1,Math.round(prog*puntos.length));
  // valores = número ganador (0-99) para MAs
  const valores=puntos.map(p=>Number(p.numero_int??parseInt(p.numero||"0")));

  // ── Curva conectora de números ────────────────────────────────────────────
  ctx.save(); ctx.beginPath(); ctx.rect(0,0,xp(drawCount-1)+espacioPuntos,h); ctx.clip();

  // Tramo calentamiento (gris tenue)
  if(warmupN>1&&drawCount>1){
    ctx.strokeStyle="rgba(120,120,160,.35)"; ctx.lineWidth=1.5; ctx.beginPath();
    puntos.slice(0,Math.min(warmupN+1,drawCount)).forEach((p,i)=>{
      const xx=xp(i), yy=yp(valores[i]);
      i===0?ctx.moveTo(xx,yy):ctx.lineTo(xx,yy);
    });
    ctx.stroke();
  }
  // Tramo estable (azul)
  if(drawCount>warmupN){
    ctx.strokeStyle="rgba(0,180,255,.70)"; ctx.lineWidth=2; ctx.beginPath();
    for(let i=warmupN;i<drawCount;i++){
      const xx=xp(i), yy=yp(valores[i]);
      i===warmupN?ctx.moveTo(xx,yy):ctx.lineTo(xx,yy);
    }
    ctx.stroke();
  }

  // ── Moving Averages del NÚMERO ────────────────────────────────────────────
  function drawMA(ventana,color,dash){
    if(valores.length<ventana) return;
    const ma=calcMA(valores,ventana);
    ctx.strokeStyle=color; ctx.lineWidth=2; ctx.setLineDash(dash||[]);
    ctx.beginPath(); let started=false;
    ma.slice(0,drawCount).forEach((v,i)=>{
      if(v==null) return;
      const xx=xp(i), yy=yp(v);
      if(!started){ctx.moveTo(xx,yy);started=true;}else{ctx.lineTo(xx,yy);}
    });
    ctx.stroke(); ctx.setLineDash([]);
  }
  if(mostrarMAs.ma7)  drawMA(7,"rgba(255,200,0,.85)",[4,4]);
  if(mostrarMAs.ma15) drawMA(15,"rgba(160,110,255,.80)",[6,4]);
  if(mostrarMAs.ma30) drawMA(30,"rgba(0,230,140,.70)",[9,5]);

  // ── Etiquetas de número sobre cada punto ──────────────────────────────────
  if(mostrarMAs.nums&&drawCount>0){
    ctx.font="bold 9px Arial"; ctx.textAlign="center";
    const srmin=Number(graficaData.score_rango_min||0);
    const srmax=Number(graficaData.score_rango_max||100);
    puntos.slice(0,drawCount).forEach((p,i)=>{
      if(i<warmupN) return; // no labels en calentamiento
      if(i%2!==0&&drawCount>40) return;
      const nv=valores[i], xx=xp(i), yy=yp(nv);
      const textY=nv>50?yy+13:yy-5;
      ctx.fillStyle=numColor(Number(p.score_ganador||0),srmin,srmax,false);
      ctx.fillText(p.numero||"",xx,textY);
    });
  }

  ctx.restore();

  // ── Puntos coloreados ─────────────────────────────────────────────────────
  const srmin=Number(graficaData.score_rango_min||0);
  const srmax=Number(graficaData.score_rango_max||100);
  puntos.slice(0,drawCount).forEach((p,i)=>{
    const nv=valores[i], xx=xp(i), yy=yp(nv);
    const isWarmup=i<warmupN;
    const sc=Number(p.score_ganador||0);
    const color=p.pendiente_memoria?"rgba(255,255,255,1)":numColor(sc,srmin,srmax,isWarmup);
    ctx.fillStyle=color; ctx.beginPath();
    const r=i===puntos.length-1?7:(isWarmup?2:3.5);
    ctx.arc(xx,yy,r,0,Math.PI*2); ctx.fill();
    if(i===puntos.length-1){
      ctx.strokeStyle="rgba(255,255,255,.9)"; ctx.lineWidth=2;
      ctx.beginPath(); ctx.arc(xx,yy,r+3,0,Math.PI*2); ctx.stroke();
    }
  });

  // ── HOY + flecha proyección NÚMERO ───────────────────────────────────────
  if(drawCount>=puntos.length&&puntos.length>0){
    const hx=xp(puntos.length-1);
    ctx.strokeStyle="rgba(255,255,255,.40)"; ctx.lineWidth=1.5; ctx.setLineDash([5,6]);
    ctx.beginPath(); ctx.moveTo(hx,padTop); ctx.lineTo(hx,h-padBottom); ctx.stroke(); ctx.setLineDash([]);
    ctx.fillStyle="rgba(255,255,255,.8)"; ctx.font="11px monospace"; ctx.textAlign="left";
    ctx.fillText("HOY",hx+5,padTop+11);

    // Flecha proyección
    const lastNum=valores[puntos.length-1];
    const projNum=Number(graficaData.proyeccion_num??lastNum);
    const x1=hx+espacioPuntos*1.5, y1=yp(lastNum);
    const x2=hx+espacioPuntos*9;
    let y2=yp(Math.max(0,Math.min(99,projNum)));
    const maxMove=usableH*0.30;
    if(y2<y1-maxMove) y2=y1-maxMove;
    if(y2>y1+maxMove) y2=y1+maxMove;
    ctx.strokeStyle="rgba(180,100,255,.90)"; ctx.lineWidth=2.5; ctx.setLineDash([8,6]);
    ctx.beginPath(); ctx.moveTo(x1,y1); ctx.lineTo(x2,y2); ctx.stroke(); ctx.setLineDash([]);
    const ang=Math.atan2(y2-y1,x2-x1), hl=11;
    ctx.fillStyle="rgba(200,130,255,.95)"; ctx.beginPath(); ctx.moveTo(x2,y2);
    ctx.lineTo(x2-hl*Math.cos(ang-Math.PI/6),y2-hl*Math.sin(ang-Math.PI/6));
    ctx.lineTo(x2-hl*Math.cos(ang+Math.PI/6),y2-hl*Math.sin(ang+Math.PI/6));
    ctx.closePath(); ctx.fill();
    const label=`TEND ${graficaData.tendencia||""}  →${String(projNum).padStart(2,"0")}`;
    const lx=x1+4, ly=y2<y1?y2-10:y2+18;
    ctx.font="bold 11px monospace"; ctx.textAlign="left";
    ctx.fillStyle="rgba(5,7,10,.75)"; ctx.fillRect(lx-3,ly-13,ctx.measureText(label).width+9,16);
    ctx.fillStyle="rgba(220,180,255,.95)"; ctx.fillText(label,lx,ly);
  }

  // ── Candidatos IA: marcadores en borde derecho ────────────────────────────
  if(drawCount>=puntos.length){
    const cands=graficaData.candidatos_ia_nums||[];
    const rx=w-padRight+4;
    ctx.font="bold 10px monospace"; ctx.textAlign="left";
    cands.slice(0,18).forEach((n,i)=>{
      const yy=yp(n);
      const alpha=Math.max(0.35,1-(i/18)*0.65);
      // diamante
      ctx.fillStyle=`rgba(0,212,255,${alpha})`;
      ctx.beginPath(); ctx.moveTo(rx+7,yy); ctx.lineTo(rx+13,yy-5); ctx.lineTo(rx+19,yy); ctx.lineTo(rx+13,yy+5); ctx.closePath(); ctx.fill();
      ctx.fillStyle=`rgba(200,240,255,${alpha})`;
      ctx.fillText(String(n).padStart(2,"0"),rx+22,yy+4);
    });
    // Etiqueta columna
    ctx.fillStyle="rgba(0,212,255,.55)"; ctx.font="9px monospace"; ctx.textAlign="left";
    ctx.fillText("IA▼",rx+4,padTop+10);
  }

  // ── Eje X inferior ────────────────────────────────────────────────────────
  ctx.strokeStyle="rgba(200,230,255,.18)"; ctx.lineWidth=1;
  ctx.beginPath(); ctx.moveTo(0,h-padBottom); ctx.lineTo(w-padRight,h-padBottom); ctx.stroke();

  // ── Y axis labels (0-99) ──────────────────────────────────────────────────
  yAxis.innerHTML="";
  (graficaData.niveles||[]).slice().reverse().forEach(n=>{
    const yy=yp(n); const el=document.createElement("div");
    el.style.cssText=`position:absolute;right:4px;top:${Math.max(0,yy-8)}px;font-size:10px;color:#4a7fa0;font-family:monospace;`;
    el.textContent=String(n).padStart(2,"0"); yAxis.appendChild(el);
  });

  // ── Info bar ──────────────────────────────────────────────────────────────
  document.getElementById("grafica-info").textContent=
    `${graficaData.total} sorteos · zona IQR30:${nzMin}-${nzMax} · tend:${graficaData.tendencia||""} · proy:${graficaData.proyeccion_num??""} · IA: ${(graficaData.candidatos_ia_nums||[]).length} candidatos`;

  // ── Tooltip al tocar ──────────────────────────────────────────────────────
  canvas.onclick=function(ev){
    const rect=canvas.getBoundingClientRect();
    const scaleX=canvas.width/rect.width;
    const clickX=(ev.clientX-rect.left)*scaleX;
    let idx=0, mejor=Infinity;
    puntos.forEach((p,i)=>{ const d=Math.abs(clickX-xp(i)); if(d<mejor){mejor=d;idx=i;} });
    const p=puntos[idx];
    const ma7v=calcMA(valores,7); const ma15v=calcMA(valores,15); const ma30v=calcMA(valores,30);
    const sc=Number(p.score_ganador||0);
    const mov=idx>0?`(${valores[idx]-valores[idx-1]>0?"+":""}${valores[idx]-valores[idx-1]})`: "";
    const enRango=(sc>=srmin&&sc<=srmax)?"✅ en rango IA":(sc<srmin?"🟡 frío":"🔴 quemado");
    document.getElementById("grafica-tip").textContent=
      `📅 ${p.fecha}  🎯 Número: ${p.numero} ${mov}  🏁 Rank: ${p.rank_ganador}`+
      `\n📊 Score: ${p.score_ganador}  ${enRango}`+
      `\nMA7-num: ${ma7v[idx]?.toFixed(1)||"—"}  MA15: ${ma15v[idx]?.toFixed(1)||"—"}  MA30: ${ma30v[idx]?.toFixed(1)||"—"}`+
      (p.pendiente_memoria?"\n⚡ Nuevo (pendiente reaprender)":"");
  };
}

// ═══════════════════════════════════════════
// HEATMAP
// ═══════════════════════════════════════════
function pintarHeatmap(d){
  const cells=d.cells||[]; const grid=document.getElementById("heatmap-grid");
  const tip=document.getElementById("hm-tip"); grid.innerHTML="";
  const maxTotal=Math.max(...cells.map(c=>c.pos1),1);
  cells.forEach(c=>{
    const calor=c.pos1/maxTotal;
    let bg="";
    if(calor>0.75) bg="rgba(255,40,40,0.85)";
    else if(calor>0.50) bg="rgba(255,120,0,0.75)";
    else if(calor>0.25) bg="rgba(255,200,0,0.60)";
    else if(calor>0.05) bg="rgba(0,120,200,0.45)";
    else bg="rgba(10,25,45,0.8)";
    const el=document.createElement("div");
    el.className="hm-cell"; el.style.background=bg;
    el.style.color=calor>0.25?"#fff":"#4a7fa0";
    el.textContent=c.numero;
    el.onclick=()=>{
      tip.style.display="block";
      tip.textContent=`${c.numero}  · 1ra: ${c.pos1}× · 2da: ${c.pos2}× · 3ra: ${c.pos3}× · Atraso: ${c.atraso} sorteos · Calor: ${Math.round(calor*100)}%`;
    };
    grid.appendChild(el);
  });
  document.getElementById("card-heatmap").classList.remove("hidden");
}

function cerrar(){
  fetch("/cerrar").then(()=>{document.body.innerHTML="<h1 style='color:#00d4ff;text-align:center;margin-top:100px'>Servidor cerrado</h1>";});
}

// Poll background
setInterval(()=>{ if(pollCarga) pollearCarga(); if(pollAp) pollearAp(); },4000);
</script>
</body>
</html>"""

# ══════════════════════════════════════════════════════════
# ARRANQUE
# ══════════════════════════════════════════════════════════
if __name__=="__main__":
    print("="*55)
    print("🎯 DR001 ANGUILLA 10AM — IA PRO V5")
    print(f"   BASE: {BASE}")
    print("   http://127.0.0.1:4040")
    print("="*55)
    app.run(host="0.0.0.0",port=4040,debug=False,use_reloader=False)
