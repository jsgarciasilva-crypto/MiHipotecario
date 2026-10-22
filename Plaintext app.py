import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
import plotly.express as px
import plotly.graph_objects as go
import requests
from fpdf import FPDF
from streamlit_gsheets import GSheetsConnection

st.set_page_config(
    page_title="Hipotecario Garcia Castillo", 
    layout="wide", 
    page_icon="🏛️"
)

# --- PALETA CORPORATIVA GARCIA ANDRADE ---
COLOR_NAVY = "#0E2A47"
COLOR_GOLD = "#C5A059"
COLOR_BG_CARD = "#FFFFFF"

# --- ESTILOS VISUALES ---
st.markdown(f"""
<style>
    .header-title {{
        color: {COLOR_NAVY};
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
        font-weight: 700;
        letter-spacing: -0.5px;
        margin-bottom: 2px;
    }}
    .header-sub {{
        color: {COLOR_GOLD};
        font-size: 1.05rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 1px;
        margin-bottom: 20px;
    }}
    .stButton>button, .stDownloadButton>button {{
        background-color: {COLOR_NAVY} !important;
        color: #FFFFFF !important;
        border: 1px solid {COLOR_GOLD} !important;
        border-radius: 6px !important;
        font-weight: 600 !important;
        transition: all 0.3s ease !important;
    }}
    .stButton>button:hover, .stDownloadButton>button:hover {{
        background-color: {COLOR_GOLD} !important;
        color: {COLOR_NAVY} !important;
        border: 1px solid {COLOR_NAVY} !important;
    }}
    button[data-baseweb="tab"][aria-selected="true"] {{
        border-bottom-color: {COLOR_GOLD} !important;
        color: {COLOR_NAVY} !important;
        font-weight: 700 !important;
    }}
</style>
""", unsafe_allow_html=True)

st.markdown('<h1 class="header-title">🏛️ Monitor Hipotecario</h1>', unsafe_allow_html=True)
st.markdown('<p class="header-sub">Crédito Hipotecario Produbanco Familia García Castillo</p>', unsafe_allow_html=True)

URL_HOJA = "https://docs.google.com/spreadsheets/d/1hOwRmaPU6BhM0gRl_8-yLcuOZuWC-W_iw1sk7lAwyRs/edit?usp=sharing"
URL_PUENTE = "https://script.google.com/macros/s/AKfycbws0PYJdAzDLS_wnd_4DbyTlUdY40uWaoPZR2Ny3XIC7Z0g98PmT0aRR43WElYJTU4/exec"

conn = st.connection("gsheets", type=GSheetsConnection)

# Inicializacion persistente y reactiva de los pagos
if "pagos_lista" not in st.session_state:
    try:
        df_sheet = conn.read(spreadsheet=URL_HOJA, ttl=0)
        df_sheet.columns = [str(c).strip() for c in df_sheet.columns]
        if "Estado_Pago" in df_sheet.columns:
            pagos = df_sheet["Estado_Pago"].astype(str).str.strip().str.upper().isin(["TRUE", "VERDADERO", "1"]).tolist()
        else:
            pagos = [False] * 240
    except Exception:
        pagos = [False] * 240
        
    if len(pagos) < 240:
        pagos.extend([False] * (240 - len(pagos)))
    st.session_state["pagos_lista"] = pagos[:240]

def actualizar_check(idx):
    st.session_state["pagos_lista"][idx] = st.session_state[f"chk_{idx}"]

