from PIL import Image
import pytesseract
import cv2
from preprocess import preprocess_image
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

def ocr_core(filename):
    processed_image = preprocess_image(filename)
    # CONVERSION A PIL
    pil_image = Image.fromarray(processed_image)
    custom_config = r'--oem 1 --psm 3'
    text = pytesseract.image_to_string(pil_image, config=custom_config)
    return text

def convert_to_print(text):
    return text.upper()  # CONVERSOR A MAYUSCULAR
