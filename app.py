import os
import sqlite3
import datetime as dt
from typing import Optional, List, Dict, Tuple

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from telethon import TelegramClient
import config

# -----------------------
# APP / TEMPLATES / STATIC
# -----------------------
app = FastAPI()
templates = Jinja2Templates(directory="templates")

os.makedirs("static", exist_ok=True)
style_path = os.path.join("static", "style.css")
if not os.path.exists(style_path):
    with open(style_path, "w", encoding="utf-8") as f:
        f.write("")

app.mount("/static", StaticFiles(directory="static"), name="static")

TEMPLATE_FILE = "registro.txt"

FIELDS_ORDER = [
    "ID",
    "NOMBRE_CLIENTE",
    "ID_CLIENTE",
    "TIENE_ARROBA",
    "CORREO_ELECTRONICO",
    "CONTRASEÑA",
    "FECHA_INICIO",
    "FECHA_CORTE",
    "DIAS_SERVICIO",
    "SERVICIO_OTORGADO",
    "PERFIL_CUENTA",
    "PIN_CUENTA",
    "MONTO_PAGADO",
    "DISPOSITIVOS",
]

SEARCH_FIELDS = [
    "NOMBRE_CLIENTE",
    "ID_CLIENTE",
    "TIENE_ARROBA",
    "ID",
    "CORREO_ELECTRONICO",
    "SERVICIO_OTORGADO",
]

# -----------------------
# DB
# -----------------------
def get_db_path() -> str:
    db_url = (config.DB_URL or "").strip()

    if db_url.startswith("sqlite:///"):
        return db_url.replace("sqlite:///", "", 1)

    if not db_url:
        return "clientes.db"

    return db_url


DB_PATH = get_db_path()


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            pk INTEGER PRIMARY KEY AUTOINCREMENT,
            id_telegram TEXT DEFAULT '',
            nombre_cliente TEXT DEFAULT '',
            id_cliente TEXT DEFAULT '',
            tiene_arroba TEXT DEFAULT '',
            correo_electronico TEXT DEFAULT '',
            contrasena TEXT DEFAULT '',
            fecha_inicio TEXT DEFAULT '',
            fecha_corte TEXT DEFAULT '',
            dias_servicio TEXT DEFAULT '',
            servicio_otorgado TEXT DEFAULT '',
            perfil_cuenta TEXT DEFAULT '',
            pin_cuenta TEXT DEFAULT '',
            monto_pagado TEXT DEFAULT '',
            dispositivos TEXT DEFAULT ''
        )
    """)

    conn.commit()
    conn.close()


def count_clientes() -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM clientes")
    total = cur.fetchone()[0]
    conn.close()
    return total


def ensure_registro_txt():
    if not os.path.exists(TEMPLATE_FILE):
        with open(TEMPLATE_FILE, "w", encoding="utf-8") as f:
            f.write("")


def leer_registros_txt() -> List[Dict[str, str]]:
    ensure_registro_txt()
    registros: List[Dict[str, str]] = []

    with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
        bloque: Dict[str, str] = {}
        for linea in f:
            linea = linea.rstrip("\n")
            if not linea.strip():
                if bloque:
                    registros.append(bloque)
                    bloque = {}
                continue
            if ":" in linea:
                k, v = linea.split(":", 1)
                bloque[k.strip()] = v.strip()
        if bloque:
            registros.append(bloque)

    for r in registros:
        for k in FIELDS_ORDER:
            r.setdefault(k, "")
    return registros


def migrar_txt_a_db_si_vacio() -> None:
    init_db()

    if count_clientes() > 0:
        return

    if not os.path.exists(TEMPLATE_FILE):
        return

    registros = leer_registros_txt()
    if not registros:
        return

    conn = get_conn()
    cur = conn.cursor()

    for r in registros:
        cur.execute("""
            INSERT INTO clientes (
                id_telegram, nombre_cliente, id_cliente, tiene_arroba,
                correo_electronico, contrasena, fecha_inicio, fecha_corte,
                dias_servicio, servicio_otorgado, perfil_cuenta, pin_cuenta,
                monto_pagado, dispositivos
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            r.get("ID", ""),
            r.get("NOMBRE_CLIENTE", ""),
            r.get("ID_CLIENTE", ""),
            r.get("TIENE_ARROBA", ""),
            r.get("CORREO_ELECTRONICO", ""),
            r.get("CONTRASEÑA", ""),
            r.get("FECHA_INICIO", ""),
            r.get("FECHA_CORTE", ""),
            r.get("DIAS_SERVICIO", ""),
            r.get("SERVICIO_OTORGADO", ""),
            r.get("PERFIL_CUENTA", ""),
            r.get("PIN_CUENTA", ""),
            r.get("MONTO_PAGADO", ""),
            r.get("DISPOSITIVOS", ""),
        ))

    conn.commit()
    conn.close()


