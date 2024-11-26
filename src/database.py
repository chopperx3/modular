import sqlite3

# Conectar a la base de datos (o crearla si no existe)
conn = sqlite3.connect('data/textos.db')
c = conn.cursor()

# Crear la tabla si no existe
c.execute('''CREATE TABLE IF NOT EXISTS textos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                imagen TEXT,
                texto EXTRAIDO TEXT
            )''')
conn.commit()

def save_to_db(file_path, extracted_text):
    """
    Guarda el texto extraído en la base de datos
    """
    c.execute("INSERT INTO textos (imagen, texto) VALUES (?, ?)", (file_path, extracted_text))
    conn.commit()

def close_connection():
    """
    Cierra la conexión a la base de datos
    """
    conn.close()
