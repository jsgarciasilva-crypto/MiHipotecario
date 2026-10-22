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

URL_HOJA = "https://docs.google.com/spreadsheets/d/1hOwRmaPU6BhM0gRl_8-yLcuOZuWC-W_iw1sk7lAwyRs/edit?usp=sharing".strip()
URL_PUENTE = "https://script.google.com/macros/s/AKfycbws0PYJdAzDLS_wnd_4DbyTlUdY40uWaoPZR2Ny3XIC7Z0g98PmT0aRR43WElYJTU4/exec".strip()

conn = st.connection("gsheets", type=GSheetsConnection)

# --- INICIALIZACIÓN PERSISTENTE DE PAGOS, ABONOS Y REAJUSTES DE TASA ---
if "datos_cargados" not in st.session_state:
    pagos = [False] * 240
    abonos_dict = {}
    reajustes_dict = {}
    try:
        df_sheet = conn.read(spreadsheet=URL_HOJA, ttl=0)
        df_sheet.columns = [str(c).strip() for c in df_sheet.columns]
        
        # 1. Cargar pagos
        if "Estado_Pago" in df_sheet.columns:
            pagos_raw = df_sheet["Estado_Pago"].astype(str).str.strip().str.upper().isin(["TRUE", "VERDADERO", "1"]).tolist()
            pagos = pagos_raw[:240]
            if len(pagos) < 240:
                pagos.extend([False] * (240 - len(pagos)))
                
        # 2. Cargar abonos históricos
        if "Abono_Extra" in df_sheet.columns and "Tipo_Abono" in df_sheet.columns:
            for idx, fila in df_sheet.iterrows():
                try:
                    val_abono = float(fila["Abono_Extra"])
                    tipo_abono = str(fila["Tipo_Abono"]).strip()
                    mes_num = int(fila["Mes"]) if "Mes" in df_sheet.columns else (idx + 1)
                    if val_abono > 0 and tipo_abono in ["Reducir Plazo", "Reducir Cuota"]:
                        abonos_dict[mes_num] = {
                            "monto": val_abono,
                            "tipo": tipo_abono
                        }
                except Exception:
                    continue
                    
        # 3. Cargar reajustes de tasa registrados
        if "Tasa_Interes" in df_sheet.columns:
            tasa_prev = None
            for idx, fila in df_sheet.iterrows():
                try:
                    m_val = int(fila["Mes"]) if "Mes" in df_sheet.columns else (idx + 1)
                    t_val = round(float(fila["Tasa_Interes"]), 2)
                    if m_val < 13:
                        tasa_prev = t_val
                    else:
                        if tasa_prev is not None and t_val != tasa_prev and t_val > 0:
                            reajustes_dict[m_val] = t_val
                            tasa_prev = t_val
                except Exception:
                    continue
    except Exception:
        pass
        
    st.session_state["pagos_lista"] = pagos[:240]
    st.session_state["abonos_guardados"] = abonos_dict
    st.session_state["reajustes_tasa"] = reajustes_dict
    st.session_state["datos_cargados"] = True

if "reajustes_tasa" not in st.session_state:
    st.session_state["reajustes_tasa"] = {}

def actualizar_check(idx):
    st.session_state["pagos_lista"][idx] = st.session_state[f"chk_{idx}"]

# --- BARRA LATERAL DINÁMICA ---
with st.sidebar:
    st.header("1. Datos del Credito")
    fecha_inicio = st.date_input("Fecha inicio / primera cuota", date(2026, 12, 1))
    valor_vivienda = st.number_input("Valor casa ($)", value=315000.0, step=5000.0)
    monto = st.number_input("Monto Financiado ($)", value=240000.0, step=1000.0)
    tasa_anual = st.number_input("Tasa Efectiva Año 1 (%)", value=6.5, step=0.1, help="Tasa fija durante el primer año (Meses 1 a 12). A partir del Mes 13 es reajustable semestralmente.")
    plazo_anios = st.number_input("Plazo Original (Anios)", value=20, step=1)
    
    st.header("2. Seguros")
    tasa_desgravamen = st.number_input("Seg. Desgravamen (%)", value=0.72, step=0.01)
    tasa_incendio = st.number_input("Seg. Incendio (%)", value=0.15, step=0.01)

    st.header("3. Sistema")
    sistema = st.selectbox("Sistema Amortizacion", ["Frances (Cuota Fija)", "Aleman (Capital Fijo)"])

# Parámetros calculados en caliente
meses_orig = int(plazo_anios * 12)
tasa_desg_mes = (tasa_desgravamen / 100.0) / 12.0
cuota_incendio = (valor_vivienda * (tasa_incendio / 100.0)) / 12.0

