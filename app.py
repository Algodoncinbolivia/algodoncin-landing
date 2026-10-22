import csv
import io
import os
import re
from datetime import date, datetime, timedelta
from functools import wraps
from urllib.parse import quote

from flask import Flask, Response, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from db import get_conn, init_db

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-cambiar-en-produccion")

CIUDADES = ["Oruro", "La Paz", "Cochabamba", "Santa Cruz"]
PUNTOS_FIJOS = {"Oruro": ["Parque de la Unión", "Plaza Sebastián Pagador"]}
FECHA_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# ID del Píxel de Meta (15-16 números, Administrador de eventos). Vacío = el píxel no se carga.
# También se puede definir como variable de entorno META_PIXEL_ID en el hosting.
META_PIXEL_ID = os.environ.get("META_PIXEL_ID", "1090696957080950").strip()  # "Algodoncín Web" en samiagenciamkt


@app.context_processor
def inyectar_pixel():
    id_ok = META_PIXEL_ID if META_PIXEL_ID.isdigit() else ""
    return {"meta_pixel_id": id_ok}


PRECIO_ALGODON_PUNTO_FIJO = 20 # mismo precio que el punto de venta (ver sistema-ventas/db.py)

# Testimonios reales de mamás que ya contrataron el servicio. Vacío a propósito:
# nunca se inventan reseñas falsas. Cuando tengas 2-3 reales (whatsapp, comentarios
# de TikTok, etc.) se agregan acá como {"texto": "...", "nombre": "...", "evento": "..."}
# y la sección aparece sola en la landing.
TESTIMONIOS = []


# ----------------------------------------------------- Halloween 2026 ----
# WhatsApp de Algodoncín. OJO: el 63339566 es de EmpresariOS, otro negocio: no mezclar.
WHATSAPP_ALGODONCIN = "59175715559"

HALLOWEEN = {
    "fecha": "Sábado 31 de octubre",
    "hora": "16:00",
    "lugar": "Hotel Edén",
    # Plazos en hora de Bolivia. Cambiarlos acá cambia la página y el cierre del registro.
    "registro_hasta": datetime(2026, 10, 29, 12, 0),
    "votos_hasta": datetime(2026, 10, 30, 20, 0),
    "cupo_algodones": None,      # tope de algodones a preparar; None = sin tope
    "max_por_registro": 4,
    "tiktok_url": None,          # enlace al TikTok de Algodoncín (se muestra solo si se completa)
}

# Personajes que sabemos preparar (los del catálogo público de la landing + los más vendidos).
DISFRACES = [
    "Hello Kitty", "Kuromi", "My Melody", "Cinnamoroll", "Unicornio", "Baby Yoda",
    "Pikachu", "Mario y Luigi", "Among Us", "Minions", "Homero", "Daisy",
]
OTRO = "Otro disfraz"

WHATSAPP_RE = re.compile(r"^[67]\d{7}$")
FUENTE_RE = re.compile(r"[^a-z0-9_-]")


def ahora_bo():
    """Hora de Bolivia (UTC-4) sin zona, porque Render corre en UTC."""
    return datetime.utcnow() - timedelta(hours=4)


def fecha_larga(dt):
    dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
             "septiembre", "octubre", "noviembre", "diciembre"]
    return f"{dias[dt.weekday()]} {dt.day} de {meses[dt.month - 1]}"


def hora_corta(dt):
    return dt.strftime("%H:%M")


def wa_link(texto):
    return f"https://wa.me/{WHATSAPP_ALGODONCIN}?text={quote(texto)}"


def algodones_registrados(db):
    fila = db.execute(
        "SELECT COALESCE(SUM(cantidad), 0) AS n FROM registros_halloween WHERE estado != 'cancelado'"
    ).fetchone()
    return fila["n"]


def estado_registro(db):
    """Devuelve (abierto, motivo_cierre, cupos_restantes)."""
    if ahora_bo() > HALLOWEEN["registro_hasta"]:
        return False, "plazo", None
    cupo = HALLOWEEN["cupo_algodones"]
    if cupo is not None:
        restantes = max(0, cupo - algodones_registrados(db))
        if restantes == 0:
            return False, "cupo", 0
        return True, None, restantes
    return True, None, None


@app.before_request
def load_db():
    g.db = get_conn()


