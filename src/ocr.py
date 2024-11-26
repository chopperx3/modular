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
