import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
from dateutil.relativedelta import relativedelta
import plotly.express as px
import plotly.graph_objects as go
from streamlit_gsheets import GSheetsConnection

st.set_page_config(page_title="Mi Crédito Produbanco", layout="wide", page_icon="🏦")

st.title("🏦 Dashboard Hipotecario - Produbanco")
st.markdown("Monitorea tu crédito, marca tus cuotas canceladas y consérvalas en la nube.")

# --- CONEXIÓN CON GOOGLE SHEETS ---
conn = st.connection("gsheets", type=GSheetsConnection)

try:
    # Lee la hoja configurada en Secrets (ttl=0 para ver cambios inmediatos)
    df_checks = conn.read(ttl=0)
    
    # Asegurar nombres de columnas limpios
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

# Total de cuotas pagadas según la hoja
cuotas_pagadas_actual = int(df_checks["Estado_Pago"].sum())

if cuotas_pagadas_actual > 0 and cuotas_pagadas_actual <= meses:
    saldo_actual = df_base.loc[cuotas_pagadas_actual - 1, "Saldo Deudor ($)"]
    capital_ya_pagado = monto - saldo_actual
else:
    saldo_actual = monto
    capital_ya_pagado = 0.0

# --- PESTAÑAS DE NAVEGACIÓN ---
tab1, tab2, tab3, tab4 = st.tabs(["☑️ Control de Pagos", "📊 Mi Realidad Actual", "💸 Abonos Extra", "📈 SRI"])

with tab1:
    st.subheader("Registro de Cuotas Canceladas")
    st.info(f"Cuotas pagadas registradas: **{cuotas_pagadas_actual} de {meses}**")
    
    anios_credito = list(range(1, int(plazo_anios) + 1))
    anio_seleccionado = st.selectbox("Selecciona el Año del Crédito:", anios_credito)
    
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
            c3.write(f"💵 **Cuota:** ${fila['Cuota Total ($)']:,.2f}")
            c4.markdown("✅ *Pagado*" if check else "⏳ *Pendiente*")
            st.divider()
        
        boton_guardar = st.form_submit_button("💾 Guardar Cambios en Google Sheets")
        
        if boton_guardar:
            with st.spinner("Guardando en la nube..."):
                df_guardar = df_checks.copy()
                df_guardar["Estado_Pago"] = estados_modificados
                df_guardar["Estado_Pago"] = df_guardar["Estado_Pago"].apply(lambda x: "TRUE" if x else "FALSE")
                
                conn.update(data=df_guardar)
                st.cache_data.clear()
            st.success("¡Pagos actualizados y guardados con éxito!")
            st.rerun()

with tab2:
    st.subheader("Tu situación al día de hoy")
    col1, col2, col3 = st.columns(3)
    col1.metric("Saldo Deudor ACTUAL", f"${saldo_actual:,.2f}", f"Has pagado ${capital_ya_pagado:,.2f}")
    col2.metric("Cuota Mensual Fija", f"${df_base.loc[0, 'Cuota Total ($)']:,.2f}")
    col3.metric("Cuotas Restantes", f"{meses - cuotas_pagadas_actual} de {meses}")

    st.markdown("---")
    st.markdown("#### Progreso de tu propiedad")
    porcentaje_pagado = (capital_ya_pagado / monto) * 100 if monto > 0 else 0
    st.progress(min(100, int(porcentaje_pagado)))
    st.caption(f"Ya eres dueño del **{porcentaje_pagado:.1f}%** del inmueble.")

with tab3:
    st.subheader("Simulador de Abonos Extraordinarios")
    col_a, col_b, col_c = st.columns(3)
    mes_sug = min(cuotas_pagadas_actual + 1, meses)
    
    mes_abono = col_a.number_input("Mes del abono", min_value=1, max_value=meses, value=mes_sug)
    monto_abono = col_b.number_input("Monto del Abono ($)", min_value=100.0, value=5000.0, step=500.0)
    tipo_beneficio = col_c.radio("Objetivo del abono", ["Reducir Plazo", "Reducir Cuota"])
    
    if st.button("Calcular impacto del abono"):
        if mes_abono < meses:
            saldo_en_mes = df_base.loc[mes_abono-1, 'Saldo Deudor ($)']
            if monto_abono >= saldo_en_mes:
                st.success("¡Con este monto cancelas la totalidad de la deuda!")
            else:
                nuevo_saldo = saldo_en_mes - monto_abono
                meses_restantes = meses - mes_abono
                tot_int_orig = df_base['Interés ($)'].sum()
                
                if tipo_beneficio == "Reducir Cuota":
                    df_nuevo = generar_amortizacion(nuevo_saldo, meses_restantes, sistema, fecha_inicio + relativedelta(months=mes_abono))
                    nueva_cuota = df_nuevo.loc[0, 'Cuota Total ($)']
                    ahorro = tot_int_orig - (df_base.loc[:mes_abono-1, 'Interés ($)'].sum() + df_nuevo['Interés ($)'].sum())
                    st.success(f"Tu nueva cuota baja a: **${nueva_cuota:,.2f}**")
                    st.info(f"Ahorro estimado en intereses: **${ahorro:,.2f}**")
                else:
                    cuota_ref = df_base.loc[mes_abono, 'Capital ($)'] + df_base.loc[mes_abono, 'Interés ($)']
                    try:
                        n_meses = -np.log(1 - (nuevo_saldo * tasa_mes) / cuota_ref) / np.log(1 + tasa_mes)
                        n_meses = int(np.ceil(n_meses))
                        ahorrados