# --- BARRA LATERAL DINAMICA ---
with st.sidebar:
    st.header("1. Datos del Credito")
    fecha_inicio = st.date_input("Fecha inicio / primera cuota", date(2026, 12, 1))
    valor_vivienda = st.number_input("Valor casa ($)", value=315000.0, step=5000.0)
    monto = st.number_input("Monto Financiado ($)", value=240000.0, step=1000.0)
    tasa_anual = st.number_input("Tasa Anual (%)", value=6.5, step=0.1)
    plazo_anios = st.number_input("Plazo (Anios)", value=20, step=1)
    
    st.header("2. Seguros")
    tasa_desgravamen = st.number_input("Seg. Desgravamen (%)", value=0.72, step=0.01)
    tasa_incendio = st.number_input("Seg. Incendio (%)", value=0.15, step=0.01)

    st.header("3. Sistema")
    sistema = st.selectbox("Sistema Amortizacion", ["Frances (Cuota Fija)", "Aleman (Capital Fijo)"])

# Parametros calculados en caliente
meses = int(plazo_anios * 12)
tasa_mes = (tasa_anual / 100.0) / 12.0
tasa_desg_mes = (tasa_desgravamen / 100.0) / 12.0
cuota_incendio = (valor_vivienda * (tasa_incendio / 100.0)) / 12.0

def generar_amortizacion(monto_val, plazo_val, sistema_val, fecha_val, t_anual_val, t_desg_val, t_inc_val, v_casa_val):
    tabla = []
    saldo = float(monto_val)
    tm = (t_anual_val / 100.0) / 12.0
    tdm = (t_desg_val / 100.0) / 12.0
    ci = (v_casa_val * (t_inc_val / 100.0)) / 12.0

    if "Frances" in sistema_val:
        factor = (1.0 + tm) ** plazo_val
        cuota_cap_int = monto_val * (tm * factor) / (factor - 1.0)
    else:
        abono_capital_fijo = monto_val / plazo_val

    for mes in range(1, plazo_val + 1):
        interes = saldo * tm
        seg_desg = saldo * tdm
        if "Frances" in sistema_val:
            capital = cuota_cap_int - interes
        else:
            capital = abono_capital_fijo
            
        cuota_total = capital + interes + seg_desg + ci
        saldo -= capital
        fecha_pago = fecha_val + relativedelta(months=mes - 1)
        tabla.append({
            "Mes": mes,
            "Fecha": fecha_pago.strftime('%Y-%m'),
            "Anio": fecha_pago.year,
            "Capital": round(capital, 2),
            "Interes": round(interes, 2),
            "Seguros": round(seg_desg + ci, 2),
            "Cuota_Total": round(cuota_total, 2),
            "Saldo": round(max(0.0, saldo), 2)
        })
    return pd.DataFrame(tabla)

df_base = generar_amortizacion(monto, meses, sistema, fecha_inicio, tasa_anual, tasa_desgravamen, tasa_incendio, valor_vivienda)

# Cantidad de pagos actualizada al instante
cuotas_pagadas_actual = sum(st.session_state["pagos_lista"])

if cuotas_pagadas_actual > 0 and cuotas_pagadas_actual <= len(df_base):
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

# Calculo de proxima cuota y semaforo en tiempo real
proximo_mes_idx = min(cuotas_pagadas_actual, meses - 1)
fila_proxima = df_base.iloc[proximo_mes_idx]
fecha_prox_dt = fecha_inicio + relativedelta(months=proximo_mes_idx)
hoy = date.today()
dias_restantes = (fecha_prox_dt - hoy).days

col_b1, col_b2, col_b3 = st.columns(3)
col_b1.metric("Proxima Cuota a Pagar", f"Mes {fila_proxima['Mes']} ({fila_proxima['Fecha']})")
col_b2.metric("Valor a Debitar", f"${fila_proxima['Cuota_Total']:,.2f}")
if dias_restantes > 0:
    col_b3.metric("Dias Restantes para Corte", f"{dias_restantes} dias", delta="A tiempo", delta_color="normal")
elif dias_restantes == 0:
    col_b3.metric("Dias Restantes para Corte", "HOY es dia de corte", delta="Atencion", delta_color="inverse")
else:
    col_b3.metric("Estado de Cuota", f"Corte paso hace {abs(dias_restantes)} dias", delta="Verificar pago", delta_color="inverse")

