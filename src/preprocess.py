import cv2
import numpy as np

def preprocess_image(image_path):
    # Leer la imagen en escala de grises
    image = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)

    # Aplicar un filtro Gaussiano para suavizar la imagen y reducir el ruido
    image = cv2.GaussianBlur(image, (5, 5), 0)

    # Convertir la imagen en una imagen binaria
    _, binary_image = cv2.threshold(image, 150, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Ecualizar el histograma de la imagen binaria para mejorar el contraste
    binary_image = cv2.equalizeHist(binary_image)

    # Aplicar la operación de apertura morfológica utilizando un kernel de tamaño 1x1 para eliminar el ruido blanco
    kernel = np.ones((1, 1), np.uint8)
    processed_image = cv2.morphologyEx(binary_image, cv2.MORPH_OPEN, kernel)

    # Retornar la imagen procesada
    return processed_image
