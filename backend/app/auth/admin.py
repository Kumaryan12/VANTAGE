"""Trusted-host account provisioning/recovery. Never expose this as an agent tool or HTTP shell."""

import argparse
import getpass
import os
from pathlib import Path

from pydantic import EmailStr, TypeAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.identity import ROLES, create_user, insert_ignore, issue_recovery, security_event
from app.database.models import User, UserRoleAssignment
from app.database.session import engine


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["create-user", "grant-role", "issue-recovery"])
    parser.add_argument("email")
    parser.add_argument("--role", choices=ROLES)
    parser.add_argument(
        "--output-file",
        type=Path,
        help="Required for recovery; creates a new mode-0600 private token file, never stdout",
    )
    args = parser.parse_args()
    email = str(TypeAdapter(EmailStr).validate_python(args.email)).casefold()
    with Session(engine) as db:
        user = db.scalar(select(User).where(User.email == email))
        if args.operation == "create-user":
            if user:
                raise SystemExit("Account already exists.")
            password = getpass.getpass("New password (15–128 characters): ")
            if password != getpass.getpass("Confirm password: "):
                raise SystemExit("Passwords do not match.")
            user = create_user(db, email, password)
            print("Account provisioned.")
        elif not user:
            raise SystemExit("Account unavailable.")
        if args.operation == "grant-role" or (args.operation == "create-user" and args.role):
            if not args.role:
                raise SystemExit("--role is required.")
            insert_ignore(
                db, UserRoleAssignment, {"user_id": user.id, "role": args.role}, ["user_id", "role"]
            )
            security_event(db, "operator_role_granted", target=user.id, role=args.role)
            db.commit()
            print("Explicit role assignment recorded.")
        if args.operation == "issue-recovery":
            if args.output_file is None:
                raise SystemExit("--output-file is required; use a trusted private directory.")
            # Fail before issuing the token if the file exists or cannot be created safely.
            fd = os.open(args.output_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                token = issue_recovery(db, user.id)
                with os.fdopen(fd, "w") as output:
                    output.write(token + "\n")
            except BaseException:
                args.output_file.unlink(missing_ok=True)
                raise
            print(
                "Single-use recovery capability written to the private output file. Expires in 15 minutes; deliver out of band."
            )


if __name__ == "__main__":
    main()
