from PIL import Image
import pytesseract

# Reemplaza esta ruta con la que copiaste EXACTAMENTE
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

img = Image.open("manuscrita.jpg")  # Cambia por tu imagen real
texto = pytesseract.image_to_string(img, lang="eng")
print("Texto detectado:\n", texto)