def row_to_registro(row: sqlite3.Row) -> Dict[str, str]:
    return {
        "PK": str(row["pk"]),
        "ID": row["id_telegram"] or "",
        "NOMBRE_CLIENTE": row["nombre_cliente"] or "",
        "ID_CLIENTE": row["id_cliente"] or "",
        "TIENE_ARROBA": row["tiene_arroba"] or "",
        "CORREO_ELECTRONICO": row["correo_electronico"] or "",
        "CONTRASEÑA": row["contrasena"] or "",
        "FECHA_INICIO": row["fecha_inicio"] or "",
        "FECHA_CORTE": row["fecha_corte"] or "",
        "DIAS_SERVICIO": row["dias_servicio"] or "",
        "SERVICIO_OTORGADO": row["servicio_otorgado"] or "",
        "PERFIL_CUENTA": row["perfil_cuenta"] or "",
        "PIN_CUENTA": row["pin_cuenta"] or "",
        "MONTO_PAGADO": row["monto_pagado"] or "",
        "DISPOSITIVOS": row["dispositivos"] or "",
    }


def leer_registros() -> List[Dict[str, str]]:
    init_db()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            pk, id_telegram, nombre_cliente, id_cliente, tiene_arroba,
            correo_electronico, contrasena, fecha_inicio, fecha_corte,
            dias_servicio, servicio_otorgado, perfil_cuenta, pin_cuenta,
            monto_pagado, dispositivos
        FROM clientes
        ORDER BY pk ASC
    """)
    rows = cur.fetchall()
    conn.close()
    return [row_to_registro(r) for r in rows]


def get_registro_by_pk(pk: int) -> Optional[Dict[str, str]]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            pk, id_telegram, nombre_cliente, id_cliente, tiene_arroba,
            correo_electronico, contrasena, fecha_inicio, fecha_corte,
            dias_servicio, servicio_otorgado, perfil_cuenta, pin_cuenta,
            monto_pagado, dispositivos
        FROM clientes
        WHERE pk = ?
    """, (pk,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return None
    return row_to_registro(row)

# -----------------------
# FECHAS / CÁLCULOS
# -----------------------
def parse_fecha(s: str) -> Optional[dt.date]:
    s = (s or "").strip()
    if not s:
        return None
    return dt.datetime.strptime(s, "%d/%m/%Y").date()


def dias_restantes(fecha_corte_str: str) -> Optional[int]:
    fc = parse_fecha(fecha_corte_str)
    if not fc:
        return None
    return (fc - dt.date.today()).days


def calc_dias(fi_str: str, fc_str: str) -> str:
    fi = parse_fecha(fi_str)
    fc = parse_fecha(fc_str)
    if not fi or not fc:
        return ""
    return str((fc - fi).days)


def nombre_para_mensaje(r: Dict[str, str]) -> str:
    nom = (r.get("NOMBRE_CLIENTE") or "").strip()
    arroba = (r.get("TIENE_ARROBA") or "").strip()
    return nom or arroba or "cliente"

# -----------------------
# SEARCH
# -----------------------
def apply_search(regs_with_idx: List[Tuple[int, Dict[str, str]]], field: str, q: str) -> List[Tuple[int, Dict[str, str]]]:
    q = (q or "").strip().lower()
    field = (field or "ALL").strip()

    if not q:
        return regs_with_idx

    def match_in_record(rec: Dict[str, str]) -> bool:
        if field == "ALL":
            for f in SEARCH_FIELDS:
                if q in (rec.get(f, "") or "").lower():
                    return True
            return False

        if field not in FIELDS_ORDER:
            for f in SEARCH_FIELDS:
                if q in (rec.get(f, "") or "").lower():
                    return True
            return False

        return q in (rec.get(field, "") or "").lower()

    return [(i, r) for (i, r) in regs_with_idx if match_in_record(r)]

# -----------------------
# MENSAJES COBRO
# -----------------------
def construir_mensaje_cobro(r: Dict[str, str]) -> Optional[str]:
    dr = dias_restantes(r.get("FECHA_CORTE", ""))
    if dr is None:
        return None

    nombre_usuario = nombre_para_mensaje(r)
    servicio = (r.get("SERVICIO_OTORGADO") or "").strip()
    correo = (r.get("CORREO_ELECTRONICO") or "").strip()
    inicio = (r.get("FECHA_INICIO") or "").strip()
    corte = (r.get("FECHA_CORTE") or "").strip()

    if 2 <= dr <= 5:
        return (
            f"⚠ NOTIFICACIÓN DE VENCIMIENTO ⚠\n\n"
            f"Hola {nombre_usuario}, tu servicio de {servicio} está por vencer y me gustaría saber si deseas renovar. "
            f"Agradecería tu confirmación.\n\n"
            f"⏱ FALTAN {dr} DÍAS\n"
            f"✉ Correo: {correo}\n"
            f"📅 F. Inicio: {inicio}\n"
            f"🚨 F. Corte: {corte}\n"
            f"💳 Monto a depositar: https://noodlestreaming.com/\n\n"
            f"✍🏻 Consulta nuestros planes aquí o en https://noodlestreaming.com"
        )

    if dr == 1:
        return (
            f"🚨 RECORDATORIO DE VENCIMIENTO 🚨\n\n"
            f"Hola {nombre_usuario}, tu servicio de {servicio} vence mañana. "
            f"Por favor confirma si deseas renovarlo.\n\n"
            f"⏱ FALTA {dr} DÍA\n"
            f"✉ Correo: {correo}\n"
            f"📅 F. Inicio: {inicio}\n"
            f"🚨 F. Corte: {corte}\n"
            f"💳 Monto a depositar: https://noodlestreaming.com\n\n"
            f"✍🏻 Consulta nuestros planes aquí o en https://noodlestreaming.com"
        )

    dias_vencido = abs(dr)
    return (
        f"🚨 RECORDATORIO DE VENCIMIENTO 🚨\n\n"
        f"Hola {nombre_usuario}, te comento que tu servicio de {servicio} VENCIÓ y el pago aún está pendiente. "
        f"Por favor confirma cuanto antes.\n\n"
        f"⏱ FALTAN {dr} DÍAS\n"
        f"✉ Correo: {correo}\n"
        f"📅 F. Inicio: {inicio}\n"
        f"🚨 F. Corte: {corte}\n"
        f"💳 Monto a depositar: https://noodlestreaming.com\n"
        f"⏱ VENCIDO HACE {dias_vencido} DÍAS\n\n"
        f"✍🏻 Consulta nuestros planes aquí o en https://noodlestreaming.com"
    )


async def telegram_send(r: Dict[str, str]) -> str:
    mensaje = construir_mensaje_cobro(r)
    if not mensaje:
        return "SIN_FECHA_CORTE"

    arroba = (r.get("TIENE_ARROBA") or "").strip()
    if arroba and not arroba.startswith("@"):
        arroba = "@" + arroba

    id_num = None
    for key in ("ID_CLIENTE", "ID"):
        v = (r.get(key) or "").strip()
        if v.isdigit():
            id_num = int(v)
            break

    async with TelegramClient("registro_cliente", config.API_ID, config.API_HASH) as client:
        await client.start()

        if arroba:
            await client.send_message(arroba, mensaje)
            return "OK"

        if id_num is not None:
            try:
                ent = await client.get_entity(id_num)
                await client.send_message(ent, mensaje)
                return "OK"
            except Exception:
                pass

            try:
                dialogs = await client.get_dialogs(limit=600)
                for d in dialogs:
                    if getattr(d.entity, "id", None) == id_num:
                        await client.send_message(d.entity, mensaje)
                        return "OK"
            except Exception:
                pass

            try:
                inp = await client.get_input_entity(id_num)
                await client.send_message(inp, mensaje)
                return "OK"
            except Exception:
                return "NO_ENTIDAD_PARA_ID"

        return "SIN_DESTINO"

# -----------------------
# STARTUP
# -----------------------
@app.on_event("startup")
def startup_event():
    init_db()
    migrar_txt_a_db_si_vacio()

# -----------------------
# ROUTES
# -----------------------
@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={}
    )


