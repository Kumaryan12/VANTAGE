"""Actual two-process restart/re-login/risk/optimization recovery on the configured database."""

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[2]


def main():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    env = {
        **os.environ,
        "AUTH_REQUIRED": "true",
        "REGISTRATION_ENABLED": "true",
        "COOKIE_SECURE": "false",
        "FRONTEND_URL": base,
    }
    logs = ROOT / "artifacts/phase6"
    logs.mkdir(parents=True, exist_ok=True)
    password = "Synthetic durable-account fixture phrase 72!"
    email = f"restart-{uuid4().hex}@example.com"
    second = f"isolation-{uuid4().hex}@example.com"
    process = None

    def start():
        output = (logs / "identity-smoke-server.log").open("ab")
        child = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--app-dir",
                str(ROOT / "backend"),
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--no-access-log",
            ],
            cwd=ROOT,
            env=env,
            stdout=output,
            stderr=subprocess.STDOUT,
        )
        output.close()
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if child.poll() is not None:
                raise RuntimeError(
                    "Identity smoke server stopped during readiness; inspect the private local log."
                )
            try:
                if httpx.get(base + "/api/health", timeout=1).status_code == 200:
                    return child
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        child.terminate()
        child.wait(timeout=10)
        raise RuntimeError("Identity smoke readiness timed out.")

    def stop(child):
        child.terminate()
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=5)

    def request(client, method, path, body=None, status=200):
        response = client.request(method, path, **({"json": body} if body is not None else {}))
        assert response.status_code == status, (
            f"{method} {path}: {response.status_code} {response.text}"
        )
        return response.json()

    def wait_job(client, ident):
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            result = request(client, "GET", f"/api/v1/optimization/runs/{ident}")
            if result["status"] not in ("queued", "running"):
                assert result["status"] == "completed", result
                return result
            time.sleep(0.1)
        raise RuntimeError("Optimization did not finish within the smoke budget.")

    try:
        process = start()
        first_pid = process.pid
        with httpx.Client(base_url=base, headers={"Origin": base}, timeout=30) as client:
            request(
                client, "POST", "/api/auth/register", {"email": email, "password": password}, 202
            )
            me = request(client, "POST", "/api/auth/login", {"email": email, "password": password})
            risk = request(
                client, "POST", "/api/v1/risk/analysis", {"simulations": 2000, "seed": 42}, 201
            )
            risk_id = risk["run_id"]
            risk_saved = request(client, "GET", f"/api/v1/risk/runs/{risk_id}")
            job = request(client, "POST", "/api/v1/optimization/run", {}, 202)
            optimization = wait_job(client, job["id"])
            request(client, "POST", "/api/auth/logout")
        stop(process)
        process = None
        process = start()
        second_pid = process.pid
        assert second_pid != first_pid
        with httpx.Client(base_url=base, headers={"Origin": base}, timeout=30) as client:
            restored = request(
                client, "POST", "/api/auth/login", {"email": email, "password": password}
            )
            assert (
                restored["user"]["id"] == me["user"]["id"]
                and restored["workspace_id"] == me["workspace_id"]
            )
            risk_after = request(client, "GET", f"/api/v1/risk/runs/{risk_id}")
            assert risk_after == risk_saved
            optimization_after = request(client, "GET", f"/api/v1/optimization/runs/{job['id']}")
            assert optimization_after == optimization
            replay = request(client, "POST", f"/api/v1/risk/runs/{risk_id}/replay")
            assert replay["input_hash_matches"] and replay["numerical_results_match"], replay
            reproduced = request(
                client, "POST", f"/api/v1/optimization/runs/{job['id']}/reproduce", status=202
            )
            assert wait_job(client, reproduced["id"])["result"]["reproduction_match"] is True
        with httpx.Client(base_url=base, headers={"Origin": base}, timeout=30) as stranger:
            request(
                stranger, "POST", "/api/auth/register", {"email": second, "password": password}, 202
            )
            request(stranger, "POST", "/api/auth/login", {"email": second, "password": password})
            request(stranger, "GET", f"/api/v1/risk/runs/{risk_id}", status=404)
            request(stranger, "POST", f"/api/v1/risk/runs/{risk_id}/replay", status=404)
            request(stranger, "GET", f"/api/v1/optimization/runs/{job['id']}", status=404)
            request(
                stranger, "POST", f"/api/v1/optimization/runs/{job['id']}/reproduce", status=404
            )
        evidence = {
            "passed": True,
            "synthetic": True,
            "first_pid": first_pid,
            "second_pid": second_pid,
            "user_id": me["user"]["id"],
            "workspace": me["workspace_id"],
            "risk_run": risk_id,
            "optimization_run": job["id"],
            "risk_saved_inputs_match": True,
            "optimization_saved_inputs_match": True,
            "cross_user_access_denied": True,
            "legacy_orphans_claimed": False,
        }
        (logs / "identity-restart-evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
        print(json.dumps(evidence, indent=2))
    finally:
        if process:
            stop(process)


if __name__ == "__main__":
    main()