# Motor de amortización con soporte para tasa reajustable semestral y multi-abono
def calcular_cronograma_financiero(
    monto_val, plazo_anios_val, sistema_val, fecha_val, 
    t_anual_base, t_desg_val, t_inc_val, v_casa_val,
    diccionario_reajustes=None, diccionario_abonos=None
):
    if diccionario_reajustes is None:
        diccionario_reajustes = {}
    if diccionario_abonos is None:
        diccionario_abonos = {}
        
    plazo_m_orig = int(plazo_anios_val * 12)
    tdm = (t_desg_val / 100.0) / 12.0
    ci = (v_casa_val * (t_inc_val / 100.0)) / 12.0

    tasa_actual = t_anual_base
    tm = (tasa_actual / 100.0) / 12.0

    if "Frances" in sistema_val:
        factor = (1.0 + tm) ** plazo_m_orig
        cuota_cap_int_actual = monto_val * (tm * factor) / (factor - 1.0)
    else:
        abono_capital_fijo = monto_val / plazo_m_orig

    saldo = float(monto_val)
    tabla = []
    mes = 0
    mes_final_proyectado = plazo_m_orig

    while saldo > 0.01 and mes < 360:
        mes += 1

        # 1. Aplicación de Reajuste de Tasa Semestral si corresponde
        if mes in diccionario_reajustes:
            tasa_actual = float(diccionario_reajustes[mes])
            tm = (tasa_actual / 100.0) / 12.0
            meses_rest = max(1, mes_final_proyectado - (mes - 1))
            if "Frances" in sistema_val:
                factor_reaj = (1.0 + tm) ** meses_rest
                cuota_cap_int_actual = saldo * (tm * factor_reaj) / (factor_reaj - 1.0)
            else:
                abono_capital_fijo = saldo / meses_rest

        interes = saldo * tm
        seg_desg = saldo * tdm

        # 2. Verificación de Abono Extraordinario
        datos_abono = diccionario_abonos.get(mes, None)
        extra = float(datos_abono["monto"]) if datos_abono else 0.0
        tipo_ab = datos_abono["tipo"] if datos_abono else ""

        if "Frances" in sistema_val:
            capital_reg = cuota_cap_int_actual - interes
        else:
            capital_reg = abono_capital_fijo

        capital_total = capital_reg + extra

        if capital_total > saldo:
            capital_total = saldo
            capital_reg = max(0.0, saldo - extra)

        cuota_total = capital_total + interes + seg_desg + ci
        saldo -= capital_total
        fecha_pago = fecha_val + relativedelta(months=mes - 1)

        tabla.append({
            "Mes": mes,
            "Fecha": fecha_pago.strftime('%Y-%m'),
            "Anio": fecha_pago.year,
            "Tasa_Anual": tasa_actual,
            "Capital": round(capital_total, 2),
            "Capital_Regular": round(capital_reg, 2),
            "Abono_Extra": round(extra, 2),
            "Tipo_Abono": tipo_ab,
            "Interes": round(interes, 2),
            "Seguros": round(seg_desg + ci, 2),
            "Cuota_Total": round(cuota_total, 2),
            "Saldo": round(max(0.0, saldo), 2)
        })

        # 3. Recálculo en caso de abono extraordinario
        if extra > 0 and saldo > 0.01:
            if tipo_ab == "Reducir Cuota":
                meses_restantes = max(1, mes_final_proyectado - mes)
                if "Frances" in sistema_val:
                    factor_n = (1.0 + tm) ** meses_restantes
                    cuota_cap_int_actual = saldo * (tm * factor_n) / (factor_n - 1.0)
                else:
                    abono_capital_fijo = saldo / meses_restantes
            elif tipo_ab == "Reducir Plazo":
                if "Frances" in sistema_val:
                    try:
                        n_meses_rem = -np.log(1.0 - (saldo * tm) / cuota_cap_int_actual) / np.log(1.0 + tm)
                        n_meses_rem = int(np.ceil(n_meses_rem))
                        mes_final_proyectado = mes + n_meses_rem
                    except Exception:
                        pass
                else:
                    n_meses_rem = int(np.ceil(saldo / abono_capital_fijo))
                    mes_final_proyectado = mes + n_meses_rem

    return pd.DataFrame(tabla)

# 1. Cronograma Original de referencia sin abonos ni reajustes
df_original = calcular_cronograma_financiero(
    monto, plazo_anios, sistema, fecha_inicio,
    tasa_anual, tasa_desgravamen, tasa_incendio, valor_vivienda,
    diccionario_reajustes={}, diccionario_abonos={}
)

