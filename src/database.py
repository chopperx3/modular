import sqlite3

# CONEXION
conn = sqlite3.connect('data/textos.db')
c = conn.cursor()

# CREAR TABLA
c.execute('''CREATE TABLE IF NOT EXISTS textos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                imagen TEXT,
                texto EXTRAIDO TEXT
            )''')
conn.commit()
#SALVAR EN BASE DE DATOS
def save_to_db(file_path, extracted_text):
    c.execute("INSERT INTO textos (imagen, texto) VALUES (?, ?)", (file_path, extracted_text))
    conn.commit()

#CERRAR CONEXION AL CERRAR EL PROGRAMA
def close_connection():
    conn.close()
