import 'dart:io';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:http/http.dart' as http;

void main() {
  runApp(const OCRApp());
}

class OCRApp extends StatelessWidget {
  const OCRApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'OCR Modular',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.indigo),
        useMaterial3: true,
      ),
      home: const OCRHome(),
      debugShowCheckedModeBanner: false,
    );
  }
}

class OCRHome extends StatefulWidget {
  const OCRHome({super.key});

  @override
  State<OCRHome> createState() => _OCRHomeState();
}

class _OCRHomeState extends State<OCRHome> {
  final ImagePicker _picker = ImagePicker();
  XFile? _imageFile;
  bool _sending = false;
  String _ocrText = '';
  int? _docTypeId;
  String? _docTypeLabel;

  // Catálogo local (debe corresponder al backend /doc_types)
  final List<Map<String, dynamic>> _docTypes = const [
    {"id": 1, "label": "Apunte"},
    {"id": 2, "label": "Tarea"},
    {"id": 3, "label": "Examen"},
    {"id": 4, "label": "Recibo"},
    {"id": 5, "label": "Carta"},
    {"id": 99, "label": "Otro"},
  ];

  Future<void> _pickImage() async {
    final XFile? picked = await _picker.pickImage(source: ImageSource.gallery);
    if (picked != null) {
      setState(() {
        _imageFile = picked;
        _ocrText = '';
      });
    }
  }

  Future<void> _sendToBackend() async {
    if (_imageFile == null) return;
    if (_docTypeId == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Selecciona un tipo de documento')),
      );
      return;
    }

    setState(() => _sending = true);

    try {
      // Emulador Android → 10.0.2.2
      final uri = Uri.parse('http://10.0.2.2:8000/ocr/');
      final req = http.MultipartRequest('POST', uri);

      req.files.add(await http.MultipartFile.fromPath('file', _imageFile!.path));
      req.fields['doc_type_id'] = _docTypeId.toString();
      req.fields['doc_type_label'] = _docTypeLabel ?? '';

      final resp = await req.send();
      final body = await resp.stream.bytesToString();

      if (resp.statusCode == 200) {
        setState(() => _ocrText = body);
      } else {
        setState(() => _ocrText = 'Error ${resp.statusCode}: $body');
      }
    } catch (e) {
      setState(() => _ocrText = 'Error: $e');
    } finally {
      setState(() => _sending = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final img = _imageFile != null ? Image.file(File(_imageFile!.path), fit: BoxFit.cover) : null;

    return Scaffold(
      appBar: AppBar(
        title: const Text('OCR Modular'),
        centerTitle: true,
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // Card de imagen
          Card(
            elevation: 2,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
            clipBehavior: Clip.antiAlias,
            child: SizedBox(
              height: 220,
              child: img ?? const Center(child: Text('Sin imagen seleccionada')),
            ),
          ),
          const SizedBox(height: 12),
          // Selector de tipo de documento
          DropdownButtonFormField<int>(
            decoration: InputDecoration(
              labelText: 'Tipo de documento',
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
              contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 14),
            ),
            value: _docTypeId,
            items: _docTypes.map((e) {
              return DropdownMenuItem<int>(
                value: e['id'] as int,
                child: Text(e['label'] as String),
              );
            }).toList(),
            onChanged: (val) {
              setState(() {
                _docTypeId = val;
                _docTypeLabel = _docTypes.firstWhere((e) => e['id'] == val)['label'];
              });
            },
          ),
          const SizedBox(height: 12),
          // Botones
          Row(
            children: [
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: _sending ? null : _pickImage,
                  icon: const Icon(Icons.photo_library),
                  label: const Text('Seleccionar imagen'),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: FilledButton.icon(
                  onPressed: _sending ? null : _sendToBackend,
                  icon: _sending ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2)) : const Icon(Icons.send),
                  label: const Text('Enviar'),
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          // Resultado
          Text(
            'Resultado OCR:',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 8),
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: Colors.grey.shade300),
            ),
            child: SelectableText(
              _ocrText.isEmpty ? '— sin resultado —' : _ocrText,
              style: const TextStyle(height: 1.4),
            ),
          ),
        ],
      ),
    );
  }
}
