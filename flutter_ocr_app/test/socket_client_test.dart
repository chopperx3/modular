import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:flutter_ocr_app/core/socket_client.dart';

void main() {
  test('wsUri convierte la URL HTTP del API al endpoint WebSocket', () {
    final c = OcrSocketClient(baseUrl: 'http://192.168.1.50:8000/', clientId: 'app-1', device: 'Pixel A');
    expect(c.wsUri.toString(), 'ws://192.168.1.50:8000/ws/ocr?client_id=app-1&device=Pixel+A');
    c.updateConfig(baseUrl: 'https://ocr.example.com');
    expect(c.wsUri.scheme, 'wss');
    c.dispose();
  });

  final server = Platform.environment['WS_TEST_URL'];
  test('envía, sobrevive a una caída de red y recupera el resultado', () async {
    final c = OcrSocketClient(baseUrl: server!, clientId: 'flutter-${randomId(3)}', device: 'test');
    final stages = <String>[];
    c.connect();
    final future = c.submit(
      file: File('../manuscrita.jpg'),
      langs: {'es', 'en'},
      handwriting: true,
      onProgress: stages.add,
    );
    await Future.delayed(const Duration(milliseconds: 600));
    c.simulateNetworkDrop();
    final result = await future.timeout(const Duration(seconds: 20));
    expect(result.id, greaterThan(0));
    expect(c.reconnects, 1);
    expect(stages, contains('waiting_connection'));
    expect(c.log.any((l) => l.text.startsWith('resume')), isTrue);
    c.dispose();
  }, skip: server == null ? 'Define WS_TEST_URL=http://host:puerto para la prueba contra el backend' : false);
}
