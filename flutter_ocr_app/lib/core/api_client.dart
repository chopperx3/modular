import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';

import '../models/ocr_result.dart';

class ApiException implements Exception {
  final int statusCode;
  final String message;
  ApiException(this.statusCode, this.message);
  @override
  String toString() => 'ApiException($statusCode): $message';
}

class ApiClient {
  String baseUrl;
  final http.Client _http;

  ApiClient(this.baseUrl, {http.Client? client}) : _http = client ?? http.Client();

  Uri _u(String path, [Map<String, String>? query]) {
    final clean = baseUrl.endsWith('/') ? baseUrl.substring(0, baseUrl.length - 1) : baseUrl;
    return Uri.parse('$clean$path').replace(queryParameters: query);
  }

  Future<Map<String, dynamic>> health() async {
    final r = await _http.get(_u('/health')).timeout(const Duration(seconds: 5));
    if (r.statusCode != 200) throw ApiException(r.statusCode, r.body);
    return json.decode(r.body) as Map<String, dynamic>;
  }

  Future<OcrResult> uploadImage({
    required File file,
    required Set<String> langs,
    required bool handwriting,
    int? docTypeId,
  }) async {
    final uri = _u('/ocr/');
    final req = http.MultipartRequest('POST', uri);

    final bytes = await file.readAsBytes();
    final name  = file.uri.pathSegments.last;
    final ext   = _mimeExt(name);

    req.files.add(http.MultipartFile.fromBytes(
      'file',
      bytes,
      filename: name,
      contentType: MediaType('image', ext),
    ));
    req.fields['lang'] = langs.join(',');
    req.fields['mode'] = handwriting ? 'handwriting' : '';
    if (docTypeId != null) req.fields['doc_type_id'] = docTypeId.toString();

    final streamed = await req.send().timeout(const Duration(minutes: 2));
    final body     = await streamed.stream.bytesToString();

    if (streamed.statusCode != 200) {
      throw ApiException(streamed.statusCode, body);
    }
    return OcrResult.fromJson(json.decode(body) as Map<String, dynamic>);
  }

  Future<List<OcrResult>> listResults({int limit = 50}) async {
    final r = await _http.get(_u('/results', {'limit': '$limit'}));
    if (r.statusCode != 200) throw ApiException(r.statusCode, r.body);
    final data = json.decode(r.body) as List<dynamic>;
    return data.map((e) => OcrResult.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<void> deleteResult(int id) async {
    final r = await _http.delete(_u('/results/$id'));
    if (r.statusCode != 204) throw ApiException(r.statusCode, r.body);
  }

  Future<BenchmarkComparison> compareEngines({
    required File file,
    String? groundTruth,
  }) async {
    final uri = _u('/benchmark/single', groundTruth == null ? null : {'ground_truth': groundTruth});
    final req = http.MultipartRequest('POST', uri);
    final bytes = await file.readAsBytes();
    final name  = file.uri.pathSegments.last;
    req.files.add(http.MultipartFile.fromBytes(
      'file',
      bytes,
      filename: name,
      contentType: MediaType('image', _mimeExt(name)),
    ));

    final streamed = await req.send().timeout(const Duration(minutes: 3));
    final body     = await streamed.stream.bytesToString();
    if (streamed.statusCode != 200) {
      throw ApiException(streamed.statusCode, body);
    }
    return BenchmarkComparison.fromJson(json.decode(body) as Map<String, dynamic>);
  }

  Future<Map<String, dynamic>> benchmarkResults() async {
    final r = await _http.get(_u('/benchmark/results'));
    if (r.statusCode != 200) throw ApiException(r.statusCode, r.body);
    return json.decode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> renew(int resultId, {int? docTypeId}) async {
    final uri = _u('/renew/$resultId', docTypeId == null ? null : {'doc_type_id': '$docTypeId'});
    final r   = await _http.post(uri);
    if (r.statusCode != 200) throw ApiException(r.statusCode, r.body);
    return json.decode(r.body) as Map<String, dynamic>;
  }

  String _mimeExt(String p) {
    final low = p.toLowerCase();
    if (low.endsWith('.png'))  return 'png';
    if (low.endsWith('.webp')) return 'webp';
    if (low.endsWith('.pdf'))  return 'pdf';
    return 'jpeg';
  }

  void close() => _http.close();
}
