import os
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

# crear static si no existe (evita crash)
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
# TXT STORAGE
# -----------------------
def ensure_registro_txt():
    if not os.path.exists(TEMPLATE_FILE):
        with open(TEMPLATE_FILE, "w", encoding="utf-8") as f:
            f.write("")


def leer_registros() -> List[Dict[str, str]]:
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


def guardar_registros(registros: List[Dict[str, str]]) -> None:
    with open(TEMPLATE_FILE, "w", encoding="utf-8") as f:
        for r in registros:
            for k in FIELDS_ORDER:
                f.write(f"{k}: {r.get(k, '')}\n")
            f.write("\n")


# -----------------------
# FECHAS / CÁLCULOS
# -----------------------
def parse_fecha(s: str) -> Optional[dt.date]:
    s = (s or "").strip()
    if not s:
        return None
    return dt.datetime.strptime(s, "%d/%m/%Y").date()


def format_fecha(d: dt.date) -> str:
    return d.strftime("%d/%m/%Y")


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
            # si campo raro, busca en todo
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
            # puede fallar si no hay chat previo
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
# ROUTES
# -----------------------
@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/registrar", response_class=HTMLResponse)
def registrar_form(request: Request):
    return templates.TemplateResponse("registrar.html", {"request": request, "error": ""})


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
    registros = leer_registros()

    ta = (tiene_arroba or "").strip()
    if ta and not ta.startswith("@"):
        ta = "@" + ta

    nuevo = {k: "" for k in FIELDS_ORDER}
    nuevo["NOMBRE_CLIENTE"] = (nombre_cliente or "").strip()
    nuevo["TIENE_ARROBA"] = ta
    nuevo["ID_CLIENTE"] = (id_cliente or "").strip()
    nuevo["ID"] = (id_telegram or "").strip()
    nuevo["CORREO_ELECTRONICO"] = (correo or "").strip()
    nuevo["CONTRASEÑA"] = (contrasena or "").strip()
    nuevo["FECHA_INICIO"] = (fecha_inicio or "").strip()
    nuevo["FECHA_CORTE"] = (fecha_corte or "").strip()
    nuevo["DIAS_SERVICIO"] = calc_dias(nuevo["FECHA_INICIO"], nuevo["FECHA_CORTE"])
    nuevo["SERVICIO_OTORGADO"] = (servicio_otorgado or "").strip()
    nuevo["DISPOSITIVOS"] = (dispositivos or "").strip()
    nuevo["PERFIL_CUENTA"] = (perfil_cuenta or "").strip()
    nuevo["PIN_CUENTA"] = (pin_cuenta or "").strip()
    nuevo["MONTO_PAGADO"] = (monto_pagado or "").strip()

    registros.append(nuevo)
    guardar_registros(registros)
    return RedirectResponse(url="/stats", status_code=303)


@app.get("/cobrar", response_class=HTMLResponse)
def cobrar(request: Request, field: str = "ALL", q: str = ""):
    registros = leer_registros()
    regs_with_idx = list(enumerate(registros))
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

    # orden menor -> mayor
    rows.sort(key=lambda x: (x["restantes"] is None, x["restantes"] if x["restantes"] is not None else 10**9))

    res = request.query_params.get("res", "")
    return templates.TemplateResponse(
        "cobrar.html",
        {"request": request, "rows": rows, "res": res, "field": field, "q": q, "search_fields": SEARCH_FIELDS}
    )


@app.post("/cobrar/enviar/{registro_id}")
async def cobrar_uno(registro_id: int):
    registros = leer_registros()
    if registro_id < 0 or registro_id >= len(registros):
        raise HTTPException(status_code=404, detail="Registro no encontrado")

    res = await telegram_send(registros[registro_id])
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
    registros = leer_registros()
    if registro_id < 0 or registro_id >= len(registros):
        raise HTTPException(status_code=404, detail="Registro no encontrado")

    registros.pop(registro_id)
    guardar_registros(registros)
    return RedirectResponse(url="/cobrar?res=ELIMINADO", status_code=303)


@app.get("/stats", response_class=HTMLResponse)
def stats(request: Request, field: str = "ALL", q: str = ""):
    registros = leer_registros()
    regs_with_idx = list(enumerate(registros))
    filtrados = apply_search(regs_with_idx, field, q)

    return templates.TemplateResponse(
        "stats.html",
        {
            "request": request,
            "regs_with_idx": filtrados,
            "fields": FIELDS_ORDER,
            "field": field,
            "q": q,
            "search_fields": SEARCH_FIELDS,
        }
    )


@app.get("/editar/{registro_id}", response_class=HTMLResponse)
def editar_form(request: Request, registro_id: int):
    registros = leer_registros()
    if registro_id < 0 or registro_id >= len(registros):
        raise HTTPException(status_code=404, detail="Registro no encontrado")

    r = registros[registro_id]
    return templates.TemplateResponse(
        "editar.html",
        {"request": request, "r": r, "registro_id": registro_id, "error": ""}
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
    registros = leer_registros()
    if registro_id < 0 or registro_id >= len(registros):
        raise HTTPException(status_code=404, detail="Registro no encontrado")

    ta = (tiene_arroba or "").strip()
    if ta and not ta.startswith("@"):
        ta = "@" + ta

    # Actualiza el registro seleccionado
    r = registros[registro_id]
    r["NOMBRE_CLIENTE"] = (nombre_cliente or "").strip()
    r["TIENE_ARROBA"] = ta
    r["ID_CLIENTE"] = (id_cliente or "").strip()
    r["ID"] = (id_telegram or "").strip()
    r["CORREO_ELECTRONICO"] = (correo or "").strip()
    r["CONTRASEÑA"] = (contrasena or "").strip()
    r["FECHA_INICIO"] = (fecha_inicio or "").strip()
    r["FECHA_CORTE"] = (fecha_corte or "").strip()
    r["DIAS_SERVICIO"] = calc_dias(r["FECHA_INICIO"], r["FECHA_CORTE"])
    r["SERVICIO_OTORGADO"] = (servicio_otorgado or "").strip()
    r["DISPOSITIVOS"] = (dispositivos or "").strip()
    r["PERFIL_CUENTA"] = (perfil_cuenta or "").strip()
    r["PIN_CUENTA"] = (pin_cuenta or "").strip()
    r["MONTO_PAGADO"] = (monto_pagado or "").strip()

    # asegura campos
    for k in FIELDS_ORDER:
        r.setdefault(k, "")

    guardar_registros(registros)
    return RedirectResponse(url="/stats?res=EDITADO", status_code=303)