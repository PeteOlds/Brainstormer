import click
from flask.cli import with_appcontext
from app.extensions import db
from app.models import User, UserRole


@click.command("create-admin")
@click.option("--email", prompt=True, help="Admin email address")
@click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True, help="Admin password")
@click.option("--name", prompt=True, help="Admin name")
@with_appcontext
def create_admin(email: str, password: str, name: str):
    """Create an admin user."""
    # Check if user already exists
    existing = User.query.filter_by(email=email).first()
    if existing:
        click.echo(f"User with email {email} already exists.", err=True)
        return

    user = User(email=email, name=name, role=UserRole.ADMIN)
    user.set_password(password)
    
    db.session.add(user)
    db.session.commit()
    
    click.echo(f"Admin user created: {email}")


@click.command("create-user")
@click.option("--email", prompt=True, help="User email address")
@click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True, help="User password")
@click.option("--name", prompt=True, help="User name")
@with_appcontext
def create_user(email: str, password: str, name: str):
    """Create a regular user."""
    existing = User.query.filter_by(email=email).first()
    if existing:
        click.echo(f"User with email {email} already exists.", err=True)
        return

    user = User(email=email, name=name, role=UserRole.USER)
    user.set_password(password)
    
    db.session.add(user)
    db.session.commit()
    
    click.echo(f"User created: {email}")


@click.command("list-users")
@with_appcontext
def list_users():
    """List all users."""
    users = User.query.all()
    for user in users:
        click.echo(f"{user.email} | {user.name} | {user.role.value} | {'Active' if user.is_active else 'Inactive'}")


@click.command("promote-user")
@click.argument("email")
@with_appcontext
def promote_user(email: str):
    """Promote a user to admin."""
    user = User.query.filter_by(email=email).first()
    if not user:
        click.echo(f"User {email} not found.", err=True)
        return
    
    user.role = UserRole.ADMIN
    db.session.commit()
    click.echo(f"User {email} promoted to admin")


def register_cli(app):
    """Register CLI commands with the Flask app."""
    app.cli.add_command(create_admin)
    app.cli.add_command(create_user)
    app.cli.add_command(list_users)
    app.cli.add_command(promote_user)