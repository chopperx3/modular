import 'package:flutter_test/flutter_test.dart';

import 'package:flutter_ocr_app/core/api_client.dart';
import 'package:flutter_ocr_app/models/ocr_result.dart';

void main() {
  test('OcrResult.fromJson parsea la respuesta del backend', () {
    final json = {
      'id': 7,
      'filename': 'manuscrita.jpg',
      'estatus': 'Procesado',
      'text': 'Habia una vez',
      'created_at': '2026-05-19T20:00:00',
      'doc_type_id': 3,
      'engine': 'groq',
    };
    final r = OcrResult.fromJson(json);
    expect(r.id, 7);
    expect(r.isProcessed, isTrue);
    expect(r.hasError, isFalse);
    expect(r.engineLabel, 'Llama 4 Scout (IA)');
  });

  test('OcrResult detecta estatus de error', () {
    final r = OcrResult.fromJson({
      'id': 1,
      'filename': 'x.jpg',
      'estatus': 'Error: OCR fallo',
      'text': '',
      'created_at': '2026-05-19T20:00:00',
    });
    expect(r.hasError, isTrue);
    expect(r.isProcessed, isFalse);
  });

  test('ApiClient normaliza la URL base con barra final', () {
    final client = ApiClient('http://10.0.2.2:8000/');
    expect(client.baseUrl, 'http://10.0.2.2:8000/');
    client.close();
  });

  test('BenchmarkComparison.fromJson parsea métricas nulas', () {
    final c = BenchmarkComparison.fromJson({
      'filename': 'x.jpg',
      'easyocr_text': 'a',
      'easyocr_cer': null,
      'easyocr_wer': null,
      'easyocr_f1': null,
      'easyocr_latency_ms': 100.0,
      'tesseract_text': 'b',
      'tesseract_cer': 0.1,
      'tesseract_wer': 0.2,
      'tesseract_f1': 0.9,
      'tesseract_latency_ms': 50.0,
      'ground_truth_provided': false,
    });
    expect(c.easyocrCer, isNull);
    expect(c.tesseractF1, 0.9);
    expect(c.groundTruthProvided, isFalse);
  });
}
