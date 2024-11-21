import os
from PIL import Image
import pytesseract

# Configura la ruta de Tesseract-OCR aquí
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

def ocr_core(filename):
    """
    Esta función tomará una ruta de archivo de imagen y devolverá el texto
    """
    text = pytesseract.image_to_string(Image.open(filename))
    return text

def save_text_to_file(text, output_path):
    """
    Esta función guardará el texto extraído en un archivo de texto
    """
    with open(output_path, 'w') as f:
        f.write(text)

if __name__ == "__main__":
    # Ruta de la imagen a procesar
    image_path = 'C:\\Users\\belen\\OneDrive\\Escritorio\\modular\\1.jpg'
    # Ruta del archivo de salida
    output_path = 'C:\\Users\\belen\\OneDrive\\Escritorio\\modular\\archivo.txt'

    # Extraer texto de la imagen
    extracted_text = ocr_core(image_path)

    # Guardar el texto en un archivo
    save_text_to_file(extracted_text, output_path)

    print("El texto ha sido extraído y guardado en", output_path)
