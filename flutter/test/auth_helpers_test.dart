import 'package:brainstormer/core/auth_helpers.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('instance-scoped admin checks', () {
    test('legacy ADMIN role is allowed', () {
      final user = <String, dynamic>{'role': 'ADMIN'};
      expect(currentUserCanAdminInstance(user, 'site-90'), isTrue);
    });

    test('site-wide grant alone does not unlock an instance', () {
      final user = <String, dynamic>{
        'role': 'USER',
        'is_site_admin': true,
        'admin_instance_ids': <String>[],
      };
      expect(currentUserCanAdminInstance(user, 'site-90'), isFalse);
    });

    test('scoped admin and site-admin memberships work only for that site', () {
      final user = <String, dynamic>{
        'role': 'USER',
        'admin_instance_ids': ['site-1'],
        'site_admin_instance_ids': ['site-2'],
      };
      expect(currentUserCanAdminInstance(user, 'site-1'), isTrue);
      expect(currentUserCanAdminInstance(user, 'site-2'), isTrue);
      expect(currentUserCanAdminInstance(user, 'site-90'), isFalse);
    });
  });

  group('prompts visibility', () {
    test('standard user cannot see prompts', () {
      final user = <String, dynamic>{'role': 'USER'};
      expect(currentUserCanViewPrompts(user, 'site-90'), isFalse);
    });

    test('product manager for the selected instance can see prompts', () {
      final user = <String, dynamic>{
        'role': 'USER',
        'product_manager_instance_ids': ['site-90'],
      };
      expect(currentUserCanViewPrompts(user, 'site-90'), isTrue);
      expect(currentUserCanViewPrompts(user, 'site-91'), isFalse);
    });
  });
}
