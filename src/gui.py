from tkinter import Tk, Label, Button, filedialog, Text
from ocr import ocr_core, convert_to_print
from database import save_to_db

def upload_images(output_text):
    file_paths = filedialog.askopenfilenames()
    if file_paths:
        output_text.delete(1.0, "end")
        for file_path in file_paths:
            extracted_text = ocr_core(file_path)
            formatted_text = convert_to_print(extracted_text)
            output_text.insert("end", f"{formatted_text}\n\n")
            save_to_db(file_path, formatted_text)

def create_gui():
    # Configuración de la interfaz gráfica
    root = Tk()
    root.title("OCR - Extractor de Texto")

    # Etiqueta de instrucciones
    label = Label(root, text="Sube una o varias imágenes para extraer el texto:")
    label.pack()

    # Botón para subir imágenes
    upload_button = Button(root, text="Subir Imágenes", command=lambda: upload_images(output_text))
    upload_button.pack()

    # Área de texto para mostrar el texto extraído
    output_text = Text(root, height=20, width=50)
    output_text.pack()

    return root
