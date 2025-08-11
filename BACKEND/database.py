from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import sqlite3

# Conexión a SQLite
engine = create_engine("sqlite:///oc_results.db", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class OCRResult(Base):
    __tablename__ = "ocr_results"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    extracted_text = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

    # Nuevas columnas para el tipo de documento
    doc_type_id = Column(Integer, nullable=True)
    doc_type_label = Column(String, nullable=True)

# Crear tabla (si no existe)
Base.metadata.create_all(bind=engine)

# Migración ligera (añade columnas si faltan)
def _ensure_columns():
    conn = sqlite3.connect("oc_results.db")
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(ocr_results)")
    cols = {row[1] for row in cur.fetchall()}

    if "doc_type_id" not in cols:
        cur.execute("ALTER TABLE ocr_results ADD COLUMN doc_type_id INTEGER")
    if "doc_type_label" not in cols:
        cur.execute("ALTER TABLE ocr_results ADD COLUMN doc_type_label TEXT")

    conn.commit()
    conn.close()

_ensure_columns()