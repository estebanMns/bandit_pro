import 'dart:async';

import 'package:flutter_webrtc/flutter_webrtc.dart';
import 'package:http/http.dart' as http;

import 'models.dart';

enum PublishState { idle, capturing, connecting, live, reconnecting, failed, stopped }

class PublishException implements Exception {
  PublishException(this.message);
  final String message;

  @override
  String toString() => message;
}

/// Publica cámara y micrófono en MediaMTX por WHIP (HTTP + SDP), con el ticket del backend.
///
/// La captura empieza solo cuando la persona aceptó la sesión en pantalla, y [stop] apaga
/// todas las pistas: cámara y micrófono quedan libres al terminar.
class WhipPublisher {
  WhipPublisher({http.Client? client}) : _client = client ?? http.Client();

  final http.Client _client;
  final _state = StreamController<PublishState>.broadcast();

  MediaStream? localStream;
  RTCPeerConnection? _peer;
  Uri? _resource;
  String? _token;
  PublishState _current = PublishState.idle;
  bool _frontCamera = false;

  Stream<PublishState> get states => _state.stream;
  PublishState get state => _current;
  bool get hasAudio => (localStream?.getAudioTracks().isNotEmpty ?? false);

  void _set(PublishState value) {
    _current = value;
    if (!_state.isClosed) _state.add(value);
  }

  /// Abre cámara (y micrófono si se autorizó). Muestra la vista previa antes de conectar.
  Future<MediaStream> startCapture({required bool audio, bool frontCamera = false}) async {
    _frontCamera = frontCamera;
    localStream = await navigator.mediaDevices.getUserMedia({
      'audio': audio
          ? {'echoCancellation': true, 'noiseSuppression': true}
          : false,
      'video': {
        'facingMode': frontCamera ? 'user' : 'environment',
        // Resolución moderada: menos ancho de banda y menos costo de análisis.
        'width': {'ideal': 1280},
        'height': {'ideal': 720},
        'frameRate': {'ideal': 20, 'max': 25},
      },
    });
    _set(PublishState.capturing);
    return localStream!;
  }

  Future<void> switchCamera() async {
    final tracks = localStream?.getVideoTracks() ?? const [];
    if (tracks.isEmpty) return;
    await Helper.switchCamera(tracks.first);
    _frontCamera = !_frontCamera;
  }

  bool get frontCamera => _frontCamera;

  /// Negocia con MediaMTX. Si ya había una conexión, la reemplaza (reconexión).
  Future<void> publish(MediaGrant grant) async {
    final stream = localStream;
    if (stream == null) throw PublishException('La cámara no está abierta.');
    await _closePeer();
    _set(_current == PublishState.live ? PublishState.reconnecting : PublishState.connecting);
    _token = grant.token;

    final peer = await createPeerConnection({
      'iceServers': grant.iceServers,
      'sdpSemantics': 'unified-plan',
      'bundlePolicy': 'max-bundle',
    });
    _peer = peer;
    for (final track in stream.getTracks()) {
      await peer.addTransceiver(
        track: track,
        kind: track.kind == 'audio'
            ? RTCRtpMediaType.RTCRtpMediaTypeAudio
            : RTCRtpMediaType.RTCRtpMediaTypeVideo,
        init: RTCRtpTransceiverInit(direction: TransceiverDirection.SendOnly, streams: [stream]),
      );
    }
    peer.onConnectionState = (state) {
      switch (state) {
        case RTCPeerConnectionState.RTCPeerConnectionStateConnected:
          _set(PublishState.live);
        case RTCPeerConnectionState.RTCPeerConnectionStateDisconnected:
          if (_current == PublishState.live) _set(PublishState.reconnecting);
        case RTCPeerConnectionState.RTCPeerConnectionStateFailed:
          _set(PublishState.failed);
        default:
          break;
      }
    };

    final offer = await peer.createOffer();
    await peer.setLocalDescription(offer);
    await _waitForIce(peer);
    final local = await peer.getLocalDescription();

    final response = await _client
        .post(
          grant.url,
          headers: {
            'Content-Type': 'application/sdp',
            'Authorization': 'Bearer ${grant.token}',
          },
          body: local?.sdp ?? offer.sdp,
        )
        .timeout(const Duration(seconds: 15));
    if (response.statusCode != 201) {
      _set(PublishState.failed);
      throw PublishException(
        response.statusCode == 401
            ? 'El servidor de video rechazó el permiso de esta sesión.'
            : 'El servidor de video respondió ${response.statusCode}.',
      );
    }
    final location = response.headers['location'];
    _resource = location == null ? null : grant.url.resolve(location);
    await peer.setRemoteDescription(RTCSessionDescription(response.body, 'answer'));
  }

  Future<void> _waitForIce(RTCPeerConnection peer) async {
    if (peer.iceGatheringState == RTCIceGatheringState.RTCIceGatheringStateComplete) return;
    final done = Completer<void>();
    peer.onIceGatheringState = (state) {
      if (state == RTCIceGatheringState.RTCIceGatheringStateComplete && !done.isCompleted) {
        done.complete();
      }
    };
    // Sin trickle ICE: se espera un momento a reunir candidatos (incluidos los de TURN).
    await done.future.timeout(const Duration(seconds: 4), onTimeout: () {});
  }

  void setMicrophoneEnabled(bool enabled) {
    for (final track in localStream?.getAudioTracks() ?? const <MediaStreamTrack>[]) {
      track.enabled = enabled;
    }
  }

  Future<void> _closePeer() async {
    final resource = _resource;
    final token = _token;
    _resource = null;
    if (resource != null && token != null) {
      try {
        await _client
            .delete(resource, headers: {'Authorization': 'Bearer $token'})
            .timeout(const Duration(seconds: 5));
      } catch (_) {
        // MediaMTX libera la ruta solo cuando la conexión se cae.
      }
    }
    await _peer?.close();
    _peer = null;
  }

  /// Apaga todo: conexión, pistas de cámara y micrófono.
  Future<void> stop() async {
    await _closePeer();
    final stream = localStream;
    localStream = null;
    if (stream != null) {
      for (final track in stream.getTracks()) {
        await track.stop();
      }
      await stream.dispose();
    }
    _set(PublishState.stopped);
  }

  Future<void> dispose() async {
    await stop();
    await _state.close();
    _client.close();
  }
}
