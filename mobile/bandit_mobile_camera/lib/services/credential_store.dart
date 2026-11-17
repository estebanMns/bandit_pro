import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import 'models.dart';

/// Guarda el token del teléfono en Keychain (iOS) o Keystore (Android). Nunca en texto plano.
class CredentialStore {
  CredentialStore([FlutterSecureStorage? storage])
      : _storage = storage ?? const FlutterSecureStorage();

  final FlutterSecureStorage _storage;

  static const _api = 'bandit.api';
  static const _device = 'bandit.device_id';
  static const _token = 'bandit.device_token';

  Future<DeviceCredentials?> read() async {
    final api = await _storage.read(key: _api);
    final device = await _storage.read(key: _device);
    final token = await _storage.read(key: _token);
    if (api == null || device == null || token == null) return null;
    return DeviceCredentials(apiBaseUrl: Uri.parse(api), deviceId: device, token: token);
  }

  Future<void> save(DeviceCredentials credentials) async {
    await _storage.write(key: _api, value: credentials.apiBaseUrl.toString());
    await _storage.write(key: _device, value: credentials.deviceId);
    await _storage.write(key: _token, value: credentials.token);
  }

  Future<void> clear() async {
    await _storage.delete(key: _api);
    await _storage.delete(key: _device);
    await _storage.delete(key: _token);
  }
}