@app.teardown_request
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def login_required_admin(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)
    return wrapped


# --------------------------------------------------------------- public ----

@app.route("/")
def index():
    return render_template(
        "index.html", ciudades=CIUDADES, puntos_fijos=PUNTOS_FIJOS, hoy=date.today().isoformat(),
        precio_punto_fijo=PRECIO_ALGODON_PUNTO_FIJO, testimonios=TESTIMONIOS,
    )


@app.route("/api/disponibilidad")
def api_disponibilidad():
    ciudad = request.args.get("ciudad", "")
    mes = request.args.get("mes", "")  # YYYY-MM
    if ciudad not in CIUDADES or not re.match(r"^\d{4}-\d{2}$", mes):
        return jsonify({"error": "Parámetros inválidos"}), 400

    filas = g.db.execute(
        """
        SELECT fecha, tipo, punto, estado FROM reservas
        WHERE ciudad = ? AND estado != 'cancelada' AND strftime('%Y-%m', fecha) = ?
        """,
        (ciudad, mes),
    ).fetchall()

    return jsonify([dict(f) for f in filas])


@app.route("/api/reservas", methods=["POST"])
def api_reservas_crear():
    data = request.get_json(force=True) or {}

    ciudad = data.get("ciudad", "")
    tipo = data.get("tipo", "")
    fecha = data.get("fecha", "")
    nombre = (data.get("nombre") or "").strip()
    whatsapp = (data.get("whatsapp") or "").strip()

    if ciudad not in CIUDADES:
        return jsonify({"error": "Ciudad no válida."}), 400
    if tipo not in ("evento", "punto_fijo"):
        return jsonify({"error": "Tipo de reserva no válido."}), 400
    if not FECHA_RE.match(fecha) or fecha < date.today().isoformat():
        return jsonify({"error": "Fecha no válida."}), 400
    if not nombre or not whatsapp:
        return jsonify({"error": "Faltan tus datos de contacto."}), 400

    punto = data.get("punto") if tipo == "punto_fijo" else None
    if tipo == "punto_fijo" and punto not in PUNTOS_FIJOS.get(ciudad, []):
        return jsonify({"error": "Punto fijo no válido para esa ciudad."}), 400

    # Evita doble reserva del mismo día/ciudad/tipo (y punto, si aplica)
    query = "SELECT id FROM reservas WHERE ciudad=? AND fecha=? AND tipo=? AND estado != 'cancelada'"
    params = [ciudad, fecha, tipo]
    if punto:
        query += " AND punto = ?"
        params.append(punto)
    existente = g.db.execute(query, params).fetchone()
    if existente:
        return jsonify({"error": "Esa fecha ya no está disponible, elige otra."}), 409

    g.db.execute(
        """
        INSERT INTO reservas (ciudad, tipo, punto, fecha, nombre, whatsapp, tipo_evento, lugar, invitados, mensaje)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ciudad, tipo, punto, fecha, nombre, whatsapp,
            (data.get("tipo_evento") or "").strip() or None,
            (data.get("lugar") or "").strip() or None,
            int(data["invitados"]) if str(data.get("invitados", "")).strip().isdigit() else None,
            (data.get("mensaje") or "").strip() or None,
        ),
    )
    g.db.commit()
    return jsonify({"ok": True})


# ------------------------------------------------------------ halloween ----

@app.route("/halloween")
def halloween():
    abierto, motivo, restantes = estado_registro(g.db)
    n_registrados = g.db.execute(
        "SELECT COUNT(*) AS n FROM registros_halloween WHERE estado != 'cancelado'"
    ).fetchone()["n"]
    h = HALLOWEEN
    return render_template(
        "halloween.html",
        h=h, disfraces=DISFRACES, otro=OTRO,
        abierto=abierto, motivo=motivo, restantes=restantes,
        n_registrados=n_registrados,
        registro_hasta=f"{fecha_larga(h['registro_hasta'])} a las {hora_corta(h['registro_hasta'])}",
        votos_hasta=f"{fecha_larga(h['votos_hasta'])} a las {hora_corta(h['votos_hasta'])}",
        wa_general=wa_link("Hola Algodoncín, quiero información del Halloween"),
        whatsapp_visible="7 5 7 1 5 5 5 9",
    )


@app.route("/api/halloween/registro", methods=["POST"])
def api_halloween_registro():
    data = request.get_json(silent=True) or {}

    # trampa para bots: un campo escondido que una persona nunca llena
    if (data.get("web") or "").strip():
        return jsonify({"ok": True})

    abierto, motivo, restantes = estado_registro(g.db)
    if not abierto:
        msg = ("Los registros ya cerraron. Escríbenos por WhatsApp y vemos si aún podemos prepararlo."
               if motivo == "plazo" else
               "Se acabaron los cupos para preparar con anticipación. Escríbenos por WhatsApp.")
        return jsonify({"error": msg, "cerrado": True}), 409

    nombre_nino = " ".join((data.get("nombre_nino") or "").split())[:60]
    nombre_adulto = " ".join((data.get("nombre_adulto") or "").split())[:80]
    whatsapp = re.sub(r"\D", "", data.get("whatsapp") or "")
    if len(whatsapp) == 11 and whatsapp.startswith("591"):
        whatsapp = whatsapp[3:]
    disfraz = (data.get("disfraz") or "").strip()
    disfraz_otro = " ".join((data.get("disfraz_otro") or "").split())[:60]
    fuente = FUENTE_RE.sub("", (data.get("fuente") or "").lower())[:40] or None

    try:
        cantidad = int(data.get("cantidad", 1))
    except (TypeError, ValueError):
        cantidad = 0

    if not nombre_nino:
        return jsonify({"error": "Escribe el nombre del niño o niña (puede ser un apodo)."}), 400
    if not nombre_adulto:
        return jsonify({"error": "Escribe tu nombre, mamá, papá o tutor."}), 400
    if not WHATSAPP_RE.match(whatsapp):
        return jsonify({"error": "Escribe un WhatsApp de 8 dígitos que empiece con 6 o 7."}), 400
    if disfraz == OTRO:
        if not disfraz_otro:
            return jsonify({"error": "Cuéntanos de qué se disfraza."}), 400
        disfraz = f"{OTRO}: {disfraz_otro}"
    elif disfraz not in DISFRACES:
        return jsonify({"error": "Elige el personaje del disfraz."}), 400
    if not 1 <= cantidad <= HALLOWEEN["max_por_registro"]:
        return jsonify({"error": f"Puedes pedir de 1 a {HALLOWEEN['max_por_registro']} algodones."}), 400
    if not data.get("acepta"):
        return jsonify({"error": "Para participar tienes que aceptar las bases."}), 400
    if restantes is not None and cantidad > restantes:
        return jsonify({"error": f"Solo quedan {restantes} cupos para preparar con anticipación."}), 409

    # doble toque: el mismo registro en los últimos 10 minutos devuelve el que ya existe
    previo = g.db.execute(
        """
        SELECT id FROM registros_halloween
        WHERE whatsapp = ? AND lower(nombre_nino) = lower(?) AND disfraz = ? AND estado != 'cancelado'
          AND creado_en >= datetime('now', '-10 minutes')
        """,
        (whatsapp, nombre_nino, disfraz),
    ).fetchone()
    if previo:
        reg_id = previo["id"]
    else:
        n_previos = g.db.execute(
            "SELECT COUNT(*) AS n FROM registros_halloween WHERE whatsapp = ? AND estado != 'cancelado'",
            (whatsapp,),
        ).fetchone()["n"]
        if n_previos >= 6:
            return jsonify({"error": "Este número ya tiene varios registros. Escríbenos por WhatsApp para ayudarte."}), 429
        cur = g.db.execute(
            """
            INSERT INTO registros_halloween (nombre_nino, nombre_adulto, whatsapp, disfraz, cantidad, fuente)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (nombre_nino, nombre_adulto, whatsapp, disfraz, cantidad, fuente),
        )
        g.db.commit()
        reg_id = cur.lastrowid

    texto = (
        f"Hola Algodoncín 🎃 Soy {nombre_adulto}. Registré a {nombre_nino} para Halloween.\n"
        f"Disfraz: {disfraz} · Algodones: {cantidad} · Registro #{reg_id}.\n"
        f"Les envío la foto del disfraz para el concurso y autorizo publicarla en su TikTok."
    )
    return jsonify({"ok": True, "id": reg_id, "nombre_nino": nombre_nino, "wa_foto": wa_link(texto)})


