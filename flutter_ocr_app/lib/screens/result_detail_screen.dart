import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:intl/intl.dart';

import '../core/api_client.dart';
import '../models/ocr_result.dart';
import '../widgets/status_chip.dart';

class ResultDetailScreen extends StatefulWidget {
  final ApiClient api;
  final OcrResult result;
  final Duration? elapsed;
  final String? imagePath;
  const ResultDetailScreen({
    super.key,
    required this.api,
    required this.result,
    this.elapsed,
    this.imagePath,
  });

  @override
  State<ResultDetailScreen> createState() => _ResultDetailScreenState();
}

class _ResultDetailScreenState extends State<ResultDetailScreen> {
  bool _renewing = false;
  Map<String, dynamic>? _renewed;

  Future<void> _renew() async {
    setState(() => _renewing = true);
    try {
      final res = await widget.api.renew(widget.result.id, docTypeId: widget.result.docTypeId);
      if (!mounted) return;
      setState(() => _renewed = res);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Documento renovado generado')),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Error: $e')));
    } finally {
      if (mounted) setState(() => _renewing = false);
    }
  }

  void _copy() {
    Clipboard.setData(ClipboardData(text: widget.result.text));
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Texto copiado al portapapeles')),
    );
  }

  @override
  Widget build(BuildContext context) {
    final r = widget.result;
    final scheme = Theme.of(context).colorScheme;
    final dateFmt = DateFormat('dd MMM yyyy, HH:mm:ss');

    return Scaffold(
      appBar: AppBar(
        title: Text(r.filename, overflow: TextOverflow.ellipsis),
        actions: [
          IconButton(onPressed: _copy, icon: const Icon(Icons.copy), tooltip: 'Copiar texto'),
        ],
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            if (widget.imagePath != null && File(widget.imagePath!).existsSync())
              ClipRRect(
                borderRadius: BorderRadius.circular(14),
                child: Image.file(File(widget.imagePath!), fit: BoxFit.cover),
              ),
            if (widget.imagePath != null) const SizedBox(height: 12),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: [
                        r.hasError
                            ? StatusChip.error(r.estatus)
                            : (r.isProcessed
                                ? StatusChip.ok('Procesado')
                                : StatusChip.warn(r.estatus)),
                        StatusChip.neutral('ID #${r.id}'),
                        if (r.engineLabel != null)
                          (r.engine == 'groq'
                              ? StatusChip.ok(r.engineLabel!)
                              : (r.engine!.contains('fallback')
                                  ? StatusChip.warn(r.engineLabel!)
                                  : StatusChip.neutral(r.engineLabel!))),
                        if (widget.elapsed != null)
                          StatusChip.neutral('${widget.elapsed!.inMilliseconds} ms'),
                      ],
                    ),
                    const SizedBox(height: 10),
                    Row(
                      children: [
                        Icon(Icons.schedule, size: 14, color: scheme.onSurfaceVariant),
                        const SizedBox(width: 4),
                        Text(
                          dateFmt.format(r.createdAt.toLocal()),
                          style: TextStyle(color: scheme.onSurfaceVariant, fontSize: 12),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 16),
            Text('Texto detectado', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: SelectableText(
                  r.text.isEmpty ? '(sin texto)' : r.text,
                  style: Theme.of(context).textTheme.bodyLarge,
                ),
              ),
            ),
            const SizedBox(height: 16),
            FilledButton.tonalIcon(
              onPressed: _renewing ? null : _renew,
              icon: _renewing
                  ? const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.refresh),
              label: Text(_renewing ? 'Generando documento…' : 'Renovar documento (.docx)'),
            ),
            if (_renewed != null) ...[
              const SizedBox(height: 12),
              Card(
                color: scheme.tertiaryContainer.withValues(alpha: .3),
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text('Documento generado', style: TextStyle(fontWeight: FontWeight.w600)),
                      const SizedBox(height: 4),
                      Text('${widget.api.baseUrl}${_renewed!['url_docx']}', style: const TextStyle(fontSize: 12)),
                      const SizedBox(height: 4),
                      Text('${widget.api.baseUrl}${_renewed!['url_txt']}', style: const TextStyle(fontSize: 12)),
                    ],
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
