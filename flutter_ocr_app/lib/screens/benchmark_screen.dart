import 'dart:io';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../core/api_client.dart';
import '../models/ocr_result.dart';
import '../widgets/metric_card.dart';

class BenchmarkScreen extends StatefulWidget {
  final ApiClient api;
  const BenchmarkScreen({super.key, required this.api});

  @override
  State<BenchmarkScreen> createState() => _BenchmarkScreenState();
}

class _BenchmarkScreenState extends State<BenchmarkScreen> {
  final _picker = ImagePicker();
  XFile? _image;
  final _gtCtrl = TextEditingController();
  bool _loading = false;
  BenchmarkComparison? _result;
  String? _error;

  @override
  void dispose() {
    _gtCtrl.dispose();
    super.dispose();
  }

  Future<void> _pick() async {
    final img = await _picker.pickImage(source: ImageSource.gallery, maxWidth: 2400, imageQuality: 95);
    if (img != null) setState(() => _image = img);
  }

  Future<void> _run() async {
    final img = _image;
    if (img == null) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Selecciona una imagen primero')));
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
      _result = null;
    });
    try {
      final gt = _gtCtrl.text.trim();
      final res = await widget.api.compareEngines(
        file: File(img.path),
        groundTruth: gt.isEmpty ? null : gt,
      );
      if (!mounted) return;
      setState(() => _result = res);
    } on ApiException catch (e) {
      setState(() => _error = '${e.statusCode}: ${e.message}');
    } catch (e) {
      setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Comparativa OCR')),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Card(
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Sistema MODULAR vs Tesseract',
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'Sube una imagen para evaluar ambos motores. Si proporcionas el texto esperado, se calculan CER, WER y F1.',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                    const SizedBox(height: 14),
                    _ImageSlot(image: _image, onPick: _pick),
                    const SizedBox(height: 12),
                    TextField(
                      controller: _gtCtrl,
                      maxLines: 3,
                      decoration: const InputDecoration(
                        labelText: 'Texto esperado (opcional)',
                        hintText: 'Transcripción de referencia para calcular métricas',
                        prefixIcon: Icon(Icons.text_fields),
                      ),
                    ),
                    const SizedBox(height: 12),
                    SizedBox(
                      height: 48,
                      child: FilledButton.icon(
                        onPressed: _loading || _image == null ? null : _run,
                        icon: _loading
                            ? const SizedBox(
                                width: 16, height: 16,
                                child: CircularProgressIndicator(strokeWidth: 2.4, color: Colors.white))
                            : const Icon(Icons.bolt),
                        label: Text(_loading ? 'Evaluando…' : 'Comparar motores'),
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 16),
            if (_error != null) _ErrorBanner(message: _error!),
            if (_result != null) _ResultsView(result: _result!),
          ],
        ),
      ),
    );
  }
}

class _ImageSlot extends StatelessWidget {
  final XFile? image;
  final VoidCallback onPick;
  const _ImageSlot({required this.image, required this.onPick});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return InkWell(
      onTap: onPick,
      borderRadius: BorderRadius.circular(14),
      child: Container(
        height: 160,
        decoration: BoxDecoration(
          color: scheme.surfaceContainerHighest.withValues(alpha: .4),
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: scheme.outlineVariant),
        ),
        clipBehavior: Clip.hardEdge,
        child: image == null
            ? Center(
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(Icons.add_photo_alternate_outlined, color: scheme.onSurfaceVariant),
                    const SizedBox(height: 6),
                    Text('Seleccionar imagen', style: TextStyle(color: scheme.onSurfaceVariant)),
                  ],
                ),
              )
            : Image.file(File(image!.path), fit: BoxFit.cover, width: double.infinity),
      ),
    );
  }
}

class _ResultsView extends StatelessWidget {
  final BenchmarkComparison result;
  const _ResultsView({required this.result});

