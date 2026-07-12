# Android Mobile App

This Flutter client connects to the FastAPI backend.

For an Android emulator, the default API base URL is:

```text
http://10.0.2.2:8012/api
```

For a physical Android phone, replace `baseUrl` in `lib/services/api_service.dart` with your computer LAN IP, for example:

```text
http://192.168.1.20:8012/api
```

Run:

```bash
flutter pub get
flutter run
```
