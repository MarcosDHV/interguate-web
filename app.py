import streamlit as st
import pymssql
from decimal import Decimal, InvalidOperation
from datetime import date, datetime

st.set_page_config(page_title="InterGuate | Agencia de Viajes", page_icon="✈️", layout="wide")

TABLAS = {
    "Paquetes": "Paquete",
    "Clientes": "Cliente",
    "Destinos": "Destino",
    "Paises": "Pais",
    "Promociones": "Promocion",
    "Reservaciones": "Reservacion",
    "Pagos": "Pago",
    "Cancelaciones": "Cancelacion",
    "Agentes de viaje": "AgenteViaje",
    "Sucursales": "Sucursal",
    "Metodos de pago": "MetodoPago",
}

PERMISOS = {
    "RolAdministrador": list(TABLAS.keys()),
    "RolAgenteViaje": ["Reservaciones", "Cancelaciones"],
    "RolCajero_Agencia": ["Reservaciones", "Pagos"],
    "RolClienteAgencia": ["Paquetes", "Reservaciones", "Pagos"],
}


def config_db():
    try:
        return st.secrets["database"]
    except Exception:
        st.error("Falta configurar la conexión. Revisa los pasos del archivo LEEME.txt y agrega los datos en Secrets.")
        st.stop()


def conectar(usuario, clave):
    cfg = config_db()
    return pymssql.connect(
        server=str(cfg["server"]),
        port=str(cfg.get("port", 1433)),
        user=usuario,
        password=clave,
        database=str(cfg.get("name", "AgenciaViajesInterGuate")),
        login_timeout=8,
        timeout=20,
        charset="UTF-8",
    )


def ejecutar_consulta(usuario, clave, sql, parametros=(), traer=True):
    conexion = conectar(usuario, clave)
    try:
        cursor = conexion.cursor(as_dict=True)
        cursor.execute(sql, parametros)
        resultado = cursor.fetchall() if traer else None
        if not traer:
            conexion.commit()
        return resultado
    finally:
        conexion.close()


def obtener_rol(usuario, clave):
    filas = ejecutar_consulta(usuario, clave, """
        SELECT CASE
            WHEN IS_MEMBER('RolAdministrador') = 1 THEN 'RolAdministrador'
            WHEN IS_MEMBER('RolAgenteViaje') = 1 THEN 'RolAgenteViaje'
            WHEN IS_MEMBER('RolCajero_Agencia') = 1 THEN 'RolCajero_Agencia'
            WHEN IS_MEMBER('RolClienteAgencia') = 1 THEN 'RolClienteAgencia'
            ELSE NULL
        END AS rol
    """)
    return filas[0]["rol"] if filas else None


def obtener_columnas(usuario, clave, tabla):
    filas = ejecutar_consulta(usuario, clave, """
        SELECT COLUMN_NAME AS nombre, DATA_TYPE AS tipo,
               IS_NULLABLE AS nullable,
               COLUMNPROPERTY(OBJECT_ID('dbo.' + %s), COLUMN_NAME, 'IsIdentity') AS identidad
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME=%s
        ORDER BY ORDINAL_POSITION
    """, (tabla, tabla))
    pk = ejecutar_consulta(usuario, clave, """
        SELECT COLUMN_NAME AS nombre
        FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
        WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME=%s
          AND CONSTRAINT_NAME IN (
            SELECT CONSTRAINT_NAME FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
            WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME=%s AND CONSTRAINT_TYPE='PRIMARY KEY'
          )
        ORDER BY ORDINAL_POSITION
    """, (tabla, tabla))
    return filas, [x["nombre"] for x in pk]


def formatear(valor):
    if valor is None:
        return ""
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()[:10]
    return str(valor)


def campo_formulario(col, valor=None, modo="editar"):
    nombre = col["nombre"]
    tipo = col["tipo"].lower()
    valor_txt = formatear(valor)
    etiqueta = f"{nombre} ({tipo})"
    if tipo == "bit":
        actual = bool(valor) if valor is not None else False
        return st.checkbox(etiqueta, value=actual, key=f"{modo}_{nombre}")
    if tipo in ("date", "datetime", "datetime2", "smalldatetime"):
        try:
            fecha = valor.date() if isinstance(valor, datetime) else valor
            if isinstance(fecha, str):
                fecha = date.fromisoformat(fecha[:10])
            if not isinstance(fecha, date):
                fecha = date.today()
        except Exception:
            fecha = date.today()
        return st.date_input(etiqueta, value=fecha, key=f"{modo}_{nombre}")
    return st.text_input(etiqueta, value=valor_txt, key=f"{modo}_{nombre}")