@app.route("/admin/halloween")
@login_required_admin
def admin_halloween():
    estado = request.args.get("estado", "activos")
    consulta = "SELECT * FROM registros_halloween"
    params = []
    if estado == "activos":
        consulta += " WHERE estado != 'cancelado'"
    elif estado in ("pendiente", "confirmado", "entregado", "cancelado"):
        consulta += " WHERE estado = ?"
        params.append(estado)
    consulta += " ORDER BY id DESC"
    filas = g.db.execute(consulta, params).fetchall()
    para_preparar = g.db.execute(
        """
        SELECT disfraz, SUM(cantidad) AS n, COUNT(*) AS registros FROM registros_halloween
        WHERE estado != 'cancelado' GROUP BY disfraz ORDER BY n DESC, disfraz
        """
    ).fetchall()
    total = algodones_registrados(g.db)
    por_fuente = g.db.execute(
        """
        SELECT COALESCE(fuente, 'directo') AS fuente, COUNT(*) AS n FROM registros_halloween
        WHERE estado != 'cancelado' GROUP BY COALESCE(fuente, 'directo') ORDER BY n DESC
        """
    ).fetchall()
    return render_template(
        "admin_halloween.html", filas=filas, estado_filtro=estado, para_preparar=para_preparar,
        total=total, por_fuente=por_fuente, cupo=HALLOWEEN["cupo_algodones"],
    )