@app.get("/registrar", response_class=HTMLResponse)
def registrar_form(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="registrar.html",
        context={"error": ""}
    )


@app.post("/registrar")
async def registrar_post(
    request: Request,
    nombre_cliente: str = Form(""),
    tiene_arroba: str = Form(""),
    id_cliente: str = Form(""),
    id_telegram: str = Form(""),
    correo: str = Form(""),
    contrasena: str = Form(""),
    fecha_inicio: str = Form(""),
    fecha_corte: str = Form(""),
    servicio_otorgado: str = Form(""),
    dispositivos: str = Form(""),
    perfil_cuenta: str = Form(""),
    pin_cuenta: str = Form(""),
    monto_pagado: str = Form(""),
):
    ta = (tiene_arroba or "").strip()
    if ta and not ta.startswith("@"):
        ta = "@" + ta

    fi = (fecha_inicio or "").strip()
    fc = (fecha_corte or "").strip()
    dias = calc_dias(fi, fc)

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO clientes (
            id_telegram, nombre_cliente, id_cliente, tiene_arroba,
            correo_electronico, contrasena, fecha_inicio, fecha_corte,
            dias_servicio, servicio_otorgado, perfil_cuenta, pin_cuenta,
            monto_pagado, dispositivos
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        (id_telegram or "").strip(),
        (nombre_cliente or "").strip(),
        (id_cliente or "").strip(),
        ta,
        (correo or "").strip(),
        (contrasena or "").strip(),
        fi,
        fc,
        dias,
        (servicio_otorgado or "").strip(),
        (perfil_cuenta or "").strip(),
        (pin_cuenta or "").strip(),
        (monto_pagado or "").strip(),
        (dispositivos or "").strip(),
    ))
    conn.commit()
    conn.close()

    return RedirectResponse(url="/stats", status_code=303)


