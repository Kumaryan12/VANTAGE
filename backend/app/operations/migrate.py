"""One-shot deployment migration. Never run this automatically inside API/worker startup."""

import json


def main():
    from alembic import command
    from alembic.config import Config

    from app.core.config import ROOT

    try:
        command.upgrade(Config(str(ROOT / "backend/alembic.ini")), "head")
    except Exception:
        print(
            json.dumps(
                {
                    "event": "migration_failed",
                    "message": "Migration did not finish. Preserve backups and use authorized forward recovery; no automatic downgrade.",
                }
            ),
            flush=True,
        )
        raise SystemExit(1) from None
    print(json.dumps({"event": "migration_completed", "target": "head"}), flush=True)


if __name__ == "__main__":
    main()
