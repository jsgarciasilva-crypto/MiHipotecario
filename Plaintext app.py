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
st.markdown("Monitorea tu crédito, marca tus pagos realizados y simula abonos.")

# --- BARRA LATERAL: INGRESO DE DATOS ---
with st.sidebar:
    st.header("1. Datos del Crédito")
    fecha_inicio = st.date_input("Fecha de inicio / primera cuota", datetime(2023, 1, 15)) # Fecha ejemplo
    valor_vivienda = st.number_input("Valor total de la casa ($)", value=100000.0, step=5000.0)
    monto = st.number_input("Monto Financiado ($)", value=80000.0, step=1000.0)
    tasa_anual = st.number_input("Tasa de Interés Anual (%)", value=9.5, step=0.1)
    plazo_anios = st.number_input("Plazo (Años)", value=20, step=1)
    
    st.header("2. Seguros")
    tasa_desgravamen = st.number_input("Seg. Desgravamen anual (%)", value=0.72)
    tasa_incendio = st.number_input("Seg. Incendio anual (%)", value=0.15)

    st.header("3. Sistema")
    sistema = st.selectbox("Sistema de Amortización", ["Francés (Cuota Fija)", "Alemán (Capital Fijo, Cuota Decreciente)"])
    
    # Hemos quitado el input manual de cuotas pagadas de aquí, ¡ahora es interactivo!

# --- CÁLCULOS BASE ---
meses = plazo_anios * 12
tasa_mes = tasa_anual / 12 / 100
tasa_desg_mes = tasa_desgravamen / 12 / 100
cuota_incendio = (valor_vivienda * (tasa_incendio / 100)) / 12

# Función para generar la tabla matemática pura
@st.cache_data # Mantiene los cálculos rápidos
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
            "Saldo Deudor ($)": round(max(0, saldo), 2)
        })
    return pd.DataFrame(tabla)

# Generamos la tabla base
df_base = generar_amortizacion(monto, meses, sistema, fecha_inicio)

# --- ESTADO DE SESIÓN (Memoria para los Checks) ---
# Creamos una lista en la memoria para recordar qué cuotas están marcadas como pagadas
if 'cuotas_pagadas_checks' not in st.session_state:
    # Inicializamos todos los meses en False (no pagado)
    st.session_state['cuotas_pagadas_checks'] = [False] * meses

# Calculamos cuántas cuotas están marcadas como True
cuotas_pagadas_actual = sum(st.session_state['cuotas_pagadas_checks'])

# --- OBTENER SALDO ACTUAL SEGÚN LOS CHECKS ---
if cuotas_pagadas_actual > 0 and cuotas_pagadas_actual <= meses:
    # El saldo actual es el saldo deudor del último mes que se marcó como pagado
    saldo_actual = df_base.loc[cuotas_pagadas_actual - 1, 'Saldo Deudor ($)']
    capital_ya_pagado = monto - saldo_actual
else:
    saldo_actual = monto
    capital_ya_pagado = 0


# TABS DE NAVEGACIÓN
tab1, tab2, tab3, tab4 = st.tabs(["☑️ Control de Pagos", "📊 Mi Realidad Actual", "💸 Abonos Extra", "📈 SRI"])

# --- TAB 1: CONTROL DE PAGOS INTERACTIVO (Nuevo) ---
with tab1:
    st.subheader("Control Interactivo de Cuotas")
    st.markdown("Marca la casilla 'Pagado' cada mes que realices tu pago al banco. Los datos de las otras pestañas se actualizarán automáticamente.")
    
    col_info1, col_info2 = st.columns(2)
    col_info1.info(f"Has pagado: **{cuotas_pagadas_actual} de {meses} cuotas**")
    
    # Para no mostrar las 240 filas de golpe (haría la página muy lenta en celulares),
    # mostramos de 12 en 12 usando un selector de año de crédito.
    anios_credito = list(range(1, plazo_anios + 1))
    anio_seleccionado = st.selectbox("Selecciona el Año del Crédito para ver sus cuotas:", anios_credito)
    
    # Filtrar qué meses corresponden a ese año (ej. Año 1 = Meses 1 al 12)
    mes_inicio_vista = (anio_seleccionado - 1) * 12
    mes_fin_vista = anio_seleccionado * 12
    
    # Creamos un diseño de cuadrícula para ver las cuotas de ese año
    st.markdown("---")
    
    # Mostramos las cuotas del año seleccionado
    for i in range(mes_inicio_vista, mes_fin_vista):
        if i < meses: # Seguridad por si acaso
            fila = df_base.iloc[i]
            
            # Usamos columnas para alinear el Checkbox con la info
            c1, c2, c3, c4 = st.columns([1, 2, 2, 2])
            
            with c1:
                # El Checkbox: su valor está atado a nuestra lista en session_state
                # Clave única para cada checkbox
                key_checkbox = f"check_mes_{i}"
                
                # Función que se ejecuta cuando el usuario hace click en el check
                def actualizar_check(indice=i, key=key_checkbox):
                    st.session_state['cuotas_pagadas_checks'][indice] = st.session_state[key]

                # Mostramos el checkbox
                st.checkbox(f"Mes {fila['Mes']}", 
                            value=st.session_state['cuotas_pagadas_checks'][i], 
                            key=key_checkbox,
                            on_change=actualizar_check)
            with c2:
                st.write(f"📅 **{fila['Fecha']}**")
            with c3:
                st.write(f"💵 **Cuota:** ${fila['Cuota Total ($)']:,.2f}")
            with c4:
                #
