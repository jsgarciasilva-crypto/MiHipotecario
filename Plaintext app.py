import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
from dateutil.relativedelta import relativedelta
import plotly.express as px
import plotly.graph_objects as go
import requests
from fpdf import FPDF
from streamlit_gsheets import GSheetsConnection

st.set_page_config(page_title="Mi Crédito Produbanco", layout="wide", page_icon="🏦")

st.title("🏦 Dashboard Hipotecario - Produbanco")
st.markdown("Monitorea tu crédito, audita tus porcentajes de avance y descarga reportes ejecutivos.")

# --- ENLACES DE CONEXIÓN ---
URL_HOJA = "https://docs.google.com/spreadsheets/d/1hOwRmaPU6BhM0gRl_8-yLcuOZuWC-W_iw1sk7lAwyRs/edit?usp=sharing"
URL_PUENTE = "https://script.google.com/macros/s/AKfycbws0PYJdAzDLS_wnd_4DbyTlUdY40uWaoPZR2Ny3XIC7Z0g98PmT0aRR43WElYJTU4/exec"

# --- LECTURA DESDE GOOGLE SHEETS ---
conn = st.connection("gsheets", type=GSheetsConnection)

try:
    df_checks = conn.read(spreadsheet=URL_HOJA, ttl=0)
    df_checks.columns = [str(c).strip() for c in df_checks.columns]
    
    if "Estado_Pago" in df_checks.columns:
        df_checks["Estado_Pago"] = df_checks["Estado_Pago"].astype(str).str.strip().str.upper().isin(["TRUE", "VERDADERO", "1"])
    else:
        df_checks["Estado_Pago"] = False

    if "Mes" not in df_checks.columns:
        df_checks["Mes"] = range(1, len(df_checks) + 1)
except Exception as err:
    st.error(f"Aviso de conexión: {err}")
    df_checks = pd.DataFrame({"Mes": range(1, 241), "Estado_Pago": [False] * 240})

# --- BARRA LATERAL: PARÁMETROS DEL PRÉSTAMO ---
with st.sidebar:
    st.header("1. Datos del Crédito")
    fecha_inicio = st.date_input("Fecha de inicio / primera cuota", datetime(2023, 1, 15))
    valor_vivienda = st.number_input("Valor total de la casa ($)", value=100000.0, step=5000.0)
    monto = st.number_input("Monto Financiado ($)", value=80000.0, step=1000.0)
    tasa_anual = st.number_input("Tasa de Interés Anual (%)", value=9.5, step=0.1)
    plazo_anios = st.number_input("Plazo (Años)", value=20, step=1)
    
    st.header("2. Seguros")
    tasa_desgravamen = st.number_input("Seg. Desgravamen anual (%)", value=0.72)
    tasa_incendio = st.number_input("Seg. Incendio anual (%)", value=0.15)

    st.header("3. Sistema")
    sistema = st.selectbox("Sistema de Amortización", ["Francés (Cuota Fija)", "Alemán (Capital Fijo, Cuota Decreciente)"])

# --- CÁLCULOS MATEMÁTICOS BASE ---
meses = int(plazo_anios * 12)
tasa_mes = (tasa_anual / 100) / 12
tasa_desg_mes = (tasa_desgravamen / 100) / 12
cuota_incendio = (valor_vivienda * (tasa_incendio / 100)) / 12

@st.cache_data
def generar_amortizacion(monto_inicial, plazo_meses, sistema_amort, fecha_arranque):
    tabla = []
    saldo = monto_inicial
    
    if "Francés" in sistema_amort:
        cuota_cap_int = monto_inicial * (tasa_mes * (1 + tasa_mes)**plazo_meses) / ((1 + tasa_mes)**plazo_meses - 1)
    else:
        abono_capital_fijo = monto_inicial / plazo_meses

    for mes in range(1, plazo_meses + 1):
        interes = saldo * tasa_mes
        seg_desg = saldo * tasa_desg_mes
        
        if "Francés" in sistema_amort:
            capital = cuota_cap_int - interes
        else:
            capital = abono_capital_fijo
            
        cuota_total = capital + interes + seg_desg + cuota_incendio
        saldo -= capital
        fecha_pago = fecha_arranque + relativedelta(months=mes-1)
        
        tabla.append({
            "Mes": mes,
            "Fecha": fecha_pago.strftime('%Y-%m'),
            "Año Calendario": fecha_pago.year,
            "Capital ($)": round(capital, 2),
            "Interés ($)": round(interes, 2),
            "Seguros ($)": round(seg_desg + cuota_incendio, 2),
            "Cuota Total ($)": round(cuota_total, 2),
            "Saldo Deudor ($)": round(max(0.0, saldo), 2)
        })
    return pd.DataFrame(tabla)

df_base = generar_amortizacion(monto, meses, sistema, fecha_inicio)

# Consolidación de Pagos
cuotas_pagadas_actual = int(df_checks["Estado_Pago"].sum())

# Desglose Financiero de Avance
df_pagado = df_base.iloc[:cuotas_pagadas_actual] if cuotas_pagadas_actual > 0 else pd.DataFrame(columns=df_base.columns)

cap_pagado = float(df_pagado["Capital ($)"].sum()) if not df_pagado.empty else 0.0
int_pagado