  @override
  Widget build(BuildContext context) {
    final eFaster = result.easyocrLatencyMs <= result.tesseractLatencyMs;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (result.groundTruthProvided) ...[
          Text('Métricas comparativas', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          _MetricsTable(result: result),
          const SizedBox(height: 16),
        ],
        Text('Latencia', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        Row(
          children: [
            Expanded(
              child: MetricCard(
                icon: Icons.flash_on,
                label: 'MODULAR (EasyOCR + IA)',
                value: result.easyocrLatencyMs.toStringAsFixed(0),
                unit: 'ms',
                accent: eFaster ? Colors.green : null,
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: MetricCard(
                icon: Icons.timelapse,
                label: 'Tesseract',
                value: result.tesseractLatencyMs.toStringAsFixed(0),
                unit: 'ms',
                accent: !eFaster ? Colors.green : null,
              ),
            ),
          ],
        ),
        const SizedBox(height: 16),
        Text('Texto reconocido', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        _TextBlock(title: 'MODULAR', text: result.easyocrText, color: Colors.blue),
        const SizedBox(height: 8),
        _TextBlock(title: 'Tesseract', text: result.tesseractText, color: Colors.orange),
      ],
    );
  }
}

class _MetricsTable extends StatelessWidget {
  final BenchmarkComparison result;
  const _MetricsTable({required this.result});

  String _pct(double? v) => v == null ? '—' : '${(v * 100).toStringAsFixed(1)}%';
  String _f1(double? v) => v == null ? '—' : v.toStringAsFixed(3);

  Widget _winner(double? a, double? b, {bool lowerIsBetter = true}) {
    if (a == null || b == null) return const SizedBox.shrink();
    final aWin = lowerIsBetter ? a < b : a > b;
    return Icon(
      Icons.emoji_events,
      color: Colors.amber.shade700,
      size: 16,
    );
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(8),
        child: Table(
          columnWidths: const {
            0: FlexColumnWidth(1.4),
            1: FlexColumnWidth(1.4),
            2: FlexColumnWidth(1.4),
          },
          children: [
            TableRow(
              decoration: BoxDecoration(color: scheme.surfaceContainerHighest.withValues(alpha: .5)),
              children: const [
                _Th(text: 'Métrica'),
                _Th(text: 'MODULAR'),
                _Th(text: 'Tesseract'),
              ],
            ),
            TableRow(children: [
              const _Td(text: 'CER ↓'),
              _Td(text: _pct(result.easyocrCer), trailing: _winner(result.easyocrCer, result.tesseractCer)),
              _Td(text: _pct(result.tesseractCer), trailing: _winner(result.tesseractCer, result.easyocrCer)),
            ]),
            TableRow(children: [
              const _Td(text: 'WER ↓'),
              _Td(text: _pct(result.easyocrWer), trailing: _winner(result.easyocrWer, result.tesseractWer)),
              _Td(text: _pct(result.tesseractWer), trailing: _winner(result.tesseractWer, result.easyocrWer)),
            ]),
            TableRow(children: [
              const _Td(text: 'F1 ↑'),
              _Td(text: _f1(result.easyocrF1), trailing: _winner(result.easyocrF1, result.tesseractF1, lowerIsBetter: false)),
              _Td(text: _f1(result.tesseractF1), trailing: _winner(result.tesseractF1, result.easyocrF1, lowerIsBetter: false)),
            ]),
          ],
        ),
      ),
    );
  }
}

class _Th extends StatelessWidget {
  final String text;
  const _Th({required this.text});
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 12),
      child: Text(text, style: const TextStyle(fontWeight: FontWeight.w600)),
    );
  }
}

class _Td extends StatelessWidget {
  final String text;
  final Widget? trailing;
  const _Td({required this.text, this.trailing});
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
      child: Row(
        children: [
          Text(text, style: const TextStyle(fontFeatures: [FontFeature.tabularFigures()])),
          if (trailing != null) ...[
            const SizedBox(width: 6),
            trailing!,
          ],
        ],
      ),
    );
  }
}

class _TextBlock extends StatelessWidget {
  final String title;
  final String text;
  final Color color;
  const _TextBlock({required this.title, required this.text, required this.color});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(width: 8, height: 8, decoration: BoxDecoration(color: color, shape: BoxShape.circle)),
                const SizedBox(width: 8),
                Text(title, style: const TextStyle(fontWeight: FontWeight.w700)),
              ],
            ),
            const SizedBox(height: 8),
            SelectableText(text.isEmpty ? '(sin texto)' : text, style: Theme.of(context).textTheme.bodyMedium),
          ],
        ),
      ),
    );
  }
}

class _ErrorBanner extends StatelessWidget {
  final String message;
  const _ErrorBanner({required this.message});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: scheme.errorContainer,
        borderRadius: BorderRadius.circular(10),
      ),
      child: Row(
        children: [
          Icon(Icons.error_outline, color: scheme.onErrorContainer),
          const SizedBox(width: 8),
          Expanded(child: Text(message, style: TextStyle(color: scheme.onErrorContainer))),
        ],
      ),
    );
  }
}