def generar_pdf():
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    C_RGB_NAVY = (14, 42, 71)
    C_RGB_GOLD = (197, 160, 89)
    C_RGB_TEXT = (45, 55, 72)
    C_RGB_GRAY = (240, 243, 246)
    
    pdf.set_fill_color(*C_RGB_NAVY)
    pdf.rect(10, 10, 190, 4, "F")
    pdf.set_fill_color(*C_RGB_GOLD)
    pdf.rect(10, 14, 190, 1.5, "F")
    
    pdf.set_y(20)
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(*C_RGB_NAVY)
    pdf.cell(0, 8, "ESTADO DE CUENTA HIPOTECARIO", ln=True, align="C")
    
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*C_RGB_GOLD)
    pdf.cell(0, 5, "CREDITO HIPOTECARIO PRODUBANCO FAMILIA GARCIA CASTILLO", ln=True, align="C")
    
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(130, 140, 150)
    pdf.cell(0, 5, f"Fecha de corte: {datetime.now().strftime('%Y-%m-%d %H:%M')}", ln=True, align="C")
    pdf.ln(4)
    
    pdf.set_draw_color(*C_RGB_GOLD)
    pdf.set_line_width(0.5)
    pdf.line(15, pdf.get_y(), 195, pdf.get_y())
    pdf.ln(5)
    
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*C_RGB_NAVY)
    pdf.cell(0, 6, "1. CONDICIONES GENERALES DEL CREDITO", ln=True)
    
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*C_RGB_TEXT)
    pdf.cell(95, 5, f"Monto Financiado: ${monto:,.2f}")
    pdf.cell(95, 5, f"Tasa Nominal Anual: {tasa_anual:.2f}%", ln=True)
    pdf.cell(95, 5, f"Sistema: {sistema.split(' ')[0]}")
    pdf.cell(95, 5, f"Plazo: {plazo_anios} anios ({meses} meses)", ln=True)
    pdf.cell(95, 5, f"Fecha Primera Cuota: {fecha_inicio.strftime('%Y-%m-%d')}")
    pdf.cell(95, 5, f"Cuotas Pagadas: {cuotas_pagadas_actual} de {meses}", ln=True)
    pdf.ln(4)
    
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*C_RGB_NAVY)
    pdf.cell(0, 6, "2. ESTADO ACTUAL DE LA DEUDA", ln=True)
    
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*C_RGB_TEXT)
    pdf.cell(95, 5, f"Saldo Deudor Actual: ${saldo_deudor:,.2f}")
    pdf.cell(95, 5, f"Capital Pagado: ${cap_pagado:,.2f}", ln=True)
    pdf.cell(95, 5, f"% Propiedad Cancelado: {pct_cap:.2f}%")
    pdf.cell(95, 5, f"Cuotas Pendientes: {meses - cuotas_pagadas_actual}", ln=True)
    pdf.ln(4)
    
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*C_RGB_NAVY)
    pdf.cell(0, 6, "3. DESGLOSE FINANCIERO Y AUDITORIA DE AVANCE", ln=True)
    
    pdf.set_fill_color(*C_RGB_NAVY)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(40, 6, "Rubro", border=1, align="C", fill=True)
    pdf.cell(38, 6, "Total Proyectado", border=1, align="C", fill=True)
    pdf.cell(38, 6, "Pagado a Fecha", border=1, align="C", fill=True)
    pdf.cell(38, 6, "Saldo Pendiente", border=1, align="C", fill=True)
    pdf.cell(36, 6, "% Pagado", border=1, align="C", fill=True, ln=True)
    
    filas_pdf = [
        ("Capital", cap_total, cap_pagado, saldo_deudor, pct_cap),
        ("Intereses", int_total, int_pagado, int_pendiente, pct_int),
        ("Seguros", seg_total, seg_pagado, seg_pendiente, pct_seg),
        ("TOTAL GENERAL", costo_total_credito, tot_desembolsado, costo_pendiente, pct_tot)
    ]
    
    pdf.set_draw_color(210, 215, 225)
    for rubro, tot_v, pag_v, pend_v, p_v in filas_pdf:
        if rubro == "TOTAL GENERAL":
            pdf.set_fill_color(*C_RGB_GRAY)
            pdf.set_text_color(*C_RGB_NAVY)
            pdf.set_font("Helvetica", "B", 8)
            fill_flag = True
        else:
            pdf.set_text_color(*C_RGB_TEXT)
            pdf.set_font("Helvetica", "", 8)
            fill_flag = False
            
        pdf.cell(40, 5.5, rubro, border=1, align="L", fill=fill_flag)
        pdf.cell(38, 5.5, f"${tot_v:,.2f}", border=1, align="R", fill=fill_flag)
        pdf.cell(38, 5.5, f"${pag_v:,.2f}", border=1, align="R", fill=fill_flag)
        pdf.cell(38, 5.5, f"${pend_v:,.2f}", border=1, align="R", fill=fill_flag)
        pdf.cell(36, 5.5, f"{p_v:.1f}%", border=1, align="R", fill=fill_flag, ln=True)
        
    pdf.ln(5)
    
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*C_RGB_NAVY)
    pdf.cell(0, 6, "4. PROYECCION SRI (INTERESES DEDUCIBLES)", ln=True)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*C_RGB_TEXT)
    sri_calc = df_base.groupby("Anio")["Interes"].sum().reset_index()
    for _, fila in sri_calc.iterrows():
        pdf.cell(60, 5, f"Ejercicio Fiscal {int(fila['Anio'])}:")
        pdf.cell(50, 5, f"${fila['Interes']:,.2f}", ln=True)
        
    out = pdf.output()
    return out.encode('latin-1') if isinstance(out, str) else bytes(out)

tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "☑️ Control de Pagos", 
    "📊 Avance y Graficos", 
    "💸 Abonos Puntuales",
    "❄️ Micro-Abonos (Bola de Nieve)",
    "⚖️ Prepago vs Inversion",
    "📈 SRI", 
    "📄 Reporte PDF"
])

with tab1:
    st.subheader("Registro de Cuotas Canceladas")
    
    col_t1, col_t2 = st.columns([3, 1])
    col_t1.info(f"Cuotas pagadas registradas: **{cuotas_pagadas_actual} de {meses}** | Saldo Deudor: **${saldo_deudor:,.2f}**")
    
    if col_t2.button("💾 Guardar en la Nube", key="btn_save_top"):
        with st.spinner("Guardando permanentemente en Google Sheets..."):
            try:
                requests.post(URL_PUENTE, json=st.session_state["pagos_lista"], timeout=15)
                st.success("¡Datos guardados con éxito en Google Sheets!")
            except Exception as err_puente:
                st.error(f"Error al enviar datos: {err_puente}")

    anios_credito = list(range(1, int(plazo_anios) + 1))
    anio_seleccionado = st.selectbox("Selecciona el Anio del Credito:", anios_credito)
    mes_inicio_vista = (anio_seleccionado - 1) * 12
    mes_fin_vista = min(anio_seleccionado * 12, meses)
    st.markdown("---")
    
    for i in range(mes_inicio_vista, mes_fin_vista):
        fila = df_base.iloc[i]
        c1, c2, c3, c4 = st.columns([1, 2, 2, 2])
        valor_actual = st.session_state["pagos_lista"][i]
        
        check = c1.checkbox(
            f"Mes {fila['Mes']}", 
            value=valor_actual, 
            key=f"chk_{i}", 
            on_change=actualizar_check, 
            args=(i,)
        )
        c2.write(f"📅 **{fila['Fecha']}**")
        c3.write(f"💵 **Cuota:** ${fila['Cuota_Total']:,.2f}")
        c4.markdown("✅ *Pagado*" if valor_actual else "⏳ *Pendiente*")
        st.divider()
        
    if st.button("💾 Guardar Cambios en Google Sheets", key="btn_save_bottom"):
        with st.spinner("Guardando permanentemente en Google Sheets..."):
            try:
                requests.post(URL_PUENTE, json=st.session_state["pagos_lista"], timeout=15)
                st.success("¡Datos guardados con éxito en Google Sheets!")
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
    
    filas_resumen = [
        {"Rubro": "Capital", "Total Proyectado": f"${cap_total:,.2f}", "Pagado a la Fecha": f"${cap_pagado:,.2f}", "% Pagado": f"{pct_cap:.2f}%", "Saldo Pendiente": f"${saldo_deudor:,.2f}", "% Pendiente": f"{100-pct_cap:.2f}%"},
        {"Rubro": "Intereses", "Total Proyectado": f"${int_total:,.2f}", "Pagado a la Fecha": f"${int_pagado:,.2f}", "% Pagado": f"{pct_int:.2f}%", "Saldo Pendiente": f"${int_pendiente:,.2f}", "% Pendiente": f"{100-pct_int:.2f}%"},
        {"Rubro": "Seguros", "Total Proyectado": f"${seg_total:,.2f}", "Pagado a la Fecha": f"${seg_pagado:,.2f}", "% Pagado": f"{pct_seg:.2f}%", "Saldo Pendiente": f"${seg_pendiente:,.2f}", "% Pendiente": f"{100-pct_seg:.2f}%"},
        {"Rubro": "Total General", "Total Proyectado": f"${costo_total_credito:,.2f}", "Pagado a la Fecha": f"${tot_desembolsado:,.2f}", "% Pagado": f"{pct_tot:.2f}%", "Saldo Pendiente": f"${costo_pendiente:,.2f}", "% Pendiente": f"{100-pct_tot:.2f}%"}
    ]
    tabla_resumen = pd.DataFrame(filas_resumen)
    st.dataframe(tabla_resumen, use_container_width=True)
    st.markdown("---")
    st.markdown("#### Progreso de Titularidad del Inmueble")
    st.progress(min(100, int(pct_cap)))
    st.caption(f"Tienes libre de hipoteca el **{pct_cap:.2f}%** del valor original financiado.")

    st.markdown("---")
    st.markdown("#### Curva de Amortizacion: Descenso de Saldo Deudor")
    fig_saldo = px.area(
        df_base, 
        x="Mes", 
        y="Saldo", 
        title="Proyeccion del Saldo Deudor en el Tiempo",
        labels={"Saldo": "Saldo Deudor ($)", "Mes": "Numero de Mes"},
        color_discrete_sequence=[COLOR_NAVY]
    )
    if cuotas_pagadas_actual > 0:
        fig_saldo.add_vline(x=cuotas_pagadas_actual, line_dash="dash", line_color=COLOR_GOLD, annotation_text="Punto Actual")
    fig_saldo.update_layout(
        plot_bgcolor="#FFFFFF",
        paper_bgcolor="#FFFFFF",
        font=dict(color=COLOR_NAVY)
    )
    st.plotly_chart(fig_saldo, use_container_width=True)

