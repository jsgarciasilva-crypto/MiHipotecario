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

st.set_page_config(page_title="Mi Credito Produbanco", layout="wide", page_icon="🏦")
st.title("🏦 Dashboard Hipotecario - Produbanco")
st.markdown("Monitorea tu credito, audita porcentajes y descarga reportes.")

URL_HOJA = "https://docs.google.com/spreadsheets/d/1hOwRmaPU6BhM0gRl_8-yLcuOZuWC-W_iw1sk7lAwyRs/edit?usp=sharing"
URL_PUENTE = "https://script.google.com/macros/s/AKfycbws0PYJdAzDLS_wnd_4DbyTlUdY40uWaoPZR2Ny3XIC7Z0g98PmT0aRR43WElYJTU4/exec"

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
    st.error(f"Aviso de conexion: {err}")
    df_checks = pd.DataFrame({"Mes": range(1, 241), "Estado_Pago": [False] * 240})

with st.sidebar:
    st.header("1. Datos del Credito")
    fecha_inicio = st.date_input("Fecha inicio / primera cuota", datetime(2023, 1, 15))
    valor_vivienda = st.number_input("Valor casa ($)", value=100000.0, step=5000.0)
    monto = st.number_input("Monto Financiado ($)", value=80000.0, step=1000.0)
    tasa_anual = st.number_input("Tasa Anual (%)", value=9.5, step=0.1)
    plazo_anios = st.number_input("Plazo (Anios)", value=20, step=1)
    
    st.header("2. Seguros")
    tasa_desgravamen = st.number_input("Seg. Desgravamen (%)", value=0.72)
    tasa_incendio = st.number_input("Seg. Incendio (%)", value=0.15)

    st.header("3. Sistema")
    sistema = st.selectbox("Sistema Amortizacion", ["Frances (Cuota Fija)", "Aleman (Capital Fijo)"])

meses = int(plazo_anios * 12)
tasa_mes = (tasa_anual / 100) / 12
tasa_desg_mes = (tasa_desgravamen / 100) / 12
cuota_incendio = (valor_vivienda * (tasa_incendio / 100)) / 12

@st.cache_data
def generar_amortizacion(monto_inicial, plazo_meses, sistema_amort, fecha_arranque):
    tabla = []
    saldo = monto_inicial
    if "Frances" in sistema_amort:
        factor = (1 + tasa_mes) ** plazo_meses
        cuota_cap_int = monto_inicial * (tasa_mes * factor) / (factor - 1)
    else:
        abono_capital_fijo = monto_inicial / plazo_meses

    for mes in range(1, plazo_meses + 1):
        interes = saldo * tasa_mes
        seg_desg = saldo * tasa_desg_mes
        if "Frances" in sistema_amort:
            capital = cuota_cap_int - interes
        else:
            capital = abono_capital_fijo
            
        cuota_total = capital + interes + seg_desg + cuota_incendio
        saldo -= capital
        fecha_pago = fecha_arranque + relativedelta(months=mes - 1)
        tabla.append({
            "Mes": mes,
            "Fecha": fecha_pago.strftime('%Y-%m'),
            "Anio": fecha_pago.year,
            "Capital": round(capital, 2),
            "Interes": round(interes, 2),
            "Seguros": round(seg_desg + cuota_incendio, 2),
            "Cuota_Total": round(cuota_total, 2),
            "Saldo": round(max(0.0, saldo), 2)
        })
    return pd.DataFrame(tabla)

df_base = generar_amortizacion(monto, meses, sistema, fecha_inicio)

cuotas_pagadas_actual = int(df_checks["Estado_Pago"].sum())

if cuotas_pagadas_actual > 0:
    df_pagado = df_base.iloc[:cuotas_pagadas_actual]
    cap_pagado = float(df_pagado["Capital"].sum())
    int_pagado = float(df_pagado["Interes"].sum())
    seg_pagado = float(df_pagado["Seguros"].sum())
    saldo_deudor = float(df_base.loc[cuotas_pagadas_actual - 1, "Saldo"])
else:
    cap_pagado = 0.0
    int_pagado = 0.0
    seg_pagado = 0.0
    saldo_deudor = float(monto)

tot_desembolsado = cap_pagado + int_pagado + seg_pagado
cap_total = float(monto)
int_total = float(df_base["Interes"].sum())
seg_total = float(df_base["Seguros"].sum())
costo_total_credito = cap_total + int_total + seg_total

int_pendiente = max(0.0, int_total - int_pagado)
seg_pendiente = max(0.0, seg_total - seg_pagado)
costo_pendiente = max(0.0, costo_total_credito - tot_desembolsado)

pct_cap = (cap_pagado / cap_total * 100.0) if cap_total > 0 else 0.0
pct_int = (int_pagado / int_total * 100.0) if int_total > 0 else 0.0
pct_seg = (seg_pagado / seg_total * 100.0) if seg_total > 0 else 0.0
pct_tot = (tot_desembolsado / costo_total_credito * 100.0) if costo_total_credito > 0 else 0.0