@app.get("/cobrar", response_class=HTMLResponse)
def cobrar(request: Request, field: str = "ALL", q: str = ""):
    registros = leer_registros()
    regs_with_idx = [(int(r.get("PK", "0")), r) for r in registros]
    filtrados = apply_search(regs_with_idx, field, q)

    rows = []
    for idx, r in filtrados:
        dr = dias_restantes(r.get("FECHA_CORTE", ""))
        rows.append({
            "id": idx,
            "cliente": (r.get("NOMBRE_CLIENTE") or r.get("TIENE_ARROBA") or "").strip(),
            "servicio": (r.get("SERVICIO_OTORGADO") or "").strip(),
            "fecha_corte": (r.get("FECHA_CORTE") or "").strip(),
            "restantes": dr,
        })

    rows.sort(key=lambda x: (x["restantes"] is None, x["restantes"] if x["restantes"] is not None else 10**9))

    res = request.query_params.get("res", "")
    return templates.TemplateResponse(
        request=request,
        name="cobrar.html",
        context={
            "rows": rows,
            "res": res,
            "field": field,
            "q": q,
            "search_fields": SEARCH_FIELDS,
        }
    )


@app.post("/cobrar/enviar/{registro_id}")
async def cobrar_uno(registro_id: int):
    r = get_registro_by_pk(registro_id)
    if not r:
        raise HTTPException(status_code=404, detail="Registro no encontrado")

    res = await telegram_send(r)
    return RedirectResponse(url=f"/cobrar?res={res}", status_code=303)