with tab3:
    st.subheader("Simulador de Abonos Extraordinarios Puntuales")
    col_a, col_b, col_c = st.columns(3)
    mes_sug = min(cuotas_pagadas_actual + 1, meses)
    mes_abono = col_a.number_input("Mes del abono", min_value=1, max_value=meses, value=mes_sug, key="abono_mes_input")
    monto_abono = col_b.number_input("Monto del Abono ($)", min_value=100.0, value=5000.0, step=500.0, key="abono_monto_input")
    tipo_beneficio = col_c.radio("Objetivo del abono", ["Reducir Plazo", "Reducir Cuota"], key="abono_tipo_input")
    if st.button("Calcular impacto del abono puntual"):
        if mes_abono < meses:
            saldo_en_mes = df_base.loc[mes_abono-1, 'Saldo']
            if monto_abono >= saldo_en_mes:
                st.success("Con este monto cancelas la totalidad de la deuda!")
            else:
                nuevo_saldo = saldo_en_mes - monto_abono
                meses_restantes = meses - mes_abono
                tot_int_orig = df_base['Interes'].sum()
                if tipo_beneficio == "Reducir Cuota":
                    df_nuevo = generar_amortizacion(nuevo_saldo, meses_restantes, sistema, fecha_inicio + relativedelta(months=mes_abono), tasa_anual, tasa_desgravamen, tasa_incendio, valor_vivienda)
                    nueva_cuota = df_nuevo.loc[0, 'Cuota_Total']
                    ahorro = tot_int_orig - (df_base.loc[:mes_abono-1, 'Interes'].sum() + df_nuevo['Interes'].sum())
                    st.success(f"Tu nueva cuota baja a: **\\${nueva_cuota:,.2f}**")
                    st.info(f"Ahorro estimado en intereses: **\\${ahorro:,.2f}**")
                else:
                    cuota_ref = df_base.loc[mes_abono, 'Capital'] + df_base.loc[mes_abono, 'Interes']
                    try:
                        n_meses = -np.log(1 - (nuevo_saldo * tasa_mes) / cuota_ref) / np.log(1 + tasa_mes)
                        n_meses = int(np.ceil(n_meses))
                        ahorrados = meses_restantes - n_meses
                        df_nuevo = generar_amortizacion(nuevo_saldo, n_meses, sistema, fecha_inicio + relativedelta(months=mes_abono), tasa_anual, tasa_desgravamen, tasa_incendio, valor_vivienda)
                        ahorro = tot_int_orig - (df_base.loc[:mes_abono-1, 'Interes'].sum() + df_nuevo['Interes'].sum())
                        st.success(f"Terminas de pagar **{ahorrados} meses antes** (equivale a {ahorrados/12:.1f} anios).")
                        st.info(f"Ahorro estimado en intereses: **\\${ahorro:,.2f}**")
                    except Exception:
                        st.info("El abono cubre la totalidad del credito pendiente.")
        else:
            st.warning("No es posible realizar un abono en la ultima cuota.")

