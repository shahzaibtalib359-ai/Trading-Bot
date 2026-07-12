class TradingSignal {
  const TradingSignal({
    required this.mode,
    required this.pair,
    required this.currentPrice,
    required this.signal,
    required this.confidence,
    required this.duration,
    required this.marketTrend,
    required this.status,
    required this.analysis,
    required this.generatedAt,
    required this.disclaimer,
  });

  final String mode;
  final String pair;
  final double currentPrice;
  final String signal;
  final int confidence;
  final String duration;
  final String marketTrend;
  final String status;
  final List<String> analysis;
  final DateTime generatedAt;
  final String disclaimer;

  factory TradingSignal.fromJson(Map<String, dynamic> json) {
    return TradingSignal(
      mode: json['mode'] as String,
      pair: json['pair'] as String,
      currentPrice: (json['current_price'] as num).toDouble(),
      signal: json['signal'] as String,
      confidence: json['confidence'] as int,
      duration: json['duration'] as String,
      marketTrend: json['market_trend'] as String,
      status: json['status'] as String,
      analysis: List<String>.from(json['analysis'] as List),
      generatedAt: DateTime.parse(json['generated_at'] as String),
      disclaimer: json['disclaimer'] as String,
    );
  }
}

class HistoryRecord {
  const HistoryRecord({
    required this.id,
    required this.createdAt,
    required this.pair,
    required this.signal,
    required this.confidence,
    required this.duration,
    required this.marketTrend,
    this.outcome,
  });

  final int id;
  final DateTime createdAt;
  final String pair;
  final String signal;
  final int confidence;
  final String duration;
  final String marketTrend;
  final String? outcome;

  factory HistoryRecord.fromJson(Map<String, dynamic> json) {
    return HistoryRecord(
      id: json['id'] as int,
      createdAt: DateTime.parse(json['created_at'] as String),
      pair: json['pair'] as String,
      signal: json['signal'] as String,
      confidence: json['confidence'] as int,
      duration: json['duration'] as String,
      marketTrend: json['market_trend'] as String,
      outcome: json['outcome'] as String?,
    );
  }
}