@app.post("/cobrar/enviar_todos")
async def cobrar_todos():
    registros = leer_registros()
    enviados = 0
    errores = 0

    for r in registros:
        dr = dias_restantes(r.get("FECHA_CORTE", ""))
        if dr is None:
            continue
        if dr <= 5:
            try:
                res = await telegram_send(r)
                if res == "OK":
                    enviados += 1
                else:
                    errores += 1
            except Exception:
                errores += 1

    return RedirectResponse(url=f"/cobrar?res=ENVIO_MASIVO_OK_{enviados}_ERR_{errores}", status_code=303)


@app.post("/cobrar/eliminar/{registro_id}")
async def eliminar_registro(registro_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM clientes WHERE pk = ?", (registro_id,))
    conn.commit()
    deleted = cur.rowcount
    conn.close()

    if deleted == 0:
        raise HTTPException(status_code=404, detail="Registro no encontrado")

    return RedirectResponse(url="/cobrar?res=ELIMINADO", status_code=303)


@app.get("/stats", response_class=HTMLResponse)
def stats(request: Request, field: str = "ALL", q: str = ""):
    registros = leer_registros()
    regs_with_idx = [(int(r.get("PK", "0")), r) for r in registros]
    filtrados = apply_search(regs_with_idx, field, q)

    return templates.TemplateResponse(
        request=request,
        name="stats.html",
        context={
            "regs_with_idx": filtrados,
            "fields": FIELDS_ORDER,
            "field": field,
            "q": q,
            "search_fields": SEARCH_FIELDS,
        }
    )


@app.get("/editar/{registro_id}", response_class=HTMLResponse)
def editar_form(request: Request, registro_id: int):
    r = get_registro_by_pk(registro_id)
    if not r:
        raise HTTPException(status_code=404, detail="Registro no encontrado")

    return templates.TemplateResponse(
        request=request,
        name="editar.html",
        context={
            "r": r,
            "registro_id": registro_id,
            "error": ""
        }
    )


@app.post("/editar/{registro_id}")
async def editar_post(
    request: Request,
    registro_id: int,
    nombre_cliente: str = Form(""),
    tiene_arroba: str = Form(""),
    id_cliente: str = Form(""),
    id_telegram: str = Form(""),
    correo: str = Form(""),
    contrasena: str = Form(""),
    fecha_inicio: str = Form(""),
    fecha_corte: str = Form(""),
    servicio_otorgado: str = Form(""),
    dispositivos: str = Form(""),
    perfil_cuenta: str = Form(""),
    pin_cuenta: str = Form(""),
    monto_pagado: str = Form(""),
):
    existente = get_registro_by_pk(registro_id)
    if not existente:
        raise HTTPException(status_code=404, detail="Registro no encontrado")

    ta = (tiene_arroba or "").strip()
    if ta and not ta.startswith("@"):
        ta = "@" + ta

    fi = (fecha_inicio or "").strip()
    fc = (fecha_corte or "").strip()
    dias = calc_dias(fi, fc)

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        UPDATE clientes
        SET
            id_telegram = ?,
            nombre_cliente = ?,
            id_cliente = ?,
            tiene_arroba = ?,
            correo_electronico = ?,
            contrasena = ?,
            fecha_inicio = ?,
            fecha_corte = ?,
            dias_servicio = ?,
            servicio_otorgado = ?,
            perfil_cuenta = ?,
            pin_cuenta = ?,
            monto_pagado = ?,
            dispositivos = ?
        WHERE pk = ?
    """, (
        (id_telegram or "").strip(),
        (nombre_cliente or "").strip(),
        (id_cliente or "").strip(),
        ta,
        (correo or "").strip(),
        (contrasena or "").strip(),
        fi,
        fc,
        dias,
        (servicio_otorgado or "").strip(),
        (perfil_cuenta or "").strip(),
        (pin_cuenta or "").strip(),
        (monto_pagado or "").strip(),
        (dispositivos or "").strip(),
        registro_id,
    ))
    conn.commit()
    conn.close()

    return RedirectResponse(url="/stats?res=EDITADO", status_code=303)