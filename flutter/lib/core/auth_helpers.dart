bool currentUserIsAdmin(Map<String, dynamic>? user) {
  if (user == null) return false;
  final role = user['role'] as String?;
  if (role == 'ADMIN') return true;
  if (user['is_site_admin'] == true) return true;
  final adminIds = user['admin_instance_ids'];
  if (adminIds is List && adminIds.isNotEmpty) return true;
  return false;
}

bool _hasId(dynamic value, String instanceId) {
  if (value is! List) return false;
  return value.any((id) => id?.toString() == instanceId);
}

/// Admin rights for one selected instance only. A NULL-instance site-wide
/// grant deliberately does not unlock instance data (D-01).
bool currentUserCanAdminInstance(
  Map<String, dynamic>? user,
  String? instanceId,
) {
  if (user == null) return false;
  if (user['role']?.toString() == 'ADMIN') return true;
  if (instanceId == null || instanceId.isEmpty) return false;
  return _hasId(user['admin_instance_ids'], instanceId) ||
      _hasId(user['site_admin_instance_ids'], instanceId);
}

/// Prompts are available to instance admins and product managers of the
/// selected instance.
bool currentUserCanViewPrompts(
  Map<String, dynamic>? user,
  String? instanceId,
) {
  if (currentUserCanAdminInstance(user, instanceId)) return true;
  return instanceId != null &&
      _hasId(user?['product_manager_instance_ids'], instanceId);
}