# 2. Cronograma Real con TODOS los abonos y reajustes aplicados
df_base = calcular_cronograma_financiero(
    monto, plazo_anios, sistema, fecha_inicio,
    tasa_anual, tasa_desgravamen, tasa_incendio, valor_vivienda,
    diccionario_reajustes=st.session_state["reajustes_tasa"],
    diccionario_abonos=st.session_state["abonos_guardados"]
)

meses_totales = len(df_base)
meses_ahorrados_totales = max(0, len(df_original) - len(df_base))
ahorro_intereses_total = max(0.0, df_original["Interes"].sum() - df_base["Interes"].sum())
total_abonado_capital = sum(v["monto"] for v in st.session_state["abonos_guardados"].values())

# Función para sincronizar Cronograma Completo (8 Columnas)
def guardar_en_nube():
    payload = []
    for _, fila in df_base.iterrows():
        m_num = int(fila["Mes"])
        esta_pag = bool(st.session_state["pagos_lista"][m_num - 1]) if (m_num - 1) < len(st.session_state["pagos_lista"]) else False
        info_ab = st.session_state["abonos_guardados"].get(m_num, None)
        ab_monto = float(info_ab["monto"]) if info_ab else 0.0
        ab_tipo = str(info_ab["tipo"]) if info_ab else ""
        
        payload.append({
            "mes": m_num,
            "fecha": str(fila["Fecha"]),
            "cuota": float(fila["Cuota_Total"]),
            "pagado": esta_pag,
            "abono": ab_monto,
            "tipo": ab_tipo,
            "saldo": float(fila["Saldo"]),
            "tasa": float(fila["Tasa_Anual"])
        })
    try:
        url_destino = URL_PUENTE.strip()
        requests.post(url_destino, json=payload, timeout=15)
        st.success("¡Datos guardados con éxito!")
    except Exception as err:
        st.error(f"Error al guardar datos: {err}")

# Cantidad de pagos actualizada al instante
cuotas_pagadas_actual = min(sum(st.session_state["pagos_lista"]), meses_totales)
cuotas_restantes = max(0, meses_totales - cuotas_pagadas_actual)
pct_cuotas_pag = (cuotas_pagadas_actual / meses_totales * 100.0) if meses_totales > 0 else 0.0
pct_cuotas_pend = max(0.0, 100.0 - pct_cuotas_pag)

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

# Próxima cuota y semáforo en tiempo real
proximo_mes_idx = min(cuotas_pagadas_actual, meses_totales - 1)
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
    
    tasa_actual_vigente = df_base.iloc[proximo_mes_idx]["Tasa_Anual"]
    pdf.cell(95, 5, f"Tasa Efectiva Vigente: {tasa_actual_vigente:.2f}% (Base: {tasa_anual:.2f}%)", ln=True)
    pdf.cell(95, 5, f"Sistema: {sistema.split(' ')[0]}")
    
    if len(st.session_state["abonos_guardados"]) > 0:
        plazo_str = f"{meses_totales} meses ({meses_totales/12:.1f} anios) [{len(st.session_state['abonos_guardados'])} abono(s) aplicados]"
    else:
        plazo_str = f"{meses_totales} meses ({plazo_anios} anios)"
    pdf.cell(95, 5, f"Plazo Vigente: {plazo_str}", ln=True)
    
    pdf.cell(95, 5, f"Fecha Primera Cuota: {fecha_inicio.strftime('%Y-%m-%d')}")
    pdf.cell(95, 5, f"Cuotas Pagadas: {cuotas_pagadas_actual} de {meses_totales}", ln=True)
    pdf.ln(4)
    
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*C_RGB_NAVY)
    pdf.cell(0, 6, "2. ESTADO ACTUAL DE LA DEUDA", ln=True)
    
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*C_RGB_TEXT)
    pdf.cell(95, 5, f"Saldo Deudor Actual: ${saldo_deudor:,.2f}")
    pdf.cell(95, 5, f"Capital Pagado: ${cap_pagado:,.2f}", ln=True)
    pdf.cell(95, 5, f"% Propiedad Cancelado: {pct_cap:.2f}%")
    pdf.cell(95, 5, f"Cuotas Pendientes: {cuotas_restantes}", ln=True)
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
        ("Cuotas (Plazo)", f"{meses_totales} cuotas", f"{cuotas_pagadas_actual} pagadas", f"{cuotas_restantes} faltantes", pct_cuotas_pag),
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
        elif rubro == "Cuotas (Plazo)":
            pdf.set_fill_color(248, 250, 252)
            pdf.set_text_color(*C_RGB_NAVY)
            pdf.set_font("Helvetica", "B", 8)
            fill_flag = True
        else:
            pdf.set_text_color(*C_RGB_TEXT)
            pdf.set_font("Helvetica", "", 8)
            fill_flag = False
            
        s_tot = f"${tot_v:,.2f}" if isinstance(tot_v, (int, float)) else str(tot_v)
        s_pag = f"${pag_v:,.2f}" if isinstance(pag_v, (int, float)) else str(pag_v)
        s_pend = f"${pend_v:,.2f}" if isinstance(pend_v, (int, float)) else str(pend_v)
        
        pdf.cell(40, 5.5, rubro, border=1, align="L", fill=fill_flag)
        pdf.cell(38, 5.5, s_tot, border=1, align="R", fill=fill_flag)
        pdf.cell(38, 5.5, s_pag, border=1, align="R", fill=fill_flag)
        pdf.cell(38, 5.5, s_pend, border=1, align="R", fill=fill_flag)
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
    "💸 Abonos a Capital",
    "❄️ Micro-Abonos (Bola de Nieve)",
    "⚖️ Prepago vs Inversion",
    "📈 SRI", 
    "📄 Reporte PDF"
])

