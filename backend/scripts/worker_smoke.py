"""Actual PostgreSQL/Redis, separate API/dispatcher/prefork worker crash and recovery evidence."""

import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[2]
LOGS = ROOT / "artifacts/phase6"


def main():
    if not os.environ.get("DATABASE_URL", "").startswith("postgresql"):
        raise SystemExit("A migrated disposable PostgreSQL DATABASE_URL is required.")
    LOGS.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "JOB_BACKEND": "celery",
        "JOB_LEASE_SECONDS": "10",
        "AUTH_REQUIRED": "true",
        "REGISTRATION_ENABLED": "true",
        "COOKIE_SECURE": "false",
        "OPENAI_API_KEY": "",
        "PYTHONPATH": str(ROOT / "backend"),
        "OBJC_DISABLE_INITIALIZE_FORK_SAFETY": "YES",
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
    }
    children = []

    def start(name, command):
        with (LOGS / f"worker-{name}.log").open("ab") as output:
            child = subprocess.Popen(
                [sys.executable, *command],
                env=env,
                cwd=ROOT,
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        children.append(child)
        return child

    def stop(child, hard=False):
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGKILL if hard else signal.SIGTERM)
            try:
                child.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait(timeout=3)

    def port():
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            return sock.getsockname()[1]

    base = f"http://127.0.0.1:{port()}"
    base2 = f"http://127.0.0.1:{port()}"
    env["FRONTEND_URL"] = base

    def wait(operation, predicate, seconds=60):
        deadline = time.monotonic() + seconds
        last = None
        while time.monotonic() < deadline:
            try:
                last = operation()
                if predicate(last):
                    return last
            except httpx.HTTPError:
                pass
            time.sleep(0.02)
        raise AssertionError(f"Bounded worker smoke timed out; last status: {last}")

    def request(client, method, path, body=None, expected=200):
        response = client.request(method, path, **({"json": body} if body is not None else {}))
        assert response.status_code == expected, f"{path}: {response.status_code} {response.text}"
        return response.json()

    def worker(name="quant", queues="research,optimization,risk,report,document"):
        return start(
            name,
            [
                "-m",
                "celery",
                "-A",
                "app.jobs.celery_app:app",
                "worker",
                "--loglevel=WARNING",
                "--concurrency=1",
                "--pool=" + ("solo" if sys.platform == "darwin" else "prefork"),
                "-Q",
                queues,
                "--hostname",
                name + "@%h",
                "--without-gossip",
                "--without-mingle",
            ],
        )

    try:
        api = start(
            "api",
            [
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                base.rsplit(":", 1)[1],
                "--no-access-log",
            ],
        )
        start(
            "api2",
            [
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                base2.rsplit(":", 1)[1],
                "--no-access-log",
            ],
        )
        for url in (base, base2):
            wait(
                lambda url=url: httpx.get(url + "/api/health", timeout=1),
                lambda r: r.status_code == 200,
            )
        start("dispatcher", ["-m", "app.jobs.dispatcher"])
        with httpx.Client(base_url=base, headers={"Origin": base}, timeout=30) as client:
            email = f"durable-worker-{uuid4().hex}@example.com"
            password = "Synthetic separate worker recovery phrase 82!"
            request(
                client, "POST", "/api/auth/register", {"email": email, "password": password}, 202
            )
            request(client, "POST", "/api/auth/login", {"email": email, "password": password})
            # Queue before workers exist: another API process sees SQL state without interruption.
            queued = request(
                client,
                "POST",
                "/api/v1/ml/backtest",
                {"max_trees": 300, "search_candidates": 3, "test_size": 125, "refit_every": 5},
                202,
            )

            def jobs():
                return request(client, "GET", "/api/v1/jobs")["jobs"]

            job = next(j for j in jobs() if j["target_id"] == queued["id"])
            with httpx.Client(
                base_url=base2, headers={"Origin": base}, cookies=client.cookies, timeout=30
            ) as peer:
                assert (
                    request(peer, "GET", f"/api/v1/ml/experiments/{queued['id']}")["status"]
                    == "queued"
                )
                response = peer.post(
                    "/api/v1/ml/backtest", json={"max_trees": 40, "search_candidates": 2}
                )
                assert response.status_code == 429, response.text
            process = worker("crash-target")
            wait(
                lambda: request(client, "GET", f"/api/v1/jobs/{job['id']}"),
                lambda j: j["status"] == "running",
                45,
            )
            crashed_pid = process.pid
            stop(process, hard=True)
            process = worker("replacement")
            recovered = wait(
                lambda: request(client, "GET", f"/api/v1/jobs/{job['id']}"),
                lambda j: j["status"] in {"completed", "failed", "interrupted"},
                90,
            )
            assert recovered["status"] == "completed" and recovered["attempts"] == 2, recovered
            models = request(client, "GET", f"/api/v1/ml/models?experiment_id={queued['id']}")
            assert len(models) == 4
            # A second live attempt is cancelled and must not publish its models.
            cancelled = request(
                client,
                "POST",
                "/api/v1/ml/backtest",
                {"max_trees": 300, "search_candidates": 3, "test_size": 125, "refit_every": 5},
                202,
            )
            canceljob = next(j for j in jobs() if j["target_id"] == cancelled["id"])
            wait(
                lambda: request(client, "GET", f"/api/v1/jobs/{canceljob['id']}"),
                lambda j: j["status"] == "running",
            )
            assert (
                request(client, "POST", f"/api/v1/jobs/{canceljob['id']}/cancel")["status"]
                == "cancel_requested"
            )
            stopped = wait(
                lambda: request(client, "GET", f"/api/v1/jobs/{canceljob['id']}"),
                lambda j: j["status"] == "cancelled",
            )
            assert (
                request(client, "GET", f"/api/v1/ml/models?experiment_id={cancelled['id']}") == []
            )
            optimization = request(client, "POST", "/api/v1/optimization/run", {}, 202)
            optjob = next(j for j in jobs() if j["target_id"] == optimization["id"])
            wait(
                lambda: request(client, "GET", f"/api/v1/jobs/{optjob['id']}"),
                lambda j: j["status"] == "completed",
            )
            saved = request(client, "GET", f"/api/v1/optimization/runs/{optimization['id']}")
            with httpx.Client(base_url=base, headers={"Origin": base}, timeout=30) as other:
                second = f"worker-isolation-{uuid4().hex}@example.com"
                request(
                    other,
                    "POST",
                    "/api/auth/register",
                    {"email": second, "password": password},
                    202,
                )
                request(other, "POST", "/api/auth/login", {"email": second, "password": password})
                request(other, "GET", f"/api/v1/jobs/{optjob['id']}", expected=404)
                request(other, "POST", f"/api/v1/jobs/{optjob['id']}/cancel", expected=404)
            # All provider-free task adapters also execute through the real broker/workers.
            worker("agent", "agent")
            from app.agent.fixtures import LIQUIDITY, pdf_bytes

            upload = client.post(
                "/api/v1/research/documents",
                files={"file": ("SYNTHETIC-worker.pdf", pdf_bytes([LIQUIDITY]), "application/pdf")},
                data={"source": "Permitted synthetic worker fixture", "permitted": "true"},
            )
            assert upload.status_code == 202, upload.text
            document_id = upload.json()["id"]
            wait(
                lambda: request(client, "GET", f"/api/v1/research/documents/{document_id}"),
                lambda d: d["status"] == "ready",
            )
            investigation = request(
                client,
                "POST",
                "/api/v1/agent/investigate",
                {
                    "question": "Summarize liquidity and refinancing risk in this uploaded disclosure",
                    "document_ids": [document_id],
                },
                202,
            )
            answer = wait(
                lambda: request(
                    client, "GET", f"/api/v1/agent/investigations/{investigation['id']}"
                ),
                lambda a: a["status"] not in {"queued", "running"},
            )
            assert answer["status"] == "completed" and answer["answer"]["citations"], answer
            riskjob = request(
                client, "POST", "/api/v1/jobs/risk", {"parameters": {"simulations": 2000}}, 202
            )
            riskdone = wait(
                lambda: request(client, "GET", f"/api/v1/jobs/{riskjob['id']}"),
                lambda j: j["status"] == "completed",
            )
            risk_id = riskdone["result_reference"]["target_id"]
            exported = request(
                client,
                "POST",
                "/api/v1/jobs/report",
                {"source_type": "optimization", "source_id": optimization["id"]},
                202,
            )
            exportdone = wait(
                lambda: request(client, "GET", f"/api/v1/jobs/{exported['id']}"),
                lambda j: j["status"] == "completed",
            )
            export_id = exportdone["result_reference"]["artifact_id"]
            assert client.get(f"/api/v1/storage/artifacts/{export_id}").status_code == 200
            worker("evaluation", "evaluation")
            evaluation = request(client, "POST", "/api/v1/agent/evaluation-runs", expected=202)
            evaluated = wait(
                lambda: request(client, "GET", f"/api/v1/agent/evaluation-runs/{evaluation['id']}"),
                lambda e: e["status"] not in {"queued", "running"},
                150,
            )
            assert (
                evaluated["status"] == "completed" and evaluated["payload"]["acceptance_passed"]
            ), evaluated
            # Separate API restart, same account and shared workers/results.
            request(client, "POST", "/api/auth/logout")
            stop(api)
            api = start(
                "api-restarted",
                [
                    "-m",
                    "uvicorn",
                    "app.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    base.rsplit(":", 1)[1],
                    "--no-access-log",
                ],
            )
            wait(lambda: httpx.get(base + "/api/health", timeout=1), lambda r: r.status_code == 200)
            request(client, "POST", "/api/auth/login", {"email": email, "password": password})
            assert (
                request(client, "GET", f"/api/v1/optimization/runs/{optimization['id']}") == saved
            )
            repro = request(
                client,
                "POST",
                f"/api/v1/optimization/runs/{optimization['id']}/reproduce",
                expected=202,
            )
            reproduced = wait(
                lambda: request(client, "GET", f"/api/v1/optimization/runs/{repro['id']}"),
                lambda j: j["status"] not in {"queued", "running"},
            )
            assert reproduced["result"]["reproduction_match"] is True
            assert (
                request(client, "GET", f"/api/v1/ml/experiments/{queued['id']}")["status"]
                == "completed"
            )
            assert (
                request(client, "GET", f"/api/v1/research/documents/{document_id}")["status"]
                == "ready"
            )
            assert (
                request(client, "GET", f"/api/v1/agent/investigations/{investigation['id']}")
                == answer
            )
            replay = request(client, "POST", f"/api/v1/risk/runs/{risk_id}/replay")
            assert replay["input_hash_matches"] and replay["numerical_results_match"]
            assert client.get(f"/api/v1/storage/artifacts/{export_id}").status_code == 200
            result = {
                "synthetic": True,
                "passed": True,
                "worker_pool": "solo" if sys.platform == "darwin" else "prefork",
                "crashed_worker_pid": crashed_pid,
                "replacement_worker_pid": process.pid,
                "recovered_job": job["id"],
                "recovery_attempts": recovered["attempts"],
                "cancelled_job": stopped["id"],
                "late_models_published": False,
                "all_seven_task_adapters": True,
                "durable_evaluation_cases_passed": sum(
                    c["passed"] for c in evaluated["payload"]["cases"]
                ),
                "document_id": document_id,
                "investigation_id": investigation["id"],
                "risk_run_id": risk_id,
                "optimization_run_id": optimization["id"],
                "experiment_id": queued["id"],
                "export_artifact_id": export_id,
                "cross_process_quota": True,
                "second_user_denied": True,
                "restart_retrieval": True,
                "optimization_reproduced": True,
            }
            (LOGS / "worker-smoke-evidence.json").write_text(json.dumps(result, indent=2) + "\n")
            print(json.dumps(result, indent=2))
    finally:
        for child in reversed(children):
            stop(child)


if __name__ == "__main__":
    main()
