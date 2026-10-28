"""Generate new development-only Compose secrets without printing their values."""

import argparse
import json
import os
import secrets
from pathlib import Path

from cryptography.fernet import Fernet


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--container-readable",
        action="store_true",
        help="Local Compose/Linux bind mounts: read-only 0444 files inside the private 0700 directory; external secret managers should set service UID permissions instead.",
    )
    args = parser.parse_args()
    root = args.output_dir.expanduser().resolve()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise SystemExit(
            "Refusing to overwrite an existing secret directory. Use a new private directory."
        )
    root.chmod(0o700)
    admin = secrets.token_urlsafe(36)
    app = secrets.token_urlsafe(36)
    broker = secrets.token_urlsafe(36)
    values = {
        "db_admin_password": admin,
        "db_app_password": app,
        "database_migration_url": f"postgresql+psycopg://vantage_migration:{admin}@db:5432/vantage",
        "database_app_url": f"postgresql+psycopg://vantage_app:{app}@db:5432/vantage",
        "redis_password": broker,
        "redis_url": f"redis://:{broker}@redis:6379/0",
        "redis_acl": f"user default on >{broker} ~* &* +@all -CONFIG -FLUSHALL -FLUSHDB -MODULE -DEBUG -SHUTDOWN -ACL -SAVE -BGSAVE -BGREWRITEAOF -REPLICAOF -SLAVEOF",
        "master_keys": json.dumps({"v1": Fernet.generate_key().decode()}),
    }
    for name, value in values.items():
        descriptor = os.open(
            root / name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o444 if args.container_readable else 0o600,
        )
        with os.fdopen(descriptor, "w") as output:
            output.write(value + "\n")
    print(
        f"Created new private local-only secrets in {root}; no values printed. Keep this directory outside source control and separately secure key recovery."
    )


if __name__ == "__main__":
    main()