def generar_pdf():
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "ESTADO DE CUENTA HIPOTECARIO", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Fecha de corte: {datetime.now().strftime('%Y-%m-%d %H:%M')}", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(5)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 7, "1. CONDICIONES DEL CREDITO", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(95, 6, f"Monto Financiado: ${monto:,.2f}")
    pdf.cell(95, 6, f"Tasa Anual: {tasa_anual:.2f}%", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(95, 6, f"Sistema: {sistema.split(' ')[0]}")
    pdf.cell(95, 6, f"Plazo: {plazo_anios} anios ({meses} meses)", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(95, 6, f"Fecha Primera Cuota: {fecha_inicio.strftime('%Y-%m-%d')}")
    pdf.cell(95, 6, f"Cuotas Pagadas: {cuotas_pagadas_actual} de {meses}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 7, "2. ESTADO ACTUAL DE LA DEUDA", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(95, 6, f"Saldo Deudor Actual: ${saldo_deudor:,.2f}")
    pdf.cell(95, 6, f"Capital Pagado: ${cap_pagado:,.2f}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(95, 6, f"% Propiedad Pagado: {pct_cap:.2f}%")
    pdf.cell(95, 6, f"Cuotas Pendientes: {meses - cuotas_pagadas_actual}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 7, "3. DESGLOSE FINANCIERO Y AVANCE", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(230, 230, 230)
    pdf.cell(40, 7, "Rubro", border=1, align="C", fill=True)
    pdf.cell(38, 7, "Total Proyectado", border=1, align="C", fill=True)
    pdf.cell(38, 7, "Pagado a Fecha", border=1, align="C", fill=True)
    pdf.cell(38, 7, "Saldo Pendiente", border=1, align="C", fill=True)
    pdf.cell(36, 7, "% Pagado", border=1, align="C", fill=True, new_x="LMARGIN", new_y="NEXT")
    filas_pdf = [
        ("Capital", cap_total, cap_pagado, saldo_deudor, pct_cap),
        ("Intereses", int_total, int_pagado, int_pendiente, pct_int),
        ("Seguros", seg_total, seg_pagado, seg_pendiente, pct_seg),
        ("TOTAL GENERAL", costo_total_credito, tot_desembolsado, costo_pendiente, pct_tot)
    ]
    for rubro, tot_v, pag_v, pend_v, p_v in filas_pdf:
        est = "B" if rubro == "TOTAL GENERAL" else ""
        pdf.set_font("Helvetica", est, 9)
        pdf.cell(40, 6, rubro, border=1, align="L")
        pdf.cell(38, 6, f"${tot_v:,.2f}", border=1, align="R")
        pdf.cell(38, 6, f"${pag_v:,.2f}", border=1, align="R")
        pdf.cell(38, 6, f"${pend_v:,.2f}", border=1, align="R")
        pdf.cell(36, 6, f"{p_v:.1f}%", border=1, align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 7, "4. PROYECCION SRI (INTERESES DEDUCIBLES)", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    sri_calc = df_base.groupby("Anio")["Interes"].sum().reset_index()
    for _, fila in sri_calc.iterrows():
        pdf.cell(60, 5, f"Ejercicio Fiscal {int(fila['Anio'])}:")
        pdf.cell(50, 5, f"${fila['Interes']:,.2f}", new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "☑️ Control de Pagos", 
    "📊 Avance y Rubros", 
    "💸 Abonos Extra", 
    "📈 SRI", 
    "📄 Reporte PDF"
])

with tab1:
    st.subheader("Registro de Cuotas Canceladas")
    st.info(f"Cuotas pagadas registradas: **{cuotas_pagadas_actual} de {meses}** | Saldo Deudor: **${saldo_deudor:,.2f}**")
    anios_credito = list(range(1, int(plazo_anios) + 1))
    anio_seleccionado = st.selectbox("Selecciona el Anio del Credito:", anios_credito)
    mes_inicio_vista = (anio_seleccionado - 1) * 12
    mes_fin_vista = min(anio_seleccionado * 12, meses)
    st.markdown("---")
    with st.form("formulario_pagos"):
        estados_modificados = df_checks["Estado_Pago"].copy()
        for i in range(mes_inicio_vista, mes_fin_vista):
            fila = df_base.iloc[i]
            c1, c2, c3, c4 = st.columns([1, 2, 2, 2])
            valor_actual = bool(df_checks.loc[i, "Estado_Pago"]) if i < len(df_checks) else False
            check = c1.checkbox(f"Mes {fila['Mes']}", value=valor_actual, key=f"pago_chk_{i}")
            estados_modificados[i] = check
            c2.write(f"📅 **{fila['Fecha']}**")
            c3.write(f"💵 **Cuota:** ${fila['Cuota_Total']:,.2f}")
            c4.markdown("✅ *Pagado*" if check else "⏳ *Pendiente*")
            st.divider()
        boton_guardar = st.form_submit_button("💾 Guardar Cambios en Google Sheets")
        if boton_guardar:
            with st.spinner("Guardando cambios en Google Sheets..."):
                lista_a_guardar = [bool(x) for x in estados_modificados.tolist()]
                try:
                    respuesta = requests.post(URL_PUENTE, json=lista_a_guardar, timeout=15)
                    st.cache_data.clear()
                    st.success("Pagos actualizados y guardados!")
                    st.rerun()
                except Exception as err_puente:
                    st.error(f"Error al enviar datos: {err_puente}")

with tab2:
    st.subheader("Auditoria de Pagos y Porcentajes de Avance")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Capital Amortizado", f"${cap_pagado:,.2f}", f"{pct_cap:.1f}%")
    col2.metric("Intereses Cancelados", f"${int_pagado:,.2f}", f"{pct_int:.1f}%")
    col3.metric("Seguros Desembolsados", f"${seg_pagado:,.2f}", f"{pct_seg:.1f}%")
    col4.metric("Desembolso General", f"${tot_desembolsado:,.2f}", f"{pct_tot:.1f}%")
    st.markdown("---")
    st.markdown("#### Tabla de Distribucion Financiera")
    tabla_resumen =
