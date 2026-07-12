import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/signal.dart';

class ApiService {
  ApiService({this.baseUrl = 'http://10.0.2.2:8012/api'});

  final String baseUrl;

  Future<Map<String, dynamic>> config() async {
    final response = await http.get(Uri.parse('$baseUrl/config'));
    return _decodeMap(response);
  }

  Future<TradingSignal> generateSignal({
    required String mode,
    required String pair,
    required String duration,
  }) async {
    final response = await http.post(
      Uri.parse('$baseUrl/signals/generate'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'mode': mode, 'pair': pair, 'duration': duration}),
    );
    return TradingSignal.fromJson(_decodeMap(response));
  }

  Future<List<TradingSignal>> scanPairs({
    required String mode,
    required String duration,
  }) async {
    final uri = Uri.parse('$baseUrl/signals/scan').replace(
      queryParameters: {'mode': mode, 'duration': duration},
    );
    final response = await http.post(uri);
    return _decodeList(response).map(TradingSignal.fromJson).toList();
  }

  Future<List<HistoryRecord>> history() async {
    final response = await http.get(Uri.parse('$baseUrl/history?limit=100'));
    return _decodeList(response).map(HistoryRecord.fromJson).toList();
  }

  Future<Map<String, dynamic>> statistics() async {
    final response = await http.get(Uri.parse('$baseUrl/statistics'));
    return _decodeMap(response);
  }

  Map<String, dynamic> _decodeMap(http.Response response) {
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw ApiException(response.body);
    }
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  List<Map<String, dynamic>> _decodeList(http.Response response) {
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw ApiException(response.body);
    }
    return (jsonDecode(response.body) as List)
        .cast<Map<String, dynamic>>();
  }
}

class ApiException implements Exception {
  const ApiException(this.message);
  final String message;

  @override
  String toString() => message;
}
