"""Multi-instance membership."""

import pytest

from app.extensions import db
from app.models import Instance, Membership, User, UserRole


def _two_instances(app):
    with app.app_context():
        u = User.query.filter_by(email="multi@example.com").first()
        if u is None:
            u = User(email="multi@example.com", role=UserRole.USER)
            u.set_password("password123")
            db.session.add(u)
            db.session.commit()
        i1 = Instance.query.filter_by(number=201).first()
        if i1 is None:
            i1 = Instance(number=201, name="Instance A")
            db.session.add(i1)
            db.session.flush()
        i2 = Instance.query.filter_by(number=202).first()
        if i2 is None:
            i2 = Instance(number=202, name="Instance B")
            db.session.add(i2)
            db.session.flush()
        for inst in (i1, i2):
            if Membership.query.filter_by(user_id=u.id, instance_id=inst.id).first() is None:
                db.session.add(Membership(user_id=u.id, instance_id=inst.id, role="USER"))
        db.session.commit()
        return str(u.id), str(i1.id), str(i2.id)


def _login(client, email="multi@example.com", instance_id=None):
    body = {"email": email, "password": "password123"}
    if instance_id:
        body["instance_id"] = instance_id
    res = client.post("/api/v1/login", json=body)
    assert res.status_code == 200, res.get_json()
    data = res.get_json()["data"]
    return data, {"Authorization": f"Bearer {data['access_token']}"}


def test_me_instances_lists_memberships(app, client):
    _two_instances(app)
    data, headers = _login(client)
    res = client.get("/api/v1/me/instances", headers=headers)
    assert res.status_code == 200
    insts = res.get_json()["data"]["instances"]
    assert len(insts) == 2
    numbers = {i["number"] for i in insts}
    assert numbers == {201, 202}


def test_switch_instance_issues_scoped_token(app, client):
    _, i1, i2 = _two_instances(app)
    data, headers = _login(client, instance_id=i1)
    assert data.get("instances") is not None

    res = client.post("/api/v1/switch-instance", json={"instance_id": i2}, headers=headers)
    assert res.status_code == 200, res.get_json()
    new_token = res.get_json()["data"]["access_token"]

    # The new token is scoped to instance 2.
    import jwt

    claims = jwt.decode(new_token, app.config["JWT_SECRET_KEY"], algorithms=["HS256"])
    assert claims["instance_id"] == i2

    # Switching to an instance the user is NOT a member of is refused.
    res = client.post("/api/v1/switch-instance", json={"instance_id": "00000000-0000-0000-0000-000000000000"}, headers=headers)
    assert res.status_code == 403


def test_login_returns_instances_when_multiple(app, client):
    _two_instances(app)
    res = client.post("/api/v1/login", json={"email": "multi@example.com", "password": "password123"})
    assert res.status_code == 200
    assert len(res.get_json()["data"]["instances"]) == 2


def test_add_and_remove_member(app, client):
    _, i1, _ = _two_instances(app)
    # site admin
    with app.app_context():
        from app.models import User, UserRole, Membership
        admin = User.query.filter_by(email="siteadmin@example.com").first()
        if admin is None:
            admin = User(email="siteadmin@example.com", role=UserRole.ADMIN)
            admin.set_password("password123")
            db.session.add(admin)
            db.session.commit()
        # grant site admin
        if Membership.query.filter_by(user_id=admin.id, instance_id=None, role="SITE_ADMIN").first() is None:
            db.session.add(Membership(user_id=admin.id, instance_id=None, role="SITE_ADMIN"))
            db.session.commit()
    _, admin_headers = _login(client, email="siteadmin@example.com")

    # add a new user
    with app.app_context():
        newu = User.query.filter_by(email="newbie@example.com").first()
        if newu is None:
            newu = User(email="newbie@example.com", role=UserRole.USER)
            newu.set_password("password123")
            db.session.add(newu)
            db.session.commit()

    res = client.post(f"/api/v1/instances/{i1}/members", json={"email": "newbie@example.com", "role": "USER"}, headers=admin_headers)
    assert res.status_code == 201, res.get_json()

    # duplicate
    res = client.post(f"/api/v1/instances/{i1}/members", json={"email": "newbie@example.com"}, headers=admin_headers)
    assert res.status_code == 409

    # remove
    with app.app_context():
        from app.models import User
        uid = str(User.query.filter_by(email="newbie@example.com").one().id)
    res = client.delete(f"/api/v1/instances/{i1}/members/{uid}", headers=admin_headers)
    assert res.status_code == 200