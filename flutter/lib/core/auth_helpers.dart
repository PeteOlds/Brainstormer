bool currentUserIsAdmin(Map<String, dynamic>? user) {
  if (user == null) return false;
  final role = user['role'] as String?;
  if (role == 'ADMIN') return true;
  if (user['is_site_admin'] == true) return true;
  final adminIds = user['admin_instance_ids'];
  if (adminIds is List && adminIds.isNotEmpty) return true;
  return false;
}
