import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
from dateutil.relativedelta import relativedelta
import plotly.express as px
import plotly.graph_objects as go
import numpy_financial as npf

# Configuración de página adaptable a PC y Celular
st.set_page_config(page_title="Mi Crédito Produbanco", layout="wide", page_icon="🏦")

st.title("🏦 Dashboard Hipotecario - Produbanco")
st.markdown("Monitorea tu crédito, simula abonos extraordinarios, compara sistemas de amortización y obtén tu proyección para el SRI.")

# --- BARRA LATERAL: INGRESO DE DATOS ---
with st.sidebar:
    st.header("1. Datos del Crédito")
    fecha_inicio = st.date_input("Fecha de desembolso / inicio", datetime.today())
    valor_vivienda = st.number_input("Valor total de la casa ($)", value=100000.0, step=5000.0)
    monto = st.number_input("Monto Financiado ($)", value=80000.0, step=1000.0)
    tasa_anual = st.number_input("Tasa de Interés Anual (%)", value=9.5, step=0.1)
    plazo_anios = st.number_input("Plazo (Años)", value=20, step=1)
    
    st.header("2. Seguros y Gastos")
    st.info("Valores referenciales usuales en Produbanco")
    tasa_desgravamen = st.number_input("Seg. Desgravamen anual (%)", value=0.72, help="Se cobra sobre el saldo deudor")
    tasa_incendio = st.number_input("Seg. Incendio anual (%)", value=0.15, help="Se cobra sobre el avalúo")
    gastos_iniciales = st.number_input("Gastos de Cierre ($)", value=1500.0, help="Avalúo, Notaría, Registro")

    st.header("3. Opciones de Análisis")
    sistema = st.selectbox("Sistema de Amortización", ["Francés (Cuota Fija)", "Alemán (Capital Fijo, Cuota Decreciente)"])

# --- CÁLCULOS BASE ---
meses = plazo_anios * 12
tasa_mes = tasa_anual / 12 / 100
tasa_desg_mes = tasa_desgravamen / 12 / 100
cuota_incendio = (valor_vivienda * (tasa_incendio / 100)) / 12

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
        fecha_pago = fecha_arranque + relativedelta(months=mes)
        
        tabla.append({
            "Mes": mes,
            "Fecha": fecha_pago.strftime('%Y-%m'),
            "Año Calendario": fecha_pago.year,
            "Capital ($)": round(capital, 2),
            "Interés ($)": round(interes, 2),
            "Seguros ($)": round(seg_desg + cuota_incendio, 2),
            "Cuota Total ($)": round(cuota_total, 2),
            "Saldo Deudor ($)": round(max(0, saldo), 2)
        })
    return pd.DataFrame(tabla)

df_base = generar_amortizacion(monto, meses, sistema, fecha_inicio)

# TABS DE NAVEGACIÓN
tab1, tab2, tab3, tab4 = st.tabs(["📊 Resumen y Gráficos", "💸 Abonos Extraordinarios", "📈 Control y SRI", "📋 Tabla Completa"])

with tab1:
    st.subheader(f"Resumen del Crédito - Sistema {sistema.split(' ')[0]}")
    
    col1, col2, col3, col4 = st.columns(4)
    cuota_inicial = df_base.loc[0, 'Cuota Total ($)']
    cuota_final = df_base.loc[meses-1, 'Cuota Total ($)']
    total_intereses = df_base['Interés ($)'].sum()
    
    # Cálculo de la Tasa Anual Efectiva (TAE) incluyendo gastos de cierre
    flujos = [-monto + gastos_iniciales] + df_base['Cuota Total ($)'].tolist()
    tae_mensual = npf.irr(flujos)
    tae_anual = ((1 + tae_mensual)**12 - 1) * 100

    col1.metric("Cuota Mensual (1er Mes)", f"${cuota_inicial:,.2f}")
    if "Alemán" in sistema:
        col2.metric("Cuota Mensual (Último Mes)", f"${cuota_final:,.2f}")
    else:
        col2.metric("Plazo", f"{plazo_anios} años")
    col3.metric("Total Intereses a Pagar", f"${total_intereses:,.2f}")
    col4.metric("TAE (Costo Real con Gastos)", f"{tae_anual:.2f}%", help="Incluye seguros y gastos de notaría/registro")

    st.markdown("---")
    c1, c2 = st.columns([2, 1])
    with c1:
        fig_evol = go.Figure()
        fig_evol.add_trace(go.Scatter(x=df_base['Fecha'], y=df_base['Saldo Deudor ($)'], name="Saldo Deudor", fill='tozeroy', line_color='#005a9c'))
        fig_evol.update_layout(title="Evolución del Saldo Deudor a lo largo de los años")
        st.plotly_chart(fig_evol, use_container_width=True)
    with c2:
        fig_pie = px.pie(values=[monto, total_intereses, df_base['Seguros ($)'].sum()], 
                         names=['Capital Financiado', 'Intereses Totales', 'Seguros Totales'],
                         title="¿Qué estás pagando realmente?", color_discrete_sequence=['#2ca02c', '#d62728', '#ff7f0e'])
        st.plotly_chart(fig_pie, use_container_width=True)

