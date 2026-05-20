import 'dart:io';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../core/api_client.dart';
import '../core/settings.dart';
import '../models/ocr_result.dart';
import 'result_detail_screen.dart';

class CaptureScreen extends StatefulWidget {
  final ApiClient api;
  final AppSettings settings;
  const CaptureScreen({super.key, required this.api, required this.settings});

  @override
  State<CaptureScreen> createState() => _CaptureScreenState();
}

class _CaptureScreenState extends State<CaptureScreen> {
  final _picker = ImagePicker();
  XFile? _image;
  bool _loading = false;
  int? _docTypeId;
  Duration? _lastDuration;

  static const _docTypes = [
    DropdownMenuItem<int?>(value: null, child: Text('— Sin clasificar —')),
    DropdownMenuItem<int?>(value: 1, child: Text('Factura / Recibo')),
    DropdownMenuItem<int?>(value: 2, child: Text('Identificación')),
    DropdownMenuItem<int?>(value: 3, child: Text('Examen')),
    DropdownMenuItem<int?>(value: 4, child: Text('Carta / Oficio')),
  ];

  Future<void> _pick(ImageSource src) async {
    final img = await _picker.pickImage(source: src, maxWidth: 2400, imageQuality: 95);
    if (img != null) setState(() => _image = img);
  }

  Future<void> _send() async {
    final img = _image;
    if (img == null) {
      _snack('Primero selecciona una imagen');
      return;
    }
    setState(() => _loading = true);
    final stop = Stopwatch()..start();
    try {
      final result = await widget.api.uploadImage(
        file: File(img.path),
        langs: widget.settings.langs,
        handwriting: widget.settings.handwriting,
        docTypeId: _docTypeId,
      );
      stop.stop();
      if (!mounted) return;
      setState(() => _lastDuration = stop.elapsed);
      Navigator.of(context).push(MaterialPageRoute(
        builder: (_) => ResultDetailScreen(
          api: widget.api,
          result: result,
          elapsed: stop.elapsed,
          imagePath: img.path,
        ),
      ));
    } on ApiException catch (e) {
      _snack('Error ${e.statusCode}: ${_short(e.message)}');
    } catch (e) {
      _snack('Fallo en la petición: $e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _snack(String msg) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
  }

  String _short(String s) => s.length > 100 ? '${s.substring(0, 100)}…' : s;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(
        title: const Text('MODULAR OCR'),
        actions: [
          AnimatedBuilder(
            animation: widget.settings,
            builder: (_, __) => Padding(
              padding: const EdgeInsets.only(right: 12),
              child: Center(
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                  decoration: BoxDecoration(
                    color: widget.settings.handwriting
                        ? scheme.tertiaryContainer
                        : scheme.secondaryContainer,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(
                    widget.settings.handwriting ? 'Manuscrita' : 'Impresa',
                    style: TextStyle(
                      color: widget.settings.handwriting
                          ? scheme.onTertiaryContainer
                          : scheme.onSecondaryContainer,
                      fontWeight: FontWeight.w600,
                      fontSize: 12,
                    ),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            _ImagePreview(image: _image, onClear: () => setState(() => _image = null)),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: FilledButton.tonalIcon(
                    onPressed: _loading ? null : () => _pick(ImageSource.camera),
                    icon: const Icon(Icons.photo_camera_outlined),
                    label: const Text('Cámara'),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: FilledButton.tonalIcon(
                    onPressed: _loading ? null : () => _pick(ImageSource.gallery),
                    icon: const Icon(Icons.photo_library_outlined),
                    label: const Text('Galería'),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Opciones de procesamiento',
                      style: Theme.of(context).textTheme.titleSmall,
                    ),
                    const SizedBox(height: 12),
                    AnimatedBuilder(
                      animation: widget.settings,
                      builder: (_, __) => SwitchListTile(
                        contentPadding: EdgeInsets.zero,
                        title: const Text('Modo manuscrita'),
                        subtitle: const Text('Usa Llama 4 Scout Vision'),
                        value: widget.settings.handwriting,
                        onChanged: (v) => widget.settings.setHandwriting(v),
                      ),
                    ),
                    const Divider(height: 8),
                    const SizedBox(height: 8),
                    Text(
                      'Idiomas',
                      style: Theme.of(context).textTheme.labelMedium?.copyWith(
                            color: scheme.onSurfaceVariant,
                          ),
                    ),
                    const SizedBox(height: 8),
                    AnimatedBuilder(
                      animation: widget.settings,
                      builder: (_, __) => Wrap(
                        spacing: 8,
                        children: [
                          for (final code in const ['es', 'en'])
                            FilterChip(
                              label: Text(code.toUpperCase()),
                              selected: widget.settings.langs.contains(code),
                              onSelected: (_) => widget.settings.toggleLang(code),
                            ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 12),
                    DropdownButtonFormField<int?>(
                      value: _docTypeId,
                      decoration: const InputDecoration(
                        labelText: 'Tipo de documento (opcional)',
                        prefixIcon: Icon(Icons.category_outlined),
                      ),
                      items: _docTypes,
                      onChanged: (v) => setState(() => _docTypeId = v),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 16),
            SizedBox(
              height: 56,
              child: FilledButton.icon(
                onPressed: _loading || _image == null ? null : _send,
                icon: _loading
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2.4, color: Colors.white),
                      )
                    : const Icon(Icons.cloud_upload_outlined),
                label: Text(
                  _loading ? 'Procesando…' : 'Procesar imagen',
                  style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
                ),
              ),
            ),
            if (_lastDuration != null && !_loading) ...[
              const SizedBox(height: 8),
              Center(
                child: Text(
                  'Último procesamiento: ${_lastDuration!.inMilliseconds} ms',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _ImagePreview extends StatelessWidget {
  final XFile? image;
  final VoidCallback onClear;
  const _ImagePreview({required this.image, required this.onClear});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return AspectRatio(
      aspectRatio: 4 / 3,
      child: Container(
        decoration: BoxDecoration(
          color: scheme.surfaceContainerHighest.withValues(alpha: .5),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: scheme.outlineVariant),
        ),
        clipBehavior: Clip.hardEdge,
        child: Stack(
          fit: StackFit.expand,
          children: [
            if (image == null)
              Center(
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(Icons.image_outlined, size: 64, color: scheme.onSurfaceVariant),
                    const SizedBox(height: 12),
                    Text(
                      'Selecciona o captura una imagen',
                      style: TextStyle(color: scheme.onSurfaceVariant),
                    ),
                  ],
                ),
              )
            else
              Image.file(File(image!.path), fit: BoxFit.contain),
            if (image != null)
              Positioned(
                top: 8,
                right: 8,
                child: IconButton.filled(
                  style: IconButton.styleFrom(backgroundColor: Colors.black54),
                  onPressed: onClear,
                  icon: const Icon(Icons.close, color: Colors.white),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
