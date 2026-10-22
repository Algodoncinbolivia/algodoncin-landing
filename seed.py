"""Uso: python seed.py — configura el PIN de administradora para /admin."""
from werkzeug.security import generate_password_hash

from db import get_conn, init_db

if __name__ == "__main__":
    init_db()
    pin = input("PIN de administradora para ver/gestionar reservas: ").strip()
    if pin:
        conn = get_conn()
        conn.execute("DELETE FROM admin")
        conn.execute("INSERT INTO admin (pin_hash) VALUES (?)", (generate_password_hash(pin),))
        conn.commit()
        conn.close()
        print("Listo. Ejecuta 'python app.py' para iniciar el sitio.")
