"""Command-line helpers for administrative workflows."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
from typing import Any, Sequence

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from auth_microservice.services.bootstrap import PlatformBootstrapService
from auth_microservice.settings import settings


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="auth-microservice",
        description="Administrative commands for the auth microservice",
    )
    subparsers = parser.add_subparsers(dest="command")

    create_parser = subparsers.add_parser(
        "createsuperuser",
        help="Create the initial platform superuser",
    )
    create_parser.add_argument("--username", required=True, help="Username for the superuser")
    create_parser.add_argument("--email", required=True, help="Primary email for the superuser")
    create_parser.add_argument("--first-name", required=True, help="First name")
    create_parser.add_argument("--last-name", required=True, help="Last name")
    create_parser.add_argument(
        "--password",
        help="Password for the superuser. If omitted a prompt will be shown.",
    )
    create_parser.add_argument(
        "--middle-name",
        help="Optional middle name",
    )
    create_parser.add_argument(
        "--nationality",
        help="Optional nationality",
    )
    create_parser.add_argument(
        "--date-of-birth",
        help="Optional date of birth",
    )
    create_parser.add_argument(
        "--phone-number",
        help="Optional phone number",
    )
    create_parser.add_argument(
        "--no-input",
        action="store_true",
        help="Fail instead of prompting for missing values",
    )
    create_parser.set_defaults(handler=_handle_createsuperuser)

    return parser


def _prompt_for_password(no_input: bool) -> str:
    if no_input:
        raise SystemExit("--password is required when --no-input is supplied")

    while True:
        first = getpass.getpass("Password: ")
        if len(first) < 8:
            print("Password must be at least 8 characters long", file=sys.stderr)
            continue
        confirm = getpass.getpass("Confirm password: ")
        if first != confirm:
            print("Passwords do not match, try again", file=sys.stderr)
            continue
        return first


async def _create_superuser(payload: dict[str, Any]) -> tuple[bool, int, int, int]:
    engine = create_async_engine(str(settings.db_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with session_factory() as session:
            async with session.begin():
                bootstrapper = PlatformBootstrapService(session)
                result = await bootstrapper.bootstrap_superuser(payload)
        await engine.dispose()
    except Exception:
        await engine.dispose()
        raise

    return (
        result.created,
        result.user.user_id,
        result.role.role_id,
        result.organization.organization_id,
    )


async def _handle_createsuperuser(args: argparse.Namespace) -> int:
    password = args.password or _prompt_for_password(bool(args.no_input))
    if len(password) < 8:
        print("Password must be at least 8 characters long", file=sys.stderr)
        return 1

    contact_information = {"email": args.email}
    if args.phone_number:
        contact_information["phone_number"] = args.phone_number

    admin_payload: dict[str, Any] = {
        "username": args.username,
        "password": password,
        "first_name": args.first_name,
        "last_name": args.last_name,
        "contact_information": contact_information,
    }
    if args.middle_name:
        admin_payload["middle_name"] = args.middle_name
    if args.nationality:
        admin_payload["nationality"] = args.nationality
    if args.date_of_birth:
        admin_payload["date_of_birth"] = args.date_of_birth

    try:
        created, user_id, role_id, organization_id = await _create_superuser(admin_payload)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if created:
        print(
            "Created superuser",
            f"user_id={user_id}",
            f"role_id={role_id}",
            f"organization_id={organization_id}",
        )
    else:
        print(
            "Superuser already exists",
            f"user_id={user_id}",
            f"role_id={role_id}",
            f"organization_id={organization_id}",
        )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 1
    return asyncio.run(handler(args))


if __name__ == "__main__":  # pragma: no cover - manual execution guard
    raise SystemExit(main())