def convertir_valor(valor, tipo):
    tipo = tipo.lower()
    if isinstance(valor, bool) or isinstance(valor, date):
        return valor
    if valor is None:
        return None
    valor = str(valor).strip()
    if valor == "":
        return None
    if tipo in ("int", "bigint", "smallint", "tinyint"):
        return int(valor)
    if tipo in ("decimal", "numeric", "money", "smallmoney", "float", "real"):
        return Decimal(valor)
    if tipo == "bit":
        return bool(valor)
    return valor


def cargar_registros(usuario, clave, tabla):
    return ejecutar_consulta(usuario, clave, f"SELECT TOP 200 * FROM dbo.[{tabla}] ORDER BY (SELECT NULL)")


def formulario_admin(usuario, clave, nombre_visible, tabla, columnas, pk):
    with st.expander("Agregar registro", expanded=False):
        with st.form(f"agregar_{tabla}"):
            valores = {}
            for col in columnas:
                if col["identidad"] == 1 or col["nombre"] in pk:
                    continue
                valores[col["nombre"]] = campo_formulario(col, None, f"add_{tabla}")
            enviado = st.form_submit_button("Guardar registro")
        if enviado:
            try:
                campos = []
                parametros = []
                for col in columnas:
                    nombre = col["nombre"]
                    if nombre not in valores:
                        continue
                    valor = valores[nombre]
                    if isinstance(valor, str) and valor.strip() == "":
                        continue
                    if valor is None:
                        continue
                    campos.append(f"[{nombre}]")
                    parametros.append(convertir_valor(valor, col["tipo"]))
                if not campos:
                    st.warning("Ingresa al menos un dato.")
                else:
                    placeholders = ", ".join(["%s"] * len(parametros))
                    sql = f"INSERT INTO dbo.[{tabla}] ({', '.join(campos)}) VALUES ({placeholders})"
                    ejecutar_consulta(usuario, clave, sql, tuple(parametros), traer=False)
                    st.success("Registro agregado correctamente.")
                    st.rerun()
            except Exception as e:
                st.error(f"No se pudo agregar el registro: {e}")

    if not pk:
        st.info("Esta tabla no tiene una clave primaria detectada; por seguridad no se habilita edición ni eliminación.")
        return

    try:
        registros = cargar_registros(usuario, clave, tabla)
    except Exception:
        return
    if not registros:
        st.caption("No hay registros para editar o eliminar.")
        return

    opciones = []
    por_clave = {}
    for reg in registros:
        clave_valores = tuple(reg.get(k) for k in pk)
        texto = " | ".join(f"{k}: {formatear(reg.get(k))}" for k in pk)
        opciones.append(texto)
        por_clave[texto] = reg

    seleccionado = st.selectbox("Selecciona un registro", opciones, key=f"seleccion_{tabla}")
    reg = por_clave[seleccionado]
    with st.expander("Editar registro", expanded=False):
        with st.form(f"editar_{tabla}"):
            valores = {}
            for col in columnas:
                nombre = col["nombre"]
                if nombre in pk or col["identidad"] == 1:
                    st.text_input(nombre, value=formatear(reg.get(nombre)), disabled=True, key=f"edid_{tabla}_{nombre}")
                else:
                    valores[nombre] = campo_formulario(col, reg.get(nombre), f"edit_{tabla}")
            enviado = st.form_submit_button("Guardar cambios")
        if enviado:
            try:
                asignaciones = []
                parametros = []
                for col in columnas:
                    nombre = col["nombre"]
                    if nombre not in valores:
                        continue
                    asignaciones.append(f"[{nombre}] = %s")
                    parametros.append(convertir_valor(valores[nombre], col["tipo"]))
                if not asignaciones:
                    st.warning("No hay campos para actualizar.")
                else:
                    where = " AND ".join(f"[{k}] = %s" for k in pk)
                    parametros.extend(reg.get(k) for k in pk)
                    sql = f"UPDATE dbo.[{tabla}] SET {', '.join(asignaciones)} WHERE {where}"
                    ejecutar_consulta(usuario, clave, sql, tuple(parametros), traer=False)
                    st.success("Registro actualizado correctamente.")
                    st.rerun()
            except Exception as e:
                st.error(f"No se pudo actualizar el registro: {e}")

    with st.expander("Eliminar registro", expanded=False):
        st.warning("Esta acción no se puede deshacer. SQL Server puede impedirla si existen registros relacionados.")
        confirmar = st.checkbox("Confirmo que deseo eliminar este registro", key=f"confirmar_{tabla}")
        if st.button("Eliminar registro seleccionado", key=f"borrar_{tabla}", type="primary", disabled=not confirmar):
            try:
                where = " AND ".join(f"[{k}] = %s" for k in pk)
                parametros = tuple(reg.get(k) for k in pk)
                ejecutar_consulta(usuario, clave, f"DELETE FROM dbo.[{tabla}] WHERE {where}", parametros, traer=False)
                st.success("Registro eliminado correctamente.")
                st.rerun()
            except Exception as e:
                st.error(f"No se pudo eliminar el registro: {e}")


