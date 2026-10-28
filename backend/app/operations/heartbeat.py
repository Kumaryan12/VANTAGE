"""Container-local readiness heartbeat: SQL and broker checked, no sensitive values written."""

import json
import os
import sys
import time
from pathlib import Path
from threading import Thread

PATH = Path("/tmp/vantage-service-ready.json")


def start(kind):
    from app.core.config import settings

    if settings().environment != "production":
        return

    def pulse():
        from redis import Redis
        from sqlalchemy import text
        from sqlalchemy.orm import Session

        from app.database.session import engine

        broker = Redis.from_url(settings().redis_url, socket_timeout=1, socket_connect_timeout=1)
        while True:
            try:
                with Session(engine) as db:
                    db.execute(text("SELECT 1"))
                if not broker.ping():
                    raise RuntimeError()
                temporary = PATH.with_suffix(".tmp")
                temporary.write_text(json.dumps({"kind": kind, "at": time.time()}))
                temporary.chmod(0o600)
                os.replace(temporary, PATH)
            except Exception:
                PATH.unlink(missing_ok=True)
            time.sleep(5)

    Thread(target=pulse, name="service-readiness", daemon=True).start()


def check():
    try:
        value = json.loads(PATH.read_text())
        assert 0 <= time.time() - value["at"] <= 15
    except Exception:
        raise SystemExit(1) from None


if __name__ == "__main__":
    if sys.argv[1:] == ["check"]:
        check()
    else:
        raise SystemExit("Use check; heartbeat startup is internal to the service lifecycle.")
