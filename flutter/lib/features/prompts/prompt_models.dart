class PromptSummary {
  PromptSummary({
    required this.id,
    required this.title,
    this.modelName = '',
    this.provider = 'ollama',
    this.isActive = true,
    this.intervalMinutes,
    this.nextRunAt,
  });

  final String id;
  final String title;
  final String modelName;
  final String provider;
  final bool isActive;
  final int? intervalMinutes;
  final String? nextRunAt;

  factory PromptSummary.fromJson(Map<String, dynamic> json) => PromptSummary(
        id: json['id'].toString(),
        title: (json['title'] ?? '').toString(),
        modelName: (json['model_name'] ?? '').toString(),
        provider: (json['provider'] ?? 'ollama').toString(),
        isActive: json['is_active'] as bool? ?? true,
        intervalMinutes: (json['interval_minutes'] as num?)?.toInt(),
        nextRunAt: json['next_run_at']?.toString(),
      );
}
