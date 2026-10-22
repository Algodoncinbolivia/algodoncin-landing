import os
import socket
import sqlite3
from pathlib import Path

# Algunos hosts en la nube (como Render) tienen una ruta IPv6 rota hacia ciertos destinos y la
# conexión se queda colgada en vez de fallar. Se fuerza IPv4 para todo el proceso.
_getaddrinfo_original = socket.getaddrinfo


def _solo_ipv4(host, port, family=0, type=0, proto=0, flags=0):
    return _getaddrinfo_original(host, port, socket.AF_INET, type, proto, flags)


socket.getaddrinfo = _solo_ipv4

DB_PATH = Path(__file__).parent / "reservas.db"


def _env(nombre):
    # quita espacios/saltos de línea que a veces quedan al copiar y pegar valores largos
    valor = os.environ.get(nombre)
    return valor.strip() if valor else valor


TURSO_URL = _env("TURSO_DATABASE_URL")
TURSO_TOKEN = _env("TURSO_AUTH_TOKEN")

SCHEMA = """
CREATE TABLE IF NOT EXISTS reservas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ciudad TEXT NOT NULL,
    tipo TEXT NOT NULL,               -- 'evento' | 'punto_fijo'
    punto TEXT,                       -- nombre del punto fijo, si aplica
    fecha TEXT NOT NULL,              -- YYYY-MM-DD
    nombre TEXT NOT NULL,
    whatsapp TEXT NOT NULL,
    tipo_evento TEXT,
    lugar TEXT,
    invitados INTEGER,
    mensaje TEXT,
    estado TEXT NOT NULL DEFAULT 'pendiente',   -- pendiente | confirmada | cancelada
    creado_en TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS registros_halloween (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre_nino TEXT NOT NULL,
    nombre_adulto TEXT NOT NULL,
    whatsapp TEXT NOT NULL,           -- 8 dígitos, sin +591
    disfraz TEXT NOT NULL,
    cantidad INTEGER NOT NULL DEFAULT 1,
    fuente TEXT,                      -- de dónde llegó (tiktok, volante, whatsapp...)
    estado TEXT NOT NULL DEFAULT 'pendiente',   -- pendiente | confirmado | entregado | cancelado
    creado_en TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS admin (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pin_hash TEXT NOT NULL
);
"""


class _Fila:
    """Una fila que se comporta como sqlite3.Row: fila["col"], fila[0] y dict(fila)."""

    __slots__ = ("_nombres", "_valores")

    def __init__(self, nombres, valores):
        self._nombres = tuple(nombres)
        self._valores = tuple(valores)

    def __getitem__(self, clave):
        if isinstance(clave, str):
            return self._valores[self._nombres.index(clave)]
        return self._valores[clave]

    def keys(self):
        return list(self._nombres)

    def __iter__(self):
        return iter(self._valores)

    def __len__(self):
        return len(self._valores)


class _CursorLike:
    """Hace que un ResultSet de libsql se use igual que un cursor de sqlite3."""

    def __init__(self, result_set):
        self._rs = result_set
        self._filas = [_Fila(result_set.columns, r.astuple()) for r in result_set.rows]
        self.lastrowid = result_set.last_insert_rowid

    def fetchall(self):
        return list(self._filas)

    def fetchone(self):
        return self._filas[0] if self._filas else None


class TursoConnection:
    """Envuelve el cliente de Turso para usarlo igual que una conexión sqlite3
    (execute / executescript / commit / close), sin tocar el resto del código."""

    def __init__(self, client):
        self._client = client

    def execute(self, sql, params=None):
        args = list(params) if params else []
        try:
            return _CursorLike(self._client.execute(sql, args))
        except _ERRORES_DE_RED:
            # Turso tardó o cortó la conexión. Solo se reintenta si es una lectura:
            # repetir un INSERT/UPDATE podría duplicar un registro.
            if not sql.lstrip().upper().startswith(("SELECT", "PRAGMA", "WITH")):
                raise
            self._reconectar()
            return _CursorLike(self._client.execute(sql, args))

    def _reconectar(self):
        try:
            self._client.close()
        except Exception:
            pass
        self._client = _nuevo_cliente_turso()

    def executescript(self, script):
        sentencias = [x.strip() for x in script.split(";") if x.strip()]
        self._client.batch(sentencias)

    def commit(self):
        pass  # cada sentencia de Turso se confirma sola por HTTP

    def close(self):
        self._client.close()


# Sin tiempo máximo la librería espera hasta 5 minutos por consulta y una sola
# consulta trabada dejaría congelada la página para todos.
TURSO_TIMEOUT_TOTAL = 15
TURSO_TIMEOUT_CONEXION = 5

try:
    import aiohttp

    _ERRORES_DE_RED = (TimeoutError, aiohttp.ClientError)
except ImportError:  # sin Turso instalado (uso local)
    _ERRORES_DE_RED = (TimeoutError,)


def _nuevo_cliente_turso():
    import libsql_client

    # https:// en vez de libsql:// (websocket): algunas redes bloquean websockets salientes
    url = TURSO_URL.replace("libsql://", "https://", 1)
    cliente = libsql_client.create_client_sync(url=url, auth_token=TURSO_TOKEN)
    try:
        import aiohttp

        cliente._client._session._timeout = aiohttp.ClientTimeout(
            total=TURSO_TIMEOUT_TOTAL, connect=TURSO_TIMEOUT_CONEXION
        )
    except AttributeError:
        pass  # otra versión de la librería: queda el tiempo por defecto
    return cliente


def usa_turso():
    return bool(TURSO_URL)


def get_conn():
    """Con TURSO_DATABASE_URL + TURSO_AUTH_TOKEN usa la base permanente en la nube;
    sin ellas usa el archivo local reservas.db (para probar en la computadora)."""
    if TURSO_URL:
        return TursoConnection(_nuevo_cliente_turso())
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.executescript(SCHEMA)
    # En el hosting no hay consola para correr seed.py: si se define ADMIN_PIN y todavía
    # no hay PIN guardado, se crea con ese valor (solo se guarda el hash, nunca el PIN).
    pin = os.environ.get("ADMIN_PIN", "").strip()
    if pin and conn.execute("SELECT COUNT(*) AS n FROM admin").fetchone()["n"] == 0:
        from werkzeug.security import generate_password_hash

        conn.execute("INSERT INTO admin (pin_hash) VALUES (?)", (generate_password_hash(pin),))
    conn.commit()
    conn.close()