with tab1:
    st.subheader("Registro de Cuotas Canceladas")
    
    # Módulo para Reajuste Semestral de Tasa
    with st.expander("🔄 **Reajustes Semestrales de Tasa de Interés (Año 2 en adelante)**", expanded=False):
        st.markdown("El crédito mantiene una tasa fija durante el primer año (Meses 1 a 12). A partir del Mes 13, Produbanco reajusta la tasa semestralmente.")
        
        col_rej1, col_rej2, col_rej3 = st.columns([2, 1.5, 1.5])
        opciones_semestres = {}
        for m in range(13, int(meses_orig) + 1, 6):
            f_p = fecha_inicio + relativedelta(months=m - 1)
            a_n = ((m - 1) // 12) + 1
            s_n = 1 if ((m - 1) % 12) < 6 else 2
            opciones_semestres[m] = f"Mes {m} ({f_p.strftime('%Y-%m')}) - Año {a_n}, Semestre {s_n}"
            
        semestre_sel = col_rej1.selectbox("Selecciona el Semestre / Mes a Reajustar:", list(opciones_semestres.keys()), format_func=lambda x: opciones_semestres[x], key="sel_semestre_reajuste")
        tasa_actual_semestre = st.session_state["reajustes_tasa"].get(semestre_sel, tasa_anual)
        nueva_tasa_val = col_rej2.number_input("Nueva Tasa Efectiva Anual (%)", min_value=1.0, max_value=25.0, value=float(tasa_actual_semestre), step=0.05, format="%.2f", key="input_nueva_tasa_semestre")
        
        col_rej3.write("")
        col_rej3.write("")
        if col_rej3.button("💾 Aplicar Reajuste de Tasa", key="btn_guardar_tasa_sem"):
            st.session_state["reajustes_tasa"][semestre_sel] = round(nueva_tasa_val, 2)
            guardar_en_nube()
            st.rerun()
            
        if len(st.session_state["reajustes_tasa"]) > 0:
            st.markdown("---")
            st.markdown("##### 📋 Historial de Tasas Reajustadas:")
            filas_tasas = [{"Periodo": "Año 1 (Fijo)", "Mes de Inicio": "Mes 1", "Fecha": fecha_inicio.strftime('%Y-%m'), "Tasa Efectiva Anual": f"{tasa_anual:.2f}%"}]
            for m_k in sorted(st.session_state["reajustes_tasa"].keys()):
                f_k = fecha_inicio + relativedelta(months=m_k - 1)
                a_k = ((m_k - 1) // 12) + 1
                s_k = 1 if ((m_k - 1) % 12) < 6 else 2
                filas_tasas.append({
                    "Periodo": f"Año {a_k}, Semestre {s_k}",
                    "Mes de Inicio": f"Mes {m_k}",
                    "Fecha": f_k.strftime('%Y-%m'),
                    "Tasa Efectiva Anual": f"{st.session_state['reajustes_tasa'][m_k]:.2f}%"
                })
            st.dataframe(pd.DataFrame(filas_tasas), use_container_width=True)
            
            c_del1, c_del2 = st.columns([2, 1])
            sem_del = c_del1.selectbox("Selecciona un reajuste para eliminar:", sorted(st.session_state["reajustes_tasa"].keys()), format_func=lambda x: opciones_semestres.get(x, f"Mes {x}"), key="sel_elim_tasa")
            if c_del2.button("🗑️ Eliminar Reajuste", key="btn_elim_tasa"):
                if sem_del in st.session_state["reajustes_tasa"]:
                    del st.session_state["reajustes_tasa"][sem_del]
                    guardar_en_nube()
                    st.rerun()

    if len(st.session_state["abonos_guardados"]) > 0:
        st.success(f"⚡ **Crédito Optimizado con {len(st.session_state['abonos_guardados'])} Abono(s) Activo(s):** Total abonado: **\\${total_abonado_capital:,.2f}** | Plazo actual: **{meses_totales} cuotas** ({meses_totales/12:.1f} años) | Ahorro total en intereses: **\\${ahorro_intereses_total:,.2f}**")
            
    col_t1, col_t2 = st.columns([3, 1])
    col_t1.info(f"Cuotas pagadas registradas: **{cuotas_pagadas_actual} de {meses_totales}** | Saldo Deudor: **\\${saldo_deudor:,.2f}**")
    
    if col_t2.button("💾 Guardar Cambios", key="btn_save_top"):
        with st.spinner("Guardando datos..."):
            guardar_en_nube()

    anios_max = int(np.ceil(meses_totales / 12.0))
    anios_credito = list(range(1, anios_max + 1))
    anio_seleccionado = st.selectbox("Selecciona el Anio del Credito:", anios_credito)
    mes_inicio_vista = (anio_seleccionado - 1) * 12
    mes_fin_vista = min(anio_seleccionado * 12, meses_totales)
    st.markdown("---")
    
    for i in range(mes_inicio_vista, mes_fin_vista):
        fila = df_base.iloc[i]
        c1, c2, c3, c4 = st.columns([1, 2, 2.7, 1.3])
        valor_actual = st.session_state["pagos_lista"][i]
        
        check = c1.checkbox(
            f"Mes {fila['Mes']}", 
            value=valor_actual, 
            key=f"chk_{i}", 
            on_change=actualizar_check, 
            args=(i,)
        )
        c2.write(f"📅 **{fila['Fecha']}**")
        
        if fila['Abono_Extra'] > 0:
            c3.markdown(f"💵 **Cuota:** \\${fila['Cuota_Total']:,.2f} *(\\${fila['Abono_Extra']:,.0f} Abono)* | {fila['Tasa_Anual']:.2f}%")
        elif i == meses_totales - 1 and meses_ahorrados_totales > 0:
            c3.markdown(f"💵 **Cuota Final:** \\${fila['Cuota_Total']:,.2f} 🏁 *(Liquidación)* | {fila['Tasa_Anual']:.2f}%")
        else:
            c3.write(f"💵 **Cuota:** \\${fila['Cuota_Total']:,.2f} ({fila['Tasa_Anual']:.2f}%)")
            
        c4.markdown("✅ *Pagado*" if valor_actual else "⏳ *Pendiente*")
        st.divider()
        
    if st.button("💾 Guardar Cambios", key="btn_save_bottom"):
        with st.spinner("Guardando datos..."):
            guardar_en_nube()

with tab2:
    st.subheader("Auditoria de Pagos y Porcentajes de Avance")
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Capital Amortizado", f"${cap_pagado:,.2f}", f"{pct_cap:.1f}% amortizado")
    col2.metric("Intereses Cancelados", f"${int_pagado:,.2f}", f"{pct_int:.1f}% pagado")
    col3.metric("Seguros Desembolsados", f"${seg_pagado:,.2f}", f"{pct_seg:.1f}% pagado")
    col4.metric("Desembolso General", f"${tot_desembolsado:,.2f}", f"{pct_tot:.1f}% del costo total")

    st.markdown("#### ⏳ Estado del Plazo y Cuotas")
    col_q1, col_q2 = st.columns(2)
    
    if meses_ahorrados_totales > 0:
        desc_plazo = f"{pct_cuotas_pag:.2f}% ({meses_ahorrados_totales} meses ahorrados en total)"
    else:
        desc_plazo = f"{pct_cuotas_pag:.2f}% del plazo total cumplido"
        
    col_q1.metric(
        "Cuotas Canceladas", 
        f"{cuotas_pagadas_actual} de {meses_totales} cuotas", 
        desc_plazo
    )
    col_q2.metric(
        "Cuotas Faltantes / Restantes", 
        f"{cuotas_restantes} cuotas", 
        f"{cuotas_restantes/12.0:.1f} anios pendientes ({pct_cuotas_pend:.2f}%)",
        delta_color="inverse"
    )

    st.markdown("---")
    st.markdown("#### Tabla de Distribucion Financiera")
    
    txt_proy_cuotas = f"{meses_totales} cuotas" + (f" (-{meses_ahorrados_totales} ahorradas)" if meses_ahorrados_totales > 0 else "")
    txt_proy_int = f"${int_total:,.2f}" + (f" (Ahorro: ${ahorro_intereses_total:,.2f})" if ahorro_intereses_total > 0 else "")
    
    filas_resumen = [
        {
            "Rubro": "📅 Cuotas (Plazo)", 
            "Total Proyectado": txt_proy_cuotas, 
            "Pagado a la Fecha": f"{cuotas_pagadas_actual} pagadas", 
            "% Pagado": f"{pct_cuotas_pag:.2f}%", 
            "Saldo Pendiente": f"{cuotas_restantes} faltantes", 
            "% Pendiente": f"{pct_cuotas_pend:.2f}%"
        },
        {
            "Rubro": "💵 Capital", 
            "Total Proyectado": f"${cap_total:,.2f}", 
            "Pagado a la Fecha": f"${cap_pagado:,.2f}", 
            "% Pagado": f"{pct_cap:.2f}%", 
            "Saldo Pendiente": f"${saldo_deudor:,.2f}", 
            "% Pendiente": f"{100-pct_cap:.2f}%"
        },
        {
            "Rubro": "📈 Intereses", 
            "Total Proyectado": txt_proy_int, 
            "Pagado a la Fecha": f"${int_pagado:,.2f}", 
            "% Pagado": f"{pct_int:.2f}%", 
            "Saldo Pendiente": f"${int_pendiente:,.2f}", 
            "% Pendiente": f"{100-pct_int:.2f}%"
        },
        {
            "Rubro": "🛡️ Seguros", 
            "Total Proyectado": f"${seg_total:,.2f}", 
            "Pagado a la Fecha": f"${seg_pagado:,.2f}", 
            "% Pagado": f"{pct_seg:.2f}%", 
            "Saldo Pendiente": f"${seg_pendiente:,.2f}", 
            "% Pendiente": f"{100-pct_seg:.2f}%"
        },
        {
            "Rubro": "🏛️ Total General", 
            "Total Proyectado": f"${costo_total_credito:,.2f}", 
            "Pagado a la Fecha": f"${tot_desembolsado:,.2f}", 
            "% Pagado": f"{pct_tot:.2f}%", 
            "Saldo Pendiente": f"${costo_pendiente:,.2f}", 
            "% Pendiente": f"{100-pct_tot:.2f}%"
        }
    ]
    tabla_resumen = pd.DataFrame(filas_resumen)
    st.dataframe(tabla_resumen, use_container_width=True)
    
    st.markdown("---")
    st.markdown("#### Progreso de Titularidad del Inmueble")
    st.progress(min(100, int(pct_cap)))
    st.caption(f"Tienes libre de hipoteca el **{pct_cap:.2f}%** del valor original financiado.")

    st.markdown("---")
    st.markdown("#### Curva de Amortizacion: Descenso de Saldo Deudor")
    
    fig_saldo = go.Figure()
    
    if len(st.session_state["abonos_guardados"]) > 0 or len(st.session_state["reajustes_tasa"]) > 0:
        fig_saldo.add_trace(go.Scatter(
            x=df_original["Mes"],
            y=df_original["Saldo"],
            mode="lines",
            name="Trayectoria Original (Tasa Fija Sin Abonos)",
            line=dict(color="#A0AEC0", dash="dash")
        ))
        
    fig_saldo.add_trace(go.Scatter(
        x=df_base["Mes"],
        y=df_base["Saldo"],
        mode="lines",
        name="Saldo Dinámico (Abonos + Tasas)",
        fill="tozeroy",
        line=dict(color=COLOR_NAVY, width=2.5)
    ))
    
    if cuotas_pagadas_actual > 0:
        fig_saldo.add_vline(x=cuotas_pagadas_actual, line_dash="dash", line_color=COLOR_GOLD, annotation_text="Punto Actual")
        
    fig_saldo.update_layout(
        title="Evolución del Saldo Deudor en el Tiempo",
        xaxis_title="Número de Mes",
        yaxis_title="Saldo Deudor ($)",
        plot_bgcolor="#FFFFFF",
        paper_bgcolor="#FFFFFF",
        font=dict(color=COLOR_NAVY)
    )
    st.plotly_chart(fig_saldo, use_container_width=True)

with tab3:
    st.subheader("💸 Gestión de Abonos Extraordinarios a Capital")
    
    subtab_sim, subtab_real = st.tabs([
        "🧪 1. Simulador de Escenarios (Sin alterar el crédito)", 
        "🏛️ 2. Abonos Reales Aplicados (Historial)"
    ])
    
    # --- SUBTAB 1: SIMULADOR HIPOTÉTICO ---
    with subtab_sim:
        st.markdown("#### 🧪 Proyección y Simulación Hipotética")
        st.caption("Prueba libremente diferentes montos y plazos para conocer el impacto y el ahorro estimado. Lo que pruebes aquí **NO** alterará tu crédito real a menos que decidas aplicarlo.")
        
        col_s1, col_s2, col_s3 = st.columns(3)
        mes_sug_sim = min(cuotas_pagadas_actual + 1, meses_totales)
        sim_mes = col_s1.number_input("Mes del abono hipotético", min_value=1, max_value=meses_orig, value=mes_sug_sim, step=1, key="sim_input_mes")
        sim_monto = col_s2.number_input("Monto a simular ($)", min_value=100.0, value=30000.0, step=1000.0, key="sim_input_monto")
        sim_tipo = col_s3.radio("Objetivo del abono", ["Reducir Plazo", "Reducir Cuota"], key="sim_input_tipo")
        
        dict_temp = dict(st.session_state["abonos_guardados"])
        dict_temp[int(sim_mes)] = {"monto": float(sim_monto), "tipo": sim_tipo}
        
        df_simulacion = calcular_cronograma_financiero(
            monto, plazo_anios, sistema, fecha_inicio,
            tasa_anual, tasa_desgravamen, tasa_incendio, valor_vivienda,
            diccionario_reajustes=st.session_state["reajustes_tasa"],
            diccionario_abonos=dict_temp
        )
        
        meses_ahorrados_sim = max(0, len(df_base) - len(df_simulacion))
        ahorro_int_sim = max(0.0, df_base["Interes"].sum() - df_simulacion["Interes"].sum())
        
        st.markdown("---")
        st.markdown("##### 📊 Resultado de la Simulación:")
        
        if sim_tipo == "Reducir Plazo":
            st.success(f"🎉 **Terminarías de pagar {meses_ahorrados_sim} meses antes** (equivale a {meses_ahorrados_sim/12:.1f} años menos de deuda).")
            st.info(f"💰 **Ahorro adicional estimado en intereses:** \\${ahorro_int_sim:,.2f}")
        else:
            mes_cuota_nueva = min(int(sim_mes + 1), len(df_simulacion))
            cuota_nueva_val = df_simulacion.loc[df_simulacion['Mes'] == mes_cuota_nueva, 'Cuota_Total'].values[0]
            cuota_actual_val = df_base.loc[df_base['Mes'] == min(int(sim_mes + 1), len(df_base)), 'Cuota_Total'].values[0]
            alivio_mensual = max(0.0, cuota_actual_val - cuota_nueva_val)
            
            st.success(f"🎉 **Tu nueva cuota bajaría a: \\${cuota_nueva_val:,.2f}** a partir del Mes {sim_mes + 1} (te liberas de \\${alivio_mensual:,.2f} cada mes).")
            st.info(f"💰 **Ahorro adicional estimado en intereses:** \\${ahorro_int_sim:,.2f}")
            
        st.markdown("---")
        if st.button("📥 ¿Te gustó este escenario? Aplicar esta simulación como Abono Real al Crédito", key="btn_promover_sim"):
            st.session_state["abonos_guardados"][int(sim_mes)] = {
                "monto": float(sim_monto),
                "tipo": sim_tipo
            }
            guardar_en_nube()
            st.rerun()

    # --- SUBTAB 2: ABONOS REALES Y BITÁCORA ---
    with subtab_real:
        st.markdown("#### 🏛️ Bitácora y Registro de Abonos Reales")
        st.caption("Abonos confirmados que impactan permanentemente todo el dashboard y quedan guardados.")
        
        with st.expander("➕ **Registrar Nuevo Abono Real Directo**", expanded=False):
            col_reg1, col_reg2, col_reg3, col_reg4 = st.columns([1.5, 2, 2, 1.5])
            
            mes_sug = min(cuotas_pagadas_actual + 1, meses_orig)
            nuevo_mes = col_reg1.number_input("Mes de aplicación", min_value=1, max_value=meses_orig, value=mes_sug, step=1, key="real_nuevo_mes")
            nuevo_monto = col_reg2.number_input("Monto del Abono ($)", min_value=100.0, value=10000.0, step=1000.0, key="real_nuevo_monto")
            nuevo_tipo = col_reg3.selectbox("Objetivo del abono", ["Reducir Plazo", "Reducir Cuota"], key="real_nuevo_tipo")
            
            fecha_proyectada = fecha_inicio + relativedelta(months=int(nuevo_mes - 1))
            col_reg4.write(f"📅 Fecha: **{fecha_proyectada.strftime('%Y-%m')}**")
            
            if st.button("➕ Confirmar y Guardar Abono Real", key="btn_agregar_abono_real"):
                st.session_state["abonos_guardados"][int(nuevo_mes)] = {
                    "monto": float(nuevo_monto),
                    "tipo": nuevo_tipo
                }
                guardar_en_nube()
                st.rerun()

        st.markdown("##### 📜 Histórico de Abonos Aplicados:")
        if len(st.session_state["abonos_guardados"]) == 0:
            st.info("ℹ️ No hay abonos extraordinarios reales registrados actualmente.")
        else:
            lista_abonos_mostrar = []
            for mes_k in sorted(st.session_state["abonos_guardados"].keys()):
                datos_k = st.session_state["abonos_guardados"][mes_k]
                f_k = fecha_inicio + relativedelta(months=mes_k - 1)
                lista_abonos_mostrar.append({
                    "Mes": mes_k,
                    "Fecha Cuota": f_k.strftime('%Y-%m'),
                    "Monto Abonado": f"${datos_k['monto']:,.2f}",
                    "Objetivo": datos_k['tipo']
                })
                
            df_abonos_tabla = pd.DataFrame(lista_abonos_mostrar)
            st.dataframe(df_abonos_tabla, use_container_width=True)
            
            col_elim1, col_elim2 = st.columns([2, 2])
            mes_a_eliminar = col_elim1.selectbox("Selecciona un mes para eliminar su abono:", sorted(st.session_state["abonos_guardados"].keys()))
            if col_elim2.button("🗑️ Eliminar Abono Seleccionado"):
                if mes_a_eliminar in st.session_state["abonos_guardados"]:
                    del st.session_state["abonos_guardados"][mes_a_eliminar]
                    guardar_en_nube()
                    st.rerun()
                    
            st.markdown("---")
            st.markdown("##### 🎯 Impacto Real Consolidado en tu Crédito")
            res1, res2, res3 = st.columns(3)
            res1.metric("Capital Extra Total Abonado", f"${total_abonado_capital:,.2f}")
            res2.metric("Ahorro Acumulado en Intereses", f"${ahorro_intereses_total:,.2f}")
            res3.metric("Plazo Total Reducido", f"{meses_ahorrados_totales} meses ahorrados", f"{meses_ahorrados_totales/12.0:.1f} años menos")

with tab4:
    st.subheader("❄️ Simulador de Micro-Abonos Mensuales (Efecto Bola de Nieve)")
    st.markdown("¿Que pasa si sumas una cantidad fija a capital cada mes ademas de tu cuota normal?")
    
    col_sn1, col_sn2 = st.columns(2)
    micro_abono = col_sn1.slider("Abono extra mensual a capital ($)", min_value=25, max_value=1000, value=100, step=25)
    mes_inicio_snowball = col_sn2.number_input("Iniciar micro-abonos desde el mes:", min_value=cuotas_pagadas_actual + 1, max_value=meses_totales, value=cuotas_pagadas_actual + 1)
    
    saldo_snow = saldo_deudor
    meses_transcurridos = cuotas_pagadas_actual
    tot_int_snow = int_pagado
    
    factor_ref = (1 + (tasa_anual/1200)) ** meses_orig
    cuota_fija_cap_int = monto * ((tasa_anual/1200) * factor_ref) / (factor_ref - 1)
    
    mes_actual_sim = meses_transcurridos
    while saldo_snow > 0.01 and mes_actual_sim < 360:
        mes_actual_sim += 1
        tasa_mes_sim = (df_base.loc[df_base['Mes']==min(mes_actual_sim, len(df_base)), 'Tasa_Anual'].values[0] / 1200) if mes_actual_sim <= len(df_base) else (tasa_anual/1200)
        interes_mes = saldo_snow * tasa_mes_sim
        tot_int_snow += interes_mes
        
        capital_regular = cuota_fija_cap_int - interes_mes
        abono_aplicable = micro_abono if mes_actual_sim >= mes_inicio_snowball else 0.0
        
        capital_total_mes = min(saldo_snow, capital_regular + abono_aplicable)
        saldo_snow -= capital_total_mes
    
    meses_ahorrados_snow = max(0, meses_totales - mes_actual_sim)
    anios_ahorrados_snow = meses_ahorrados_snow / 12.0
    ahorro_interes_snow = max(0.0, int_total - tot_int_snow)
    
    cs1, cs2, cs3 = st.columns(3)
    cs1.metric("Tiempo Ahorrado", f"{meses_ahorrados_snow} meses", f"{anios_ahorrados_snow:.1f} anios antes")
    cs2.metric("Ahorro Total en Intereses", f"${ahorro_interes_snow:,.2f}")
    cs3.metric("Nuevo Mes Final", f"Mes {mes_actual_sim} de {meses_totales}")
    
    st.info(f"💡 Al aportar **\\${micro_abono:,.2f} extra cada mes**, cancelas tu deuda en **{mes_actual_sim - cuotas_pagadas_actual} meses mas** en lugar de {cuotas_restantes} meses restantes.")

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
