import 'dart:convert';

import 'package:http/http.dart' as http;

import 'models.dart';

class BanditApiException implements Exception {
  BanditApiException(this.statusCode, this.message);

  final int statusCode;
  final String message;

  bool get isUnauthorized => statusCode == 401;

  @override
  String toString() => message;
}

/// Cliente HTTP del teléfono. Toda petición autenticada usa el token del dispositivo.
class BanditApi {
  BanditApi(this.baseUrl, {this.token, http.Client? client})
      : _client = client ?? http.Client();

  final Uri baseUrl;
  String? token;
  final http.Client _client;

  static const _timeout = Duration(seconds: 15);

  Uri _uri(String path) => baseUrl.replace(path: path);

  Map<String, String> get _headers => {
        'Content-Type': 'application/json',
        if (token != null) 'Authorization': 'Bearer $token',
      };

  Future<Map<String, dynamic>> _send(
    String method,
    String path, [
    Map<String, dynamic>? body,
  ]) async {
    final request = http.Request(method, _uri(path))..headers.addAll(_headers);
    if (body != null) request.body = jsonEncode(body);
    final streamed = await _client.send(request).timeout(_timeout);
    final response = await http.Response.fromStream(streamed);
    if (response.statusCode >= 400) {
      throw BanditApiException(response.statusCode, _detail(response));
    }
    if (response.statusCode == 204 || response.body.isEmpty) return const {};
    return jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
  }

  String _detail(http.Response response) {
    try {
      final body = jsonDecode(utf8.decode(response.bodyBytes));
      if (body is Map && body['detail'] is String) return body['detail'] as String;
    } on FormatException {
      // Respuesta sin JSON: se usa el mensaje genérico.
    }
    return 'El servidor respondió ${response.statusCode}. Inténtalo otra vez.';
  }

  /// Completa la vinculación con el código del QR y devuelve las credenciales del teléfono.
  Future<DeviceCredentials> register(
    PairingQr qr, {
    required String deviceName,
    required String platform,
  }) async {
    final body = await _send('POST', '/api/mobile-cameras/register', {
      'pairing_id': qr.pairingId,
      'code': qr.code,
      'device_name': deviceName,
      'platform': platform,
    });
    return DeviceCredentials(
      apiBaseUrl: baseUrl,
      deviceId: body['device_id'] as String,
      token: body['device_token'] as String,
    );
  }

  Future<DeviceInfo> me() async =>
      DeviceInfo.fromJson(await _send('GET', '/api/mobile-device/me'));

  Future<DeviceInfo> setAvailability(bool available) async => DeviceInfo.fromJson(
        await _send('PATCH', '/api/mobile-device/availability', {'available': available}),
      );

  Future<AcceptedSession> accept(String sessionId, {required bool audio}) async =>
      AcceptedSession.fromJson(
        await _send('POST', '/api/mobile-camera-sessions/$sessionId/accept', {
          'audio': audio,
          'video': true,
        }),
      );

  Future<void> reject(String sessionId) =>
      _send('POST', '/api/mobile-camera-sessions/$sessionId/reject');

  Future<MediaGrant> renewPublish(String sessionId) async => MediaGrant.fromJson(
        await _send('POST', '/api/mobile-camera-sessions/$sessionId/publish-ticket'),
      );

  /// state: live | reconnecting | failed
  Future<void> reportState(String sessionId, String state) =>
      _send('POST', '/api/mobile-camera-sessions/$sessionId/state', {'state': state});

  Future<void> stop(String sessionId) =>
      _send('POST', '/api/mobile-device/sessions/$sessionId/stop');

  Future<String> rotateToken() async =>
      (await _send('POST', '/api/mobile-device/token'))['device_token'] as String;

  Future<void> unpair() => _send('DELETE', '/api/mobile-device');

  void close() => _client.close();
}
