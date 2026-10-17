"""Unit tests for the messaging module (Phase 4: Talk).

Tests message model, API endpoints, and permissions without external
services.
"""

from app.models import Message, User


def test_message_model_creation(app):
    """Test creating a Message model instance."""
    from app.extensions import db
    from app.models import Instance, Membership

    with app.app_context():
        inst = Instance(number=9902, name="Msg Model Test")
        db.session.add(inst)
        db.session.flush()

        sender = User(email="msg-sender@example.com")
        sender.set_password("password123")
        recipient = User(email="msg-recipient@example.com")
        recipient.set_password("password123")
        db.session.add(sender)
        db.session.add(recipient)
        db.session.flush()

        db.session.add(
            Membership(user_id=sender.id, instance_id=inst.id, role="USER")
        )
        db.session.add(
            Membership(
                user_id=recipient.id,
                instance_id=inst.id,
                role="INSTANCE_ADMIN",
            )
        )
        db.session.commit()

        msg = Message(
            instance_id=inst.id,
            sender_id=sender.id,
            recipient_id=recipient.id,
            body="Hello from the user!",
        )
        db.session.add(msg)
        db.session.commit()

        assert msg.id is not None
        assert msg.sender_id == sender.id
        assert msg.recipient_id == recipient.id
        assert msg.body == "Hello from the user!"
        assert msg.read_at is None
        assert msg.created_at is not None

        # Test to_dict
        d = msg.to_dict()
        assert d["sender_id"] == str(sender.id)
        assert d["recipient_id"] == str(recipient.id)
        assert d["body"] == "Hello from the user!"
        assert d["read_at"] is None


def test_message_with_idea_link(app, client):
    """Test sending a message with an idea link."""
    from app.extensions import db
    from app.models import Instance, Idea, Membership, User

    with app.app_context():
        inst = Instance(number=9903, name="Msg Link Test")
        db.session.add(inst)
        db.session.flush()
        iid = inst.id

        admin = User(email="msg-admin-link@example.com")
        admin.set_password("password123")
        user = User(email="msg-user-link@example.com")
        user.set_password("password123")
        db.session.add(admin)
        db.session.add(user)
        db.session.flush()

        db.session.add(
            Membership(user_id=user.id, instance_id=iid, role="USER")
        )
        db.session.add(
            Membership(user_id=admin.id, instance_id=iid, role="INSTANCE_ADMIN")
        )

        parent = Idea(
            reference_code="IDEA-MSG",
            prompt_title="Test idea",
            raw_content="test",
            status="SCALE",
            instance_id=iid,
        )
        db.session.add(parent)
        db.session.commit()

        pid = str(parent.id)
        aid = str(admin.id)
        uid = str(user.id)

    # Login as user
    res = client.post(
        "/api/v1/login",
        json={"email": "msg-user-link@example.com", "password": "password123", "instance_id": iid},
    )
    assert res.status_code == 200
    user_token = res.get_json()["data"]["access_token"]

    # User sends message to admin with idea link
    res = client.post(
        "/api/v1/messages",
        json={
            "recipient_id": aid,
            "body": "Look at this idea",
            "idea_id": pid,
        },
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert res.status_code == 201, res.get_json()
    msg = res.get_json()["data"]["message"]
    assert msg["idea_id"] == pid
    assert msg["link"] is not None
    assert pid in msg["link"]


def test_message_delete_own(app, client):
    """Test that a user can delete their own sent message."""
    from app.extensions import db
    from app.models import Instance, Membership, User

    with app.app_context():
        inst = Instance(number=9904, name="Msg Delete Test")
        db.session.add(inst)
        db.session.flush()
        iid = inst.id

        admin = User(email="msg-admin-del@example.com")
        admin.set_password("password123")
        user = User(email="msg-user-del@example.com")
        user.set_password("password123")
        db.session.add(admin)
        db.session.add(user)
        db.session.flush()

        db.session.add(
            Membership(user_id=user.id, instance_id=iid, role="USER")
        )
        db.session.add(
            Membership(user_id=admin.id, instance_id=iid, role="INSTANCE_ADMIN")
        )
        db.session.commit()

        uid = str(user.id)
        aid = str(admin.id)

    # Login as user
    res = client.post(
        "/api/v1/login",
        json={"email": "msg-user-del@example.com", "password": "password123", "instance_id": iid},
    )
    assert res.status_code == 200
    user_token = res.get_json()["data"]["access_token"]

    # User sends message to admin
    res = client.post(
        "/api/v1/messages",
        json={"recipient_id": aid, "body": "To be deleted"},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert res.status_code == 201, res.get_json()
    msg_id = res.get_json()["data"]["message"]["id"]

    # User deletes their own message
    res = client.delete(
        f"/api/v1/messages/{msg_id}", headers={"Authorization": f"Bearer {user_token}"}
    )
    assert res.status_code == 200
    assert res.get_json()["data"]["deleted"] == msg_id

    # Verify it's gone from admin's inbox
    res = client.post(
        "/api/v1/login",
        json={"email": "msg-admin-del@example.com", "password": "password123", "instance_id": iid},
    )
    assert res.status_code == 200
    admin_token = res.get_json()["data"]["access_token"]

    res = client.get("/api/v1/messages", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    ids = [m["id"] for m in res.get_json()["data"]["messages"]]
    assert msg_id not in ids


def test_admins_picker(app, client):
    """Test the admin picker endpoint for message composition."""
    from app.extensions import db
    from app.models import Instance, Membership, User

    with app.app_context():
        inst = Instance(number=9905, name="Msg Picker Test")
        db.session.add(inst)
        db.session.flush()
        iid = inst.id

        admin = User(email="msg-admin-pick@example.com")
        admin.set_password("password123")
        user = User(email="msg-user-pick@example.com")
        user.set_password("password123")
        db.session.add(admin)
        db.session.add(user)
        db.session.flush()

        db.session.add(
            Membership(user_id=user.id, instance_id=iid, role="USER")
        )
        db.session.add(
            Membership(user_id=admin.id, instance_id=iid, role="INSTANCE_ADMIN")
        )
        db.session.commit()

        uid = str(user.id)
        aid = str(admin.id)

    # Login as user
    res = client.post(
        "/api/v1/login",
        json={"email": "msg-user-pick@example.com", "password": "password123", "instance_id": iid},
    )
    assert res.status_code == 200
    user_token = res.get_json()["data"]["access_token"]

    # User can see admin in picker
    res = client.get("/api/v1/messages/admins", headers={"Authorization": f"Bearer {user_token}"})
    assert res.status_code == 200
    admins = res.get_json()["data"]["admins"]
    assert len(admins) == 1
    assert admins[0]["id"] == aid