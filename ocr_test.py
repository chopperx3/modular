from PIL import Image
import pytesseract

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

img = Image.open("manuscrita.jpg")
texto = pytesseract.image_to_string(img, lang="eng")
print("Texto detectado:\n", texto)