@app.route("/admin/halloween/<int:reg_id>/estado", methods=["POST"])
@login_required_admin
def admin_halloween_estado(reg_id):
    nuevo = request.form.get("estado")
    if nuevo in ("pendiente", "confirmado", "entregado", "cancelado"):
        g.db.execute("UPDATE registros_halloween SET estado = ? WHERE id = ?", (nuevo, reg_id))
        g.db.commit()
    return redirect(url_for("admin_halloween", estado=request.args.get("estado", "activos")))


@app.route("/admin/halloween.csv")
@login_required_admin
def admin_halloween_csv():
    filas = g.db.execute("SELECT * FROM registros_halloween ORDER BY id").fetchall()
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["id", "registrado (UTC)", "niño/a", "mamá/papá", "whatsapp", "disfraz", "algodones", "origen", "estado"])
    for r in filas:
        w.writerow([r["id"], r["creado_en"], r["nombre_nino"], r["nombre_adulto"], r["whatsapp"],
                    r["disfraz"], r["cantidad"], r["fuente"] or "directo", r["estado"]])
    return Response("﻿" + out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=halloween-registros.csv"})


# ---------------------------------------------------------------- admin ----

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "GET":
        return render_template("admin_login.html", error=request.args.get("error"))

    pin = request.form.get("pin", "")
    admin = g.db.execute("SELECT * FROM admin LIMIT 1").fetchone()
    if admin is None or not check_password_hash(admin["pin_hash"], pin):
        return redirect(url_for("admin_login", error="PIN incorrecto."))
    session.clear()
    session["is_admin"] = True
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


@app.route("/admin")
@login_required_admin
def admin_dashboard():
    estado_filtro = request.args.get("estado", "activas")
    query = "SELECT * FROM reservas"
    if estado_filtro == "activas":
        query += " WHERE estado != 'cancelada'"
    elif estado_filtro in ("pendiente", "confirmada", "cancelada"):
        query += " WHERE estado = ?"
    query += " ORDER BY fecha ASC"

    params = [estado_filtro] if estado_filtro in ("pendiente", "confirmada", "cancelada") else []
    filas = g.db.execute(query, params).fetchall()
    return render_template("admin.html", filas=filas, estado_filtro=estado_filtro)


@app.route("/admin/reservas/<int:reserva_id>/estado", methods=["POST"])
@login_required_admin
def admin_cambiar_estado(reserva_id):
    nuevo_estado = request.form.get("estado")
    if nuevo_estado in ("pendiente", "confirmada", "cancelada"):
        g.db.execute("UPDATE reservas SET estado = ? WHERE id = ?", (nuevo_estado, reserva_id))
        g.db.commit()
    return redirect(url_for("admin_dashboard", estado=request.args.get("estado", "activas")))


init_db()  # crea las tablas que falten, también cuando corre con gunicorn en el hosting

if __name__ == "__main__":
    app.run(debug=True, port=5100)
