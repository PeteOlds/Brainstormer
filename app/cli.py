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
    app.cli.add_command(restore_instance)
    app.cli.add_command(init_tenancy)
    app.cli.add_command(promote_site_admin)
    app.cli.add_command(create_instance)
    app.cli.add_command(set_entitlement)
    app.cli.add_command(provision_proxy_key)


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
    required=True,
    help="Instance number or UUID to export (real per-instance filtering)",
)
@click.option("--output", required=True, help="Destination .json bundle file")
@with_appcontext
def backup_instance(instance_id: str, output: str):
    """Export one instance to JSON (rows, members, configs — no sessions)."""
    from app.services import backup as backup_svc

    try:
        bundle = backup_svc.export_instance(_resolve_instance_id(instance_id))
    except (backup_svc.BackupIntegrityError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    backup_svc.write_bundle(bundle, output)
    manifest = bundle["manifest"]
    total = sum(manifest["tables"].values())
    click.echo(
        f"Instance {manifest.get('instance_number')} backup written to {output}: "
        f"{total} rows, checksum {manifest['checksum'][:16]}…"
    )


def _resolve_instance_id(raw: str):
    """Accept an instance number or UUID, returning the UUID."""
    import uuid as uuid_mod

    from app.models import Instance

    try:
        number = int(raw)
    except (TypeError, ValueError):
        number = None
    if number is not None:
        instance = Instance.query.filter_by(number=number).first()
    else:
        try:
            instance = Instance.query.get(uuid_mod.UUID(str(raw)))
        except (ValueError, TypeError, AttributeError):
            instance = None
    if instance is None:
        raise ValueError(f"Unknown instance: {raw}.")
    return instance.id


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


@click.command("restore-instance")
@click.option("--input", "input_path", required=True, help="Instance bundle .json file")
@click.option("--yes", is_flag=True, help="Skip the destructive-action confirmation")
@with_appcontext
def restore_instance(input_path: str, yes: bool):
    """Restore one instance bundle (other instances untouched)."""
    from app.services import backup as backup_svc

    if not yes:
        click.confirm(
            "Restore replaces ALL rows of the bundled instance. Continue?",
            abort=True,
        )
    try:
        bundle = backup_svc.read_bundle(input_path)
        counts = backup_svc.restore_instance(bundle)
    except (backup_svc.BackupIntegrityError, backup_svc.BackupVersionError) as exc:
        raise click.ClickException(str(exc)) from exc
    total = sum(counts.values())
    click.echo(
        f"Restored instance {bundle['manifest'].get('instance_number')}: "
        f"{total} rows from {input_path}"
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


@click.command("set-entitlement")
@click.option(
    "--instance", "instance_ref", required=True, help="Instance number or UUID"
)
@click.option("--key", required=True, help="Entitlement key (e.g. hosted_ai)")
@click.option("--grant/--revoke", default=True, help="Grant or revoke")
@with_appcontext
def set_entitlement(instance_ref: str, key: str, grant: bool):
    """Grant or revoke a billing entitlement (operator-run, billing manual)."""
    from app.models import ENTITLEMENTS, Instance, InstanceEntitlement

    try:
        iid = _resolve_instance_id(instance_ref)
    except ValueError as exc:
        click.echo(f"Error: {exc}", err=True)
        return
    if key not in ENTITLEMENTS:
        click.echo(f"Error: key must be one of {', '.join(ENTITLEMENTS)}.", err=True)
        return
    from app.extensions import db

    row = InstanceEntitlement.query.filter_by(instance_id=iid, key=key).first()
    if row is None:
        row = InstanceEntitlement(instance_id=iid, key=key)
        db.session.add(row)
    row.granted = grant
    db.session.commit()
    click.echo(
        f"Entitlement {key} {'granted' if grant else 'revoked'} for instance {iid}"
    )


@click.command("provision-proxy-key")
@click.option(
    "--instance", "instance_ref", required=True, help="Instance number or UUID"
)
@click.option(
    "--provider", required=True, help="Provider with a stored API key (e.g. openai)"
)
@click.option(
    "--models", required=True, help="Comma-separated litellm model ids for the key"
)
@with_appcontext
def provision_proxy_key(instance_ref: str, provider: str, models: str):
    """Issue a LiteLLM virtual key and store it (raw key stays in the proxy).

    Requires the provider API key already configured plus
    LITELLM_MASTER_KEY. The virtual key itself is encrypted at rest and
    never printed: only its prefix is shown for identification.
    """
    from app.models import InstanceAIConfig
    from app.services.llm_backends import provision_virtual_key

    try:
        iid = _resolve_instance_id(instance_ref)
    except ValueError as exc:
        click.echo(f"Error: {exc}", err=True)
        return
    config = InstanceAIConfig.query.filter_by(
        instance_id=iid, provider=provider.strip().lower()
    ).first()
    if config is None or not config.api_key:
        click.echo(
            f"Error: no API key configured for provider '{provider}' on this instance.",
            err=True,
        )
        return
    model_list = [m.strip() for m in models.split(",") if m.strip()]
    if not model_list:
        click.echo("Error: --models must list at least one model id.", err=True)
        return
    try:
        key = provision_virtual_key(model_list, alias=f"{iid}:{provider}")
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        return
    config.virtual_key = key
    config.use_proxy = True
    from app.extensions import db

    db.session.commit()
    click.echo(
        f"Proxy key provisioned for instance {iid} provider {provider} "
        f"(prefix {key[:7]}…, stored encrypted, proxy mode on)."
    )
