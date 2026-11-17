import 'dart:convert';

import 'package:bandit_mobile_camera/services/models.dart';
import 'package:flutter_test/flutter_test.dart';

String qr(Map<String, Object?> changes) => jsonEncode({
      'v': 1,
      'type': 'bandit-mobile-camera',
      'api': 'https://bandit.example',
      'pairing_id': '7b0c5d9e-0000-4000-8000-000000000001',
      'code': 'codigo-temporal-de-prueba-1234',
      'expires_at': '2026-11-17T05:05:00+00:00',
      ...changes,
    });

void main() {
  group('PairingQr', () {
    test('lee un QR válido de Bandit', () {
      final parsed = PairingQr.parse(qr({}));
      expect(parsed.apiBaseUrl.host, 'bandit.example');
      expect(parsed.isExpired(DateTime.utc(2026, 11, 17, 5, 4)), isFalse);
      expect(parsed.isExpired(DateTime.utc(2026, 11, 17, 5, 5)), isTrue);
    });

    test('rechaza QR ajenos, incompletos o de otra versión', () {
      expect(() => PairingQr.parse('https://otra-cosa'), throwsA(isA<InvalidQrException>()));
      expect(() => PairingQr.parse(qr({'type': 'otro'})), throwsA(isA<InvalidQrException>()));
      expect(() => PairingQr.parse(qr({'v': 2})), throwsA(isA<InvalidQrException>()));
      expect(() => PairingQr.parse(qr({'code': null})), throwsA(isA<InvalidQrException>()));
    });

    test('exige HTTPS salvo en pruebas locales', () {
      final local = qr({'api': 'http://192.168.1.10:8080'});
      expect(() => PairingQr.parse(local), throwsA(isA<InvalidQrException>()));
      expect(PairingQr.parse(local, allowInsecureHttp: true).apiBaseUrl.port, 8080);
    });
  });

  test('el WebSocket usa wss con HTTPS', () {
    final credentials = DeviceCredentials(
      apiBaseUrl: Uri.parse('https://bandit.example'),
      deviceId: 'id',
      token: 'bmc_x',
    );
    expect(credentials.websocketUrl().toString(), 'wss://bandit.example/ws/mobile-cameras/device');
  });

  test('lee una solicitud de sesión', () {
    final request = SessionRequest.fromMessage({
      'type': 'mobile_camera.session_requested',
      'session_id': 's1',
      'requested_by': 'duena@example.com',
      'audio_requested': true,
      'answer_by': '2026-11-17T05:01:30+00:00',
      'expires_at': '2026-11-17T05:15:00+00:00',
    });
    expect(request.requestedBy, 'duena@example.com');
    expect(request.audioRequested, isTrue);
  });

  test('estados de sesión', () {
    expect(SessionStatus.fromWire('awaiting_device'), SessionStatus.awaitingDevice);
    expect(SessionStatus.fromWire('live').isOpen, isTrue);
    expect(SessionStatus.fromWire('rejected').isOpen, isFalse);
  });
}