def pantalla_login():
    st.markdown("<h1 style='text-align:center;color:#1f3b57'>INTERGUATE</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align:center'>Sistema de Agencia de Viajes</p>", unsafe_allow_html=True)
    _, centro, _ = st.columns([1, 1.2, 1])
    with centro:
        with st.form("login"):
            usuario = st.text_input("Usuario SQL Server")
            clave = st.text_input("Contraseña", type="password")
            entrar = st.form_submit_button("Iniciar sesión", use_container_width=True)
        if entrar:
            if not usuario.strip() or not clave:
                st.warning("Ingresa el usuario y la contraseña.")
            else:
                try:
                    rol = obtener_rol(usuario.strip(), clave)
                    if not rol or rol not in PERMISOS:
                        st.error("El usuario no pertenece a un rol autorizado para InterGuate.")
                    else:
                        st.session_state.usuario = usuario.strip()
                        st.session_state.clave = clave
                        st.session_state.rol = rol
                        st.rerun()
                except Exception as e:
                    st.error("No se pudo conectar con SQL Server. Verifica el servidor, las credenciales y los permisos.")
                    st.caption(str(e))


def main():
    st.title("✈️ InterGuate")
    st.caption("Sistema de administración de una agencia de viajes")
    if "usuario" not in st.session_state or "clave" not in st.session_state or "rol" not in st.session_state:
        pantalla_login()
        return

    usuario = st.session_state.usuario
    clave = st.session_state.clave
    rol = st.session_state.rol
    with st.sidebar:
        st.subheader("InterGuate")
        st.write(f"**Usuario:** {usuario}")
        st.write(f"**Rol:** {rol}")
        if st.button("Cerrar sesión", use_container_width=True):
            for k in ("usuario", "clave", "rol", "tabla"):
                st.session_state.pop(k, None)
            st.rerun()
        st.divider()
        opciones = ["Inicio"] + PERMISOS[rol]
        seleccion = st.radio("Menú", opciones)

    if seleccion == "Inicio":
        st.subheader("Bienvenido a InterGuate")
        st.write("Selecciona un módulo del menú lateral para consultar la información disponible según tu rol.")
        st.info("La aplicación web utiliza tu usuario de SQL Server. Los permisos finales dependen de los roles configurados en la base de datos.")
        c1, c2 = st.columns(2)
        c1.metric("Módulos disponibles", len(PERMISOS[rol]))
        c2.write("**Módulos:**")
        c2.write(", ".join(PERMISOS[rol]))
        return

    tabla = TABLAS[seleccion]
    st.subheader(seleccion)
    try:
        columnas, pk = obtener_columnas(usuario, clave, tabla)
        registros = cargar_registros(usuario, clave, tabla)
        if registros:
            st.dataframe(registros, use_container_width=True, hide_index=True)
            st.caption("Se muestran hasta 200 registros.")
        else:
            st.info("La tabla no contiene registros.")
        if rol == "RolAdministrador":
            st.divider()
            formulario_admin(usuario, clave, seleccion, tabla, columnas, pk)
        else:
            st.caption("Este rol puede consultar este módulo. Las operaciones de escritura deben realizarse mediante los permisos y procedimientos autorizados en SQL Server.")
    except Exception as e:
        st.error("No se pudo cargar el módulo. Es posible que el rol no tenga permiso para consultar esta tabla.")
        st.caption(str(e))


if __name__ == "__main__":
    main()
