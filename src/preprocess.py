import cv2
import numpy as np

def preprocess_image(image_path):
    image = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)

    # Aplicar suavizado gaussiano para reducir ruido
    image = cv2.GaussianBlur(image, (5, 5), 0)

    # Aplicar binarización (umbralización)
    _, binary_image = cv2.threshold(image, 150, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Ajustar contraste utilizando ecualización del histograma
    binary_image = cv2.equalizeHist(binary_image)

    # Eliminar ruido mediante apertura
    kernel = np.ones((1, 1), np.uint8)
    processed_image = cv2.morphologyEx(binary_image, cv2.MORPH_OPEN, kernel)

    return processed_image