with tab2:
    st.subheader("Simulador de Abonos Extraordinarios a Capital")
    st.markdown("Descubre cuánto te ahorras si inyectas dinero extra (ej. utilidades o décimos).")
    
    col_a, col_b, col_c = st.columns(3)
    mes_abono = col_a.number_input("¿En qué mes harás el abono?", min_value=1, max_value=meses-1, value=12)
    monto_abono = col_b.number_input("Monto del Abono ($)", min_value=100.0, value=5000.0, step=1000.0)
    tipo_beneficio = col_c.radio("¿Qué deseas hacer?", ["Reducir Plazo (Terminar antes)", "Reducir Cuota (Aliviar el mes)"])
    
    if st.button("Simular Abono"):
        saldo_en_mes = df_base.loc[mes_abono-1, 'Saldo Deudor ($)']
        nuevo_saldo = saldo_en_mes - monto_abono
        meses_restantes = meses - mes_abono
        
        if "Reducir Cuota" in tipo_beneficio:
            df_nuevo = generar_amortizacion(nuevo_saldo, meses_restantes, sistema, fecha_inicio + relativedelta(months=mes_abono))
            nueva_cuota = df_nuevo.loc[0, 'Cuota Total ($)']
            ahorro_int = total_intereses - (df_base.loc[:mes_abono-1, 'Interés ($)'].sum() + df_nuevo['Interés ($)'].sum())
            st.success(f"✅ ¡Tu cuota mensual bajará a **${nueva_cuota:,.2f}** desde el mes {mes_abono+1}!")
            st.info(f"💰 Ahorro total en intereses: **${ahorro_int:,.2f}**")
            
        else: # Reducir Plazo (Aproximación para sistema Francés)
            if "Francés" in sistema:
                cuota_actual_cap_int = df_base.loc[mes_abono, 'Capital ($)'] + df_base.loc[mes_abono, 'Interés ($)']
                # Recalcular n usando logaritmos: n = -log(1 - (P*i)/A) / log(1+i)
                try:
                    nuevos_meses = -np.log(1 - (nuevo_saldo * tasa_mes) / cuota_actual_cap_int) / np.log(1 + tasa_mes)
                    nuevos_meses = int(np.ceil(nuevos_meses))
                    meses_ahorrados = meses_restantes - nuevos_meses
                    
                    df_nuevo = generar_amortizacion(nuevo_saldo, nuevos_meses, sistema, fecha_inicio + relativedelta(months=mes_abono))
                    ahorro_int = total_intereses - (df_base.loc[:mes_abono-1, 'Interés ($)'].sum() + df_nuevo['Interés ($)'].sum())
                    
                    st.success(f"✅ ¡Terminarás de pagar el crédito **{meses_ahorrados} meses antes** ({meses_ahorrados//12} años y {meses_ahorrados%12} meses)!")
                    st.info(f"💰 Ahorro total en intereses: **${ahorro_int:,.2f}**")
                except:
                    st.error("El abono es demasiado grande para calcular el nuevo plazo. ¡Prácticamente liquidas la deuda!")
            else:
                st.warning("En el sistema Alemán, los abonos a capital generalmente reducen la cuota automáticamente por su naturaleza. El cálculo de reducción estricta de plazo requiere acuerdo directo con el banco.")

with tab3:
    st.subheader("🏛️ Proyección SRI (Deducibilidad de Gastos Personales)")
    st.markdown("En Ecuador, los intereses del crédito hipotecario (para una sola vivienda principal) son deducibles del Impuesto a la Renta.")
    
    sri_df = df_base.groupby('Año Calendario')['Interés ($)'].sum().reset_index()
    sri_df.columns = ['Año Fiscal', 'Intereses Deducibles ($)']
    st.dataframe(sri_df.style.format({'Intereses Deducibles ($)': '${:,.2f}'}), use_container_width=True)
    
    st.markdown("---")
    st.subheader("⚠️ Calculadora de Mora (Atrasos)")
    st.markdown("Calcula cuánto pagarás de penalización si te atrasas, basado en el tarifario estándar.")
    c_m1, c_m2, c_m3 = st.columns(3)
    cuota_vencida = c_m1.number_input("Monto de Cuota Vencida ($)", value=float(cuota_inicial))
    dias_atraso = c_m2.number_input("Días de Atraso", min_value=1, value=5)
    tasa_mora = c_m3.number_input("Tasa de Mora Anual (%)", value=10.5, help="La tasa máxima convencional fijada por el BCE")
    
    # Formula estándar de mora en Ecuador: Cuota Vencida * Tasa Mora * (Días / 360)
    interes_mora = cuota_vencida * (tasa_mora / 100) * (dias_atraso / 360)
    st.error(f"Por {dias_atraso} días de atraso, el banco te cobrará un recargo por mora estimado de: **${interes_mora:,.2f}** (además de los gastos de cobranza si superas los 15 días).")

with tab4:
    st.subheader("Tabla de Amortización Completa")
    st.dataframe(df_base.style.format({
        'Capital ($)': '${:,.2f}',
        'Interés ($)': '${:,.2f}',
        'Seguros ($)': '${:,.2f}',
        'Cuota Total ($)': '${:,.2f}',
        'Saldo Deudor ($)': '${:,.2f}'
    }), use_container_width=True, hide_index=True)
