"""Un proceso con varios hilos: si Turso se demora en una consulta, las demás visitas siguen
atendiéndose. Cada visita abre su propia conexión, así que no se comparte nada entre hilos."""
workers = 1
threads = 8
timeout = 60
graceful_timeout = 20
keepalive = 5
