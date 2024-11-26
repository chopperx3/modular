from PIL import Image
import pytesseract
import cv2
from preprocess import preprocess_image

# Configura la ruta de Tesseract-OCR aquí
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

def ocr_core(filename):
    """
    Esta función tomará una ruta de archivo de imagen, aplicará preprocesamiento y devolverá el texto.
    """
    processed_image = preprocess_image(filename)
    # Convertir la imagen procesada a un formato PIL
    pil_image = Image.fromarray(processed_image)
    custom_config = r'--oem 1 --psm 3'
    text = pytesseract.image_to_string(pil_image, config=custom_config)
    return text

def convert_to_print(text):
    """
    Esta función convierte el texto manuscrito extraído a letra de molde.
    """
    return text.upper()  # Ejemplo simple que convierte el texto a mayúsculas
