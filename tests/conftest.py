import pytest
from app import create_app
from app.extensions import db
from app.models import User


@pytest.fixture(scope="function")
def app():
    """Fresh app + empty :memory: DB per test.

    Session scope once shared one SQLite database across the whole run, so
    hardcoded emails/codes (admin@test.com, IDEA-0001, ...) collided with
    UNIQUE errors depending on test order. Function scope isolates every
    test permanently.
    """
    _app = create_app("testing")
    with _app.app_context():
        db.create_all()
    yield _app
    with _app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture(scope="function")
def celery_app():
    """Fresh app + empty :memory: DB per test (see `app` above)."""
    _app = create_app("testing", init_celery_app=True)
    with _app.app_context():
        db.create_all()
    yield _app
    with _app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture(scope="function")
def user_with_token(app):
    with app.app_context():
        user = User.query.filter_by(email="test@example.com").first()
        if user is None:
            user = User(email="test@example.com")
            user.set_password("password123")
            db.session.add(user)
            db.session.commit()
        tokens = user.get_token()
        return {"email": user.email, "token": tokens["access_token"]}


@pytest.fixture(scope="function")
def auth_headers(user_with_token):
    return {"Authorization": f"Bearer {user_with_token['token']}"}


@pytest.fixture()
def admin_user(app):
    """Ensure an ADMIN user (admin@test.com) exists; return it.

    Several integration tests query this user to own prompts/ideas. Creating
    it here (get-or-create) removes the hidden dependency on test order.
    """
    from app.models import UserRole

    with app.app_context():
        admin = User.query.filter_by(email="admin@test.com").first()
        if admin is None:
            admin = User(email="admin@test.com", role=UserRole.ADMIN)
            admin.set_password("admin123")
            db.session.add(admin)
            db.session.commit()
        return admin


@pytest.fixture()
def admin_prompt(app, admin_user):
    """Ensure a PromptConfig owned by admin@test.com exists; return it.

    Several integration tests query for an admin-owned prompt instead of
    creating one — a hidden dependency on test order. Ensuring it here
    makes each test self-sufficient. (Re-queries the admin in this fixture's
    own session: ORM objects can't cross the nested app contexts used here.)
    """
    from app.models import PromptConfig, User

    with app.app_context():
        admin = User.query.filter_by(email="admin@test.com").first()
        assert admin is not None
        prompt = PromptConfig.query.filter_by(created_by_id=admin.id).first()
        if prompt is None:
            prompt = PromptConfig(
                title="Fixture Prompt",
                prompt_body="Generate an idea about {{topic}}",
                interval_minutes=60,
                model_name="llama3:8b",
                is_active=True,
                created_by_id=admin.id,
            )
            db.session.add(prompt)
            db.session.commit()
        return prompt


@pytest.fixture()
def auth_user(client):
    email = "user@example.com"
    password = "password123"
    res = client.post("/api/v1/register", json={"email": email, "password": password})
    token = res.get_json()["data"]["access_token"]
    return email, token


@pytest.fixture()
def admin_client(client, app):
    """Admin-authenticated test client.

    The integration suite was written against this fixture but it was never
    defined, so every test using it errored at setup. Tests use the
    headers-only JWT config, so the wrapper injects the Authorization
    header on every request (tests call admin_client.get/post directly).
    """
    from app.models import UserRole

    with app.app_context():
        admin = User.query.filter_by(email="admin@example.com").first()
        if admin is None:
            admin = User(email="admin@example.com", role=UserRole.ADMIN)
            admin.set_password("admin123")
            db.session.add(admin)
            db.session.commit()
    login = client.post("/api/v1/login", json={
        "email": "admin@example.com", "password": "admin123"})
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.get_json()['data']['access_token']}"}
    return _AuthHeaderClient(client, headers)


class _AuthHeaderClient:
    """Flask test-client wrapper injecting default auth headers."""

    _METHODS = ("get", "post", "put", "patch", "delete", "head", "options")

    def __init__(self, client, headers):
        self._client = client
        self._headers = dict(headers)

    def _call(self, method, *args, **kwargs):
        headers = dict(self._headers)
        headers.update(kwargs.pop("headers", None) or {})
        return method(*args, headers=headers, **kwargs)

    def __getattr__(self, name):
        if name in self._METHODS:
            method = getattr(self._client, name)
            return lambda *a, **k: self._call(method, *a, **k)
        return getattr(self._client, name)


@pytest.fixture(scope="function")
def client(app):
    return app.test_client()


@pytest.fixture(scope="function")
def session(app):
    with app.app_context():
        db.create_all()
    yield db.session
    with app.app_context():
        db.session.remove()
