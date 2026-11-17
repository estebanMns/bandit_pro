import 'package:flutter/material.dart';

import '../features/pairing/pairing_screen.dart';
import '../features/sessions/home_screen.dart';
import '../services/credential_store.dart';
import '../services/models.dart';

const _noche = Color(0xFF101D42);
const _sodio = Color(0xFFFFB000);

class BanditMobileCameraApp extends StatelessWidget {
  const BanditMobileCameraApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Bandit Mobile Camera',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: _sodio,
          brightness: Brightness.dark,
          surface: _noche,
        ),
        useMaterial3: true,
      ),
      home: const AppGate(),
    );
  }
}

/// Decide si el teléfono ya está vinculado o hay que escanear el QR.
class AppGate extends StatefulWidget {
  const AppGate({super.key});

  @override
  State<AppGate> createState() => _AppGateState();
}

class _AppGateState extends State<AppGate> {
  final _store = CredentialStore();
  DeviceCredentials? _credentials;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final credentials = await _store.read();
    if (!mounted) return;
    setState(() {
      _credentials = credentials;
      _loading = false;
    });
  }

  Future<void> _paired(DeviceCredentials credentials) async {
    await _store.save(credentials);
    if (mounted) setState(() => _credentials = credentials);
  }

  Future<void> _unpaired() async {
    await _store.clear();
    if (mounted) setState(() => _credentials = null);
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    final credentials = _credentials;
    if (credentials == null) return PairingScreen(onPaired: _paired);
    return HomeScreen(
      key: ValueKey(credentials.deviceId),
      credentials: credentials,
      onUnpaired: _unpaired,
      onTokenRotated: (token) => _paired(
        DeviceCredentials(
          apiBaseUrl: credentials.apiBaseUrl,
          deviceId: credentials.deviceId,
          token: token,
        ),
      ),
    );
  }
}
