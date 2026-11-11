"""Xodim yaratish yoki parolini yangilash: python -m app.manage create-staff <login> <rol>"""

import argparse
from getpass import getpass

from app.auth import ROLES, create_or_update_staff
from app.db.session import SessionLocal

MIN_PASSWORD_LENGTH = 8


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.manage")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create-staff")
    create.add_argument("login")
    create.add_argument("role", choices=ROLES)
    args = parser.parse_args()

    password = getpass("Parol: ")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise SystemExit(f"Parol kamida {MIN_PASSWORD_LENGTH} belgi boʻlishi kerak.")
    if password != getpass("Parolni takrorlang: "):
        raise SystemExit("Parollar mos kelmadi.")

    with SessionLocal() as db:
        created = create_or_update_staff(db, args.login, password, args.role)
    print(("Yaratildi: " if created else "Yangilandi: ") + args.login)


if __name__ == "__main__":
    main()
