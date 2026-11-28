"""Auth payload must distinguish site-wide grants from instance membership."""

from app.extensions import db
from app.models import ROLE_SITE_ADMIN, Membership, UserRole
from app.utils.tenancy import user_payload
from tests.integration.test_tenancy import grant, make_instance, make_user


def test_site_wide_and_scoped_grants_are_separate(app):
    with app.app_context():
        user = make_user("scope@t.test", role=UserRole.USER)
        site_a = make_instance(200, "A")
        site_b = make_instance(201, "B")
        grant(user, site_a, ROLE_SITE_ADMIN)
        db.session.add(
            Membership(user_id=user.id, instance_id=None, role=ROLE_SITE_ADMIN)
        )
        db.session.commit()
        payload = user_payload(user)

        assert payload["is_site_admin"] is True
        assert str(site_a.id) in payload["site_admin_instance_ids"]
        assert str(site_b.id) not in payload["site_admin_instance_ids"]
        assert str(site_a.id) not in payload["admin_instance_ids"]
