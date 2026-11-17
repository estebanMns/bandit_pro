import 'package:flutter/material.dart';
import 'package:flutter_webrtc/flutter_webrtc.dart';
import 'package:permission_handler/permission_handler.dart';

/// Prueba local de la cámara: no hay conexión con Bandit y todo se apaga al salir.
class PreviewScreen extends StatefulWidget {
  const PreviewScreen({super.key});

  @override
  State<PreviewScreen> createState() => _PreviewScreenState();
}

class _PreviewScreenState extends State<PreviewScreen> {
  final _renderer = RTCVideoRenderer();
  MediaStream? _stream;
  String? _error;

  @override
  void initState() {
    super.initState();
    _open();
  }

  Future<void> _open() async {
    await _renderer.initialize();
    if (!(await Permission.camera.request()).isGranted) {
      if (mounted) setState(() => _error = 'Sin permiso de cámara.');
      return;
    }
    try {
      final stream = await navigator.mediaDevices.getUserMedia({
        'audio': false,
        'video': {'facingMode': 'environment'},
      });
      _stream = stream;
      _renderer.srcObject = stream;
      if (mounted) setState(() {});
    } catch (error) {
      if (mounted) setState(() => _error = 'No se pudo abrir la cámara: $error');
    }
  }

  @override
  void dispose() {
    final stream = _stream;
    if (stream != null) {
      for (final track in stream.getTracks()) {
        track.stop();
      }
      stream.dispose();
    }
    _renderer.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Probar la cámara')),
      body: _error != null
          ? Center(child: Text(_error!))
          : Stack(
              children: [
                Positioned.fill(child: RTCVideoView(_renderer)),
                const Positioned(
                  top: 12,
                  left: 12,
                  child: Chip(
                    avatar: Icon(Icons.videocam, size: 18, color: Colors.redAccent),
                    label: Text('Cámara activa (solo en este teléfono)'),
                  ),
                ),
              ],
            ),
    );
  }
}
