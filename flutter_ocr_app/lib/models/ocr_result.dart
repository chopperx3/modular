class OcrResult {
  final int id;
  final String filename;
  final String estatus;
  final String text;
  final DateTime createdAt;
  final int? docTypeId;
  final String? engine;

  const OcrResult({
    required this.id,
    required this.filename,
    required this.estatus,
    required this.text,
    required this.createdAt,
    this.docTypeId,
    this.engine,
  });

  factory OcrResult.fromJson(Map<String, dynamic> json) {
    return OcrResult(
      id: json['id'] as int,
      filename: (json['filename'] ?? '') as String,
      estatus: (json['estatus'] ?? '') as String,
      text: (json['text'] ?? '') as String,
      createdAt: DateTime.tryParse(json['created_at']?.toString() ?? '') ?? DateTime.now(),
      docTypeId: json['doc_type_id'] as int?,
      engine: json['engine'] as String?,
    );
  }

  bool get isProcessed => estatus.toLowerCase() == 'procesado';
  bool get hasError    => estatus.toLowerCase().startsWith('error');

  String? get engineLabel {
    if (engine == null) return null;
    if (engine == 'groq') return 'Llama 4 Scout (IA)';
    if (engine!.contains('fallback')) return 'EasyOCR (fallback)';
    return 'EasyOCR';
  }
}

class BenchmarkComparison {
  final String filename;
  final String easyocrText;
  final double? easyocrCer;
  final double? easyocrWer;
  final double? easyocrF1;
  final double easyocrLatencyMs;
  final String tesseractText;
  final double? tesseractCer;
  final double? tesseractWer;
  final double? tesseractF1;
  final double tesseractLatencyMs;
  final bool groundTruthProvided;

  const BenchmarkComparison({
    required this.filename,
    required this.easyocrText,
    required this.easyocrCer,
    required this.easyocrWer,
    required this.easyocrF1,
    required this.easyocrLatencyMs,
    required this.tesseractText,
    required this.tesseractCer,
    required this.tesseractWer,
    required this.tesseractF1,
    required this.tesseractLatencyMs,
    required this.groundTruthProvided,
  });

  factory BenchmarkComparison.fromJson(Map<String, dynamic> j) {
    double? n(dynamic v) => v == null ? null : (v as num).toDouble();
    return BenchmarkComparison(
      filename: (j['filename'] ?? '') as String,
      easyocrText: (j['easyocr_text'] ?? '') as String,
      easyocrCer: n(j['easyocr_cer']),
      easyocrWer: n(j['easyocr_wer']),
      easyocrF1: n(j['easyocr_f1']),
      easyocrLatencyMs: (j['easyocr_latency_ms'] as num).toDouble(),
      tesseractText: (j['tesseract_text'] ?? '') as String,
      tesseractCer: n(j['tesseract_cer']),
      tesseractWer: n(j['tesseract_wer']),
      tesseractF1: n(j['tesseract_f1']),
      tesseractLatencyMs: (j['tesseract_latency_ms'] as num).toDouble(),
      groundTruthProvided: (j['ground_truth_provided'] ?? false) as bool,
    );
  }
}
