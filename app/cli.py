import click
from flask.cli import with_appcontext

from app.extensions import db
from app.models import User, UserRole


@click.command("create-admin")
@click.option("--email", prompt=True, help="Admin email address")
@click.option(
    "--password",
    prompt=True,
    hide_input=True,
    confirmation_prompt=True,
    help="Admin password",
)
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
@click.option(
    "--password",
    prompt=True,
    hide_input=True,
    confirmation_prompt=True,
    help="User password",
)
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
        click.echo(
            f"{user.email} | {user.name} | {user.role.value} | {'Active' if user.is_active else 'Inactive'}"
        )


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
    app.cli.add_command(backup_site)
    app.cli.add_command(backup_instance)
    app.cli.add_command(restore_backup)
    app.cli.add_command(init_tenancy)
    app.cli.add_command(promote_site_admin)
    app.cli.add_command(create_instance)


@click.command("backup-site")
@click.option("--output", required=True, help="Destination .json bundle file")
@with_appcontext
def backup_site(output: str):
    """Export the whole site database to a versioned JSON bundle.

    Encrypted blobs travel as-is: keep the same FERNET_KEY to restore.
    Take this before every upgrade (golden rule).
    """
    from app.services import backup as backup_svc

    try:
        bundle = backup_svc.export_site()
    except Exception as exc:
        from sqlalchemy.exc import OperationalError

        if isinstance(exc, OperationalError):
            raise click.ClickException(
                f"cannot read the database ({exc.orig}); run 'flask db upgrade' first"
            ) from exc
        raise
    backup_svc.write_bundle(bundle, output)
    manifest = bundle["manifest"]
    total = sum(manifest["tables"].values())
    click.echo(
        f"Site backup written to {output}: {total} rows, "
        f"checksum {manifest['checksum'][:16]}…"
    )


@click.command("backup-instance")
@click.option(
    "--instance-id",
    default=None,
    help="Instance to export (per-instance filtering lands in Phase 1)",
)
@click.option("--output", required=True, help="Destination .json bundle file")
@with_appcontext
def backup_instance(instance_id: str | None, output: str):
    """Export one instance to JSON (Phase 0: exports the whole database).

    Per-instance filtering arrives with `instance_id` columns in Phase 1;
    until then this is identical to backup-site and says so in the manifest.
    """
    from app.services import backup as backup_svc

    bundle = backup_svc.export_site()
    backup_svc.rescope_bundle(
        bundle,
        "instance",
        instance_id=instance_id,
        note="Phase 0: whole-database export; per-instance filtering lands in Phase 1",
    )
    backup_svc.write_bundle(bundle, output)
    click.echo(
        f"Instance backup written to {output} (whole-database export; per-instance filtering lands in Phase 1)"
    )


@click.command("restore")
@click.option(
    "--input", "input_path", required=True, help="Bundle .json file to restore"
)
@click.option("--yes", is_flag=True, help="Skip the destructive-action confirmation")
@with_appcontext
def restore_backup(input_path: str, yes: bool):
    """Verify, wipe and re-import a backup bundle. Destructive: confirm first."""
    from app.services import backup as backup_svc

    if not yes:
        click.confirm(
            "Restore wipes ALL current data before re-importing. Continue?", abort=True
        )
    bundle = backup_svc.read_bundle(input_path)
    counts = backup_svc.restore_site(bundle)
    total = sum(counts.values())
    click.echo(
        f"Restored {total} rows from {input_path} "
        f"(schema v{bundle['manifest']['export_schema_version']})"
    )


@click.command("init-tenancy")
@with_appcontext
def init_tenancy():
    """Idempotent first-time tenancy seed.

    Creates Instances 1 (template) + 5 (production), moves all existing
    rows to Site 5, and grants Site 5 memberships from V1 roles. Take a
    backup first; the Site Admin itself comes from promote-site-admin.
    """
    from app.services import instances as instance_svc

    report = instance_svc.init_site_data()
    moved = sum(report["backfilled"].values())
    click.echo(
        f"Tenancy initialised: template={report['template_id']} "
        f"production={report['production_id']}, {moved} rows to Site 5, "
        f"{report['memberships']} memberships granted."
    )


@click.command("promote-site-admin")
@click.argument("email")
@with_appcontext
def promote_site_admin(email: str):
    """Grant a user the site-wide SITE_ADMIN membership."""
    from app.models import User
    from app.services import instances as instance_svc

    user = User.query.filter_by(email=email.strip().lower()).first()
    if not user:
        click.echo(f"User {email} not found.", err=True)
        return
    instance_svc.grant_site_admin(user.id)
    click.echo(f"User {email} is now a site admin")


@click.command("create-instance")
@click.option(
    "--number",
    type=int,
    required=True,
    help="Instance number (>= 20; 1 and 5 exist; 2-19 reserved)",
)
@click.option("--name", required=True, help="Instance display name")
@with_appcontext
def create_instance(number: int, name: str):
    """Create an instance from the Instance 1 template (operator-run)."""
    from app.services import instances as instance_svc

    try:
        instance = instance_svc.create_instance(number, name.strip())
    except instance_svc.InstanceError as exc:
        click.echo(f"Error: {exc}", err=True)
        return
    click.echo(f"Instance created: number={instance.number} id={instance.id}")