with tab4:
    st.subheader("❄️ Simulador de Micro-Abonos Mensuales (Efecto Bola de Nieve)")
    st.markdown("¿Que pasa si sumas una cantidad fija a capital cada mes ademas de tu cuota normal?")
    
    col_sn1, col_sn2 = st.columns(2)
    micro_abono = col_sn1.slider("Abono extra mensual a capital ($)", min_value=25, max_value=1000, value=100, step=25)
    mes_inicio_snowball = col_sn2.number_input("Iniciar micro-abonos desde el mes:", min_value=cuotas_pagadas_actual + 1, max_value=meses, value=cuotas_pagadas_actual + 1)
    
    saldo_snow = saldo_deudor
    meses_transcurridos = cuotas_pagadas_actual
    tot_int_snow = int_pagado
    
    factor_ref = (1 + tasa_mes) ** meses
    cuota_fija_cap_int = monto * (tasa_mes * factor_ref) / (factor_ref - 1)
    
    mes_actual_sim = meses_transcurridos
    while saldo_snow > 0.01 and mes_actual_sim < meses:
        mes_actual_sim += 1
        interes_mes = saldo_snow * tasa_mes
        tot_int_snow += interes_mes
        
        capital_regular = cuota_fija_cap_int - interes_mes
        abono_aplicable = micro_abono if mes_actual_sim >= mes_inicio_snowball else 0.0
        
        capital_total_mes = min(saldo_snow, capital_regular + abono_aplicable)
        saldo_snow -= capital_total_mes
    
    meses_ahorrados_snow = meses - mes_actual_sim
    anios_ahorrados_snow = meses_ahorrados_snow / 12.0
    ahorro_interes_snow = max(0.0, int_total - tot_int_snow)
    
    cs1, cs2, cs3 = st.columns(3)
    cs1.metric("Tiempo Ahorrado", f"{meses_ahorrados_snow} meses", f"{anios_ahorrados_snow:.1f} anios antes")
    cs2.metric("Ahorro Total en Intereses", f"${ahorro_interes_snow:,.2f}")
    cs3.metric("Nuevo Mes Final", f"Mes {mes_actual_sim} de {meses}")
    
    st.info(f"💡 Al aportar **\\${micro_abono:,.2f} extra cada mes**, cancelas tu deuda en **{mes_actual_sim - cuotas_pagadas_actual} meses mas** en lugar de {meses - cuotas_pagadas_actual} meses restantes.")

