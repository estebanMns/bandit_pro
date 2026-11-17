/// Modelos compartidos por la app: QR de vinculación, credenciales, sesiones y tickets.
library;

import 'dart:convert';

const qrType = 'bandit-mobile-camera';
const qrVersion = 1;

class InvalidQrException implements Exception {
  InvalidQrException(this.message);
  final String message;

  @override
  String toString() => message;
}

/// Contenido del QR que genera Bandit web. El código es temporal y de un solo uso.
class PairingQr {
  PairingQr({
    required this.apiBaseUrl,
    required this.pairingId,
    required this.code,
    required this.expiresAt,
  });

  final Uri apiBaseUrl;
  final String pairingId;
  final String code;
  final DateTime expiresAt;

  bool isExpired(DateTime now) => !now.isBefore(expiresAt);

  static PairingQr parse(String raw, {bool allowInsecureHttp = false}) {
    Object? decoded;
    try {
      decoded = jsonDecode(raw);
    } on FormatException {
      throw InvalidQrException('Este código QR no es de Bandit.');
    }
    if (decoded is! Map<String, dynamic> || decoded['type'] != qrType) {
      throw InvalidQrException('Este código QR no es de Bandit.');
    }
    if (decoded['v'] != qrVersion) {
      throw InvalidQrException('Actualiza la app: el QR usa otra versión.');
    }
    final api = Uri.tryParse('${decoded['api'] ?? ''}');
    final pairingId = decoded['pairing_id'];
    final code = decoded['code'];
    final expiresAt = DateTime.tryParse('${decoded['expires_at'] ?? ''}');
    if (api == null ||
        !api.hasAuthority ||
        pairingId is! String ||
        code is! String ||
        expiresAt == null) {
      throw InvalidQrException('El código QR está incompleto.');
    }
    // Las credenciales del teléfono solo viajan cifradas, salvo en pruebas de red local.
    if (api.scheme != 'https' && !(allowInsecureHttp && api.scheme == 'http')) {
      throw InvalidQrException('El servidor de Bandit debe usar HTTPS.');
    }
    return PairingQr(
      apiBaseUrl: api,
      pairingId: pairingId,
      code: code,
      expiresAt: expiresAt,
    );
  }
}

/// Lo que el teléfono guarda en el almacenamiento seguro del sistema tras vincularse.
class DeviceCredentials {
  DeviceCredentials({
    required this.apiBaseUrl,
    required this.deviceId,
    required this.token,
  });

  final Uri apiBaseUrl;
  final String deviceId;
  final String token;

  Uri websocketUrl() {
    final scheme = apiBaseUrl.scheme == 'https' ? 'wss' : 'ws';
    return apiBaseUrl.replace(scheme: scheme, path: '/ws/mobile-cameras/device');
  }
}

enum SessionStatus {
  requested,
  awaitingDevice,
  accepted,
  connecting,
  live,
  reconnecting,
  rejected,
  ended,
  failed,
  expired;

  static SessionStatus fromWire(String value) => switch (value) {
        'requested' => requested,
        'awaiting_device' => awaitingDevice,
        'accepted' => accepted,
        'connecting' => connecting,
        'live' => live,
        'reconnecting' => reconnecting,
        'rejected' => rejected,
        'ended' => ended,
        'failed' => failed,
        _ => expired,
      };

  bool get isOpen =>
      this != rejected && this != ended && this != failed && this != expired;
}

/// Solicitud de transmisión que llega por el WebSocket del teléfono.
class SessionRequest {
  SessionRequest({
    required this.sessionId,
    required this.requestedBy,
    required this.audioRequested,
    required this.answerBy,
    required this.expiresAt,
  });

  final String sessionId;
  final String requestedBy;
  final bool audioRequested;
  final DateTime answerBy;
  final DateTime expiresAt;

  factory SessionRequest.fromMessage(Map<String, dynamic> message) => SessionRequest(
        sessionId: message['session_id'] as String,
        requestedBy: (message['requested_by'] as String?) ?? 'Bandit',
        audioRequested: (message['audio_requested'] as bool?) ?? false,
        answerBy: DateTime.parse(message['answer_by'] as String),
        expiresAt: DateTime.parse(message['expires_at'] as String),
      );
}

/// Ticket temporal para publicar por WHIP en MediaMTX.
class MediaGrant {
  MediaGrant({
    required this.url,
    required this.token,
    required this.expiresIn,
    required this.iceServers,
  });

  final Uri url;
  final String token;
  final int expiresIn;
  final List<Map<String, dynamic>> iceServers;

  factory MediaGrant.fromJson(Map<String, dynamic> json) => MediaGrant(
        url: Uri.parse(json['url'] as String),
        token: json['token'] as String,
        expiresIn: (json['expires_in'] as num).toInt(),
        iceServers: [
          for (final server in (json['ice_servers'] as List<dynamic>))
            Map<String, dynamic>.from(server as Map),
        ],
      );
}

class AcceptedSession {
  AcceptedSession({required this.audioEnabled, required this.publish});

  final bool audioEnabled;
  final MediaGrant publish;

  factory AcceptedSession.fromJson(Map<String, dynamic> json) => AcceptedSession(
        audioEnabled:
            ((json['session'] as Map<String, dynamic>)['audio_enabled'] as bool?) ?? false,
        publish: MediaGrant.fromJson(json['publish'] as Map<String, dynamic>),
      );
}

class DeviceInfo {
  DeviceInfo({
    required this.id,
    required this.name,
    required this.platform,
    required this.isAvailable,
    required this.status,
  });

  final String id;
  final String name;
  final String platform;
  final bool isAvailable;
  final String status;

  factory DeviceInfo.fromJson(Map<String, dynamic> json) => DeviceInfo(
        id: json['id'] as String,
        name: json['name'] as String,
        platform: json['platform'] as String,
        isAvailable: json['is_available'] as bool,
        status: json['status'] as String,
      );
}
