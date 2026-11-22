"""Seed a ProductManager test user on instance 90 (idempotent)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db
from app.models import (
    Instance,
    Membership,
    User,
    UserRole,
)

app = create_app(os.getenv("FLASK_ENV", "development"), init_celery_app=False)
with app.app_context():
    inst = Instance.query.filter_by(number=90).first()
    if inst is None:
        print("Instance 90 not found")
        sys.exit(1)
    user = User.query.filter_by(email="ProductManager@test.local").first()
    if user is None:
        user = User(email="ProductManager@test.local", role=UserRole.USER, name="Product Manager")
        user.set_password("pm@test.local")
        db.session.add(user)
        db.session.flush()
    # ensure membership as PRODUCT_MANAGER
    m = Membership.query.filter_by(user_id=user.id, instance_id=inst.id).first()
    if m is None:
        m = Membership(user_id=user.id, instance_id=inst.id, role="PRODUCT_MANAGER")
        db.session.add(m)
    else:
        m.role = "PRODUCT_MANAGER"
    db.session.commit()
    print("Seeded ProductManager@test.local on instance 90")