with tab5:
    st.subheader("⚖️ Analisis Financiero: Prepagar Credito vs Invertir en Poliza")
    st.markdown("Compara el costo de tu deuda frente al rendimiento de depositar tu dinero en una poliza o fondo.")
    
    tasa_costo_efectivo = tasa_anual + tasa_desgravamen + tasa_incendio
    col_inv1, col_inv2 = st.columns(2)
    tasa_inversion = col_inv1.number_input("Rendimiento anual estimado de tu inversion / poliza (%)", value=8.5, step=0.25)
    capital_analisis = col_inv2.number_input("Monto de capital disponible para evaluar ($)", value=5000.0, step=500.0)
    
    diff_tasa = tasa_costo_efectivo - tasa_inversion
    ahorro_anual_credito = capital_analisis * (tasa_costo_efectivo / 100.0)
    ganancia_anual_inversion = capital_analisis * (tasa_inversion / 100.0)
    
    col_m1, col_m2, col_m3 = st.columns(3)
    col_m1.metric("Costo Total Deuda (Tasa + Seguros)", f"{tasa_costo_efectivo:.2f}%")
    col_m2.metric("Rendimiento Inversion", f"{tasa_inversion:.2f}%")
    col_m3.metric("Diferencial Financiero", f"{abs(diff_tasa):.2f}%", delta="Ventaja Prepago" if diff_tasa > 0 else "Ventaja Inversion")
    
    if diff_tasa > 0:
        st.success(f"🏆 **Conviene PREPAGAR el credito:** El costo de tu deuda ({tasa_costo_efectivo:.2f}%) supera el rendimiento de la inversion ({tasa_inversion:.2f}%). Al abonar \\${capital_analisis:,.2f} al credito te ahorras **\\${ahorro_anual_credito:,.2f}/anio**, mientras que invirtiendolo ganarias solo **\\${ganancia_anual_inversion:,.2f}/anio**.")
    else:
        st.warning(f"📈 **Conviene INVERTIR:** La inversion rinde ({tasa_inversion:.2f}%), superando el costo del credito ({tasa_costo_efectivo:.2f}%). Al invertir \\${capital_analisis:,.2f} generas mas rendimiento de lo que te cuesta el credito.")

with tab6:
    st.subheader("🏛️ Proyeccion SRI (Intereses Deducibles)")
    sri_df = df_base.groupby('Anio')['Interes'].sum().reset_index()
    sri_df.columns = ['Anio Fiscal', 'Intereses Deducibles ($)']
    st.dataframe(sri_df.style.format({'Intereses Deducibles ($)': '${:,.2f}'}), use_container_width=True)

with tab7:
    st.subheader("📄 Reporte Ejecutivo en PDF")
    st.markdown("Descarga un informe detallado con el corte actual de amortizacion, saldos e intereses.")
    pdf_bytes = generar_pdf()
    st.download_button(
        label="📥 Descargar Estado de Cuenta (PDF)",
        data=pdf_bytes,
        file_name=f"Estado_Credito_Produbanco_GarciaCastillo_{datetime.now().strftime('%Y%m%d')}.pdf",
        mime="application/pdf"
    )
