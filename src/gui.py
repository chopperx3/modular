from tkinter import Tk, Label, Button, filedialog, Text
from ocr import ocr_core
from database import save_to_db

def upload_image(output_text):
    file_path = filedialog.askopenfilename()
    if file_path:
        extracted_text = ocr_core(file_path)
        output_text.delete(1.0, "end")
        output_text.insert("end", extracted_text)
        save_to_db(file_path, extracted_text)

def create_gui():
    # Configuración de la interfaz gráfica
    root = Tk()
    root.title("OCR - Extractor de Texto")

    # Etiqueta de instrucciones
    label = Label(root, text="Sube una imagen para extraer el texto:")
    label.pack()

    # Botón para subir imagen
    upload_button = Button(root, text="Subir Imagen", command=lambda: upload_image(output_text))
    upload_button.pack()

    # Área de texto para mostrar el texto extraído
    output_text = Text(root, height=20, width=50)
    output_text.pack()

    return root
