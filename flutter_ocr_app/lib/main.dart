import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';
import 'package:image_picker/image_picker.dart';

void main() => runApp(const OCRApp());

class OCRApp extends StatelessWidget {
  const OCRApp({super.key});
  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'MODULAR OCR',
      theme: ThemeData(brightness: Brightness.dark, useMaterial3: true),
      home: const OcrHome(),
    );
  }
}

class OcrHome extends StatefulWidget {
  const OcrHome({super.key});
  @override
  State<OcrHome> createState() => _OcrHomeState();
}

class _OcrHomeState extends State<OcrHome> {
  final ImagePicker _picker = ImagePicker();
  XFile? _image;

  // Ajusta tu URL por defecto
  String _baseUrl = 'http://10.0.2.2:8000'; // Android emulator -> localhost
  bool _handwriting = false;
  final Set<String> _langs = {'es', 'en'};
  int? _docTypeId; // null = sin clasificar

  bool _loading = false;
  Map<String, dynamic>? _lastJson;
  String? _lastText;

  Future<void> _pick(ImageSource src) async {
    final img = await _picker.pickImage(source: src, maxWidth: 2400, imageQuality: 95);
    if (img != null) setState(() => _image = img);
  }

  String _mimeFromPath(String p) {
    final ext = p.toLowerCase();
    if (ext.endsWith('.png')) return 'png';
    if (ext.endsWith('.jpg') || ext.endsWith('.jpeg')) return 'jpeg';
    if (ext.endsWith('.webp')) return 'webp';
    return 'jpeg';
  }

  Future<void> _send() async {
    if (_image == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Primero selecciona una imagen')),
      );
      return;
    }
    setState(() {
      _loading = true;
      _lastJson = null;
      _lastText = null;
    });

    final uri = Uri.parse('$_baseUrl/ocr');
    final req = http.MultipartRequest('POST', uri);

    final fileBytes = await _image!.readAsBytes();
    final fname = _image!.name;
    final ext = _mimeFromPath(fname);

    req.files.add(http.MultipartFile.fromBytes(
      'file',
      fileBytes,
      filename: fname,
      contentType: MediaType('image', ext),
    ));

    req.fields['lang'] = _langs.join(',');
    req.fields['mode'] = _handwriting ? 'handwriting' : '';
    if (_docTypeId != null) req.fields['doc_type_id'] = _docTypeId.toString();

    try {
      final resp = await req.send();
      final body = await resp.stream.bytesToString();
      if (!mounted) return;

      if (resp.statusCode == 200) {
        final jsonMap = json.decode(body) as Map<String, dynamic>;
        setState(() {
          _lastJson = jsonMap;
          _lastText = (jsonMap['text'] ?? '') as String;
        });
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Error ${resp.statusCode}: $body')),
        );
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Fallo en la petición: $e')),
      );
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final img = _image;

    return Scaffold(
      appBar: AppBar(title: const Text('MODULAR OCR')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // API URL
          TextField(
            decoration: const InputDecoration(
              labelText: 'URL de la API (http://host:8000)',
              border: OutlineInputBorder(),
            ),
            controller: TextEditingController(text: _baseUrl),
            onSubmitted: (v) => setState(() => _baseUrl = v.trim()),
          ),
          const SizedBox(height: 12),

          // Idiomas
          Wrap(
            spacing: 8,
            children: [
              FilterChip(
                label: const Text('ES'),
                selected: _langs.contains('es'),
                onSelected: (v) => setState(() {
                  v ? _langs.add('es') : _langs.remove('es');
                }),
              ),
              FilterChip(
                label: const Text('EN'),
                selected: _langs.contains('en'),
                onSelected: (v) => setState(() {
                  v ? _langs.add('en') : _langs.remove('en');
                }),
              ),
            ],
          ),
          const SizedBox(height: 12),

          // Modo manuscrita
          SwitchListTile(
            title: const Text('Manuscrita'),
            value: _handwriting,
            onChanged: (v) => setState(() => _handwriting = v),
          ),

          // Tipo de documento
          DropdownButtonFormField<int>(
            decoration: const InputDecoration(
              labelText: 'Tipo de documento (opcional)',
              border: OutlineInputBorder(),
            ),
            value: _docTypeId,
            items: const [
              DropdownMenuItem(value: null, child: Text('— Sin clasificar —')),
              DropdownMenuItem(value: 1, child: Text('Factura/Recibo')),
              DropdownMenuItem(value: 2, child: Text('Identificación')),
              DropdownMenuItem(value: 3, child: Text('Examen')),
              DropdownMenuItem(value: 4, child: Text('Carta/Oficio')),
            ],
            onChanged: (v) => setState(() => _docTypeId = v),
          ),
          const SizedBox(height: 12),

          // Imagen
          AspectRatio(
            aspectRatio: 16 / 9,
            child: DecoratedBox(
              decoration: BoxDecoration(
                border: Border.all(color: theme.colorScheme.outlineVariant),
                borderRadius: BorderRadius.circular(12),
              ),
              child: img == null
                  ? const Center(child: Text('Sin imagen'))
                  : ClipRRect(
                      borderRadius: BorderRadius.circular(12),
                      child: Image.file(
                        File(img.path),
                        fit: BoxFit.contain,
                      ),
                    ),
            ),
          ),
          const SizedBox(height: 12),

          // Botones
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              FilledButton.icon(
                onPressed: _loading ? null : () => _pick(ImageSource.gallery),
                icon: const Icon(Icons.photo_library),
                label: const Text('Galería'),
              ),
              FilledButton.icon(
                onPressed: _loading ? null : () => _pick(ImageSource.camera),
                icon: const Icon(Icons.photo_camera),
                label: const Text('Cámara'),
              ),
              FilledButton.tonalIcon(
                onPressed: _loading ? null : _send,
                icon: const Icon(Icons.cloud_upload),
                label: _loading ? const Text('Procesando...') : const Text('Enviar a OCR'),
              ),
            ],
          ),
          const SizedBox(height: 16),

          if (_lastText != null) ...[
            Text('Texto detectado', style: theme.textTheme.titleMedium),
            const SizedBox(height: 8),
            SelectableText(_lastText!, style: theme.textTheme.bodyLarge),
            const SizedBox(height: 16),
          ],

          if (_lastJson != null) ...[
            Text('Respuesta JSON', style: theme.textTheme.titleMedium),
            const SizedBox(height: 8),
            SelectableText(const JsonEncoder.withIndent('  ').convert(_lastJson)),
          ],
        ],
      ),
    );
  }
}
