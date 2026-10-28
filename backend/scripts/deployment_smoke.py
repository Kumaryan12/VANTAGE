"""Actual HTTPS/non-root/role-isolated Compose journey, restart and saved evidence verification."""

import argparse
import hashlib
import json
import os
import secrets
import ssl
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[2]


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default="vantage-phase6")
    parser.add_argument("--url", default="https://localhost:8443")
    parser.add_argument("--ca-file", type=Path, required=True)
    parser.add_argument(
        "--identity-file", type=Path, default=ROOT / "artifacts/phase6/deployment-identity.json"
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Verify restored/restarted records from a private previous identity file",
    )
    args = parser.parse_args()
    if not args.verify_only and args.identity_file.exists():
        raise SystemExit(
            "Use a new private identity file or --verify-only; existing recovery evidence is never overwritten."
        )
    compose = [
        "docker",
        "compose",
        "-p",
        args.project,
        "-f",
        str(ROOT / "infra/compose.production.yml"),
    ]

    def command(values, data=None):
        result = subprocess.run(
            [*compose, *values], input=data, text=True, capture_output=True, cwd=ROOT
        )
        if result.returncode:
            raise AssertionError(
                "Authorized Compose operation failed; inspect private container health/logs. No raw secret-bearing exception is emitted."
            )
        return result.stdout

    def provision(email, password, role="USER"):
        code = "import json,sys; from sqlalchemy.orm import Session; from app.database.session import engine; from app.auth.identity import create_user,insert_ignore; from app.database.models import UserRoleAssignment; v=json.load(sys.stdin); db=Session(engine); u=create_user(db,v['email'],v['password']); insert_ignore(db,UserRoleAssignment,{'user_id':u.id,'role':v['role']},['user_id','role']); db.commit(); print('Account provisioned')"
        command(
            ["exec", "-T", "backend", "python", "-c", code],
            json.dumps({"email": email, "password": password, "role": role}),
        )

    context = ssl.create_default_context(cafile=str(args.ca_file))
    with httpx.Client(
        base_url=args.url, verify=context, headers={"Origin": args.url}, timeout=30, trust_env=False
    ) as client:

        def request(method, path, body=None, expected=200):
            response = client.request(method, path, **({"json": body} if body is not None else {}))
            assert response.status_code == expected, (
                f"HTTP verification failed for {path}: status {response.status_code}; response contents omitted."
            )
            return response.json()

        def wait(path, ready, timeout=90):
            deadline = time.monotonic() + timeout
            last = None
            while time.monotonic() < deadline:
                try:
                    last = request("GET", path)
                    if ready(last):
                        return last
                except (httpx.HTTPError, AssertionError):
                    pass
                time.sleep(0.2)
            raise AssertionError(
                f"Bounded deployment readiness/completion failed: {path}; last status {last and last.get('status')}"
            )

        def login(identity):
            response = client.post(
                "/api/auth/login",
                json={"email": identity["email"], "password": identity["password"]},
            )
            assert response.status_code == 200
            cookie = response.headers["set-cookie"].lower()
            assert "httponly" in cookie and "secure" in cookie and "samesite=lax" in cookie
            return response.json()

        def check_saved(identity):
            for path, expected_hash in identity["saved_hashes"].items():
                assert digest(request("GET", path)) == expected_hash, (
                    f"Restored/restarted evidence differs: {path}"
                )
            replay = request("POST", f"/api/v1/risk/runs/{identity['risk_id']}/replay")
            assert replay["input_hash_matches"] and replay["numerical_results_match"]
            repro = request(
                "POST",
                f"/api/v1/optimization/runs/{identity['optimization_id']}/reproduce",
                expected=202,
            )
            reproduced = wait(
                f"/api/v1/optimization/runs/{repro['id']}",
                lambda r: r["status"] not in {"queued", "running"},
            )
            assert reproduced["result"]["reproduction_match"] is True
            ml = request(
                "POST",
                f"/api/v1/ml/experiments/{identity['experiment_id']}/reproduce",
                expected=202,
            )
            repeated = wait(
                f"/api/v1/ml/experiments/{ml['id']}",
                lambda r: r["status"] not in {"queued", "running"},
            )
            assert repeated["reproduction_match"] is True
            assert (
                client.get(f"/api/v1/storage/artifacts/{identity['export_id']}").status_code == 200
            )
            assert (
                client.get(f"/api/v1/ml/models/{identity['model_id']}/artifact").status_code == 200
            )
            assert (
                client.get(f"/api/v1/research/documents/{identity['document_id']}/file").status_code
                == 200
            )

        wait("/api/health", lambda r: r["status"] == "ok")
        if args.verify_only:
            identity = json.loads(args.identity_file.read_text())
            login(identity)
            check_saved(identity)
            print(
                json.dumps(
                    {
                        "passed": True,
                        "synthetic": True,
                        "mode": "restored_or_restarted_verification",
                        "https_certificate_verified": True,
                        "saved_hashes_verified": len(identity["saved_hashes"]),
                        "risk_reproduced": True,
                        "optimization_reproduced": True,
                        "ml_reproduced": True,
                    }
                )
            )
            return
        assert client.get("/").status_code == 200
        assert client.get("/api/docs").status_code == 404
        assert (
            client.post(
                "/api/auth/register",
                json={
                    "email": "closed@example.com",
                    "password": "Synthetic closed-registration fixture 53!",
                },
            ).status_code
            == 403
        )
        assert client.get("/api/portfolio").status_code == 401
        identity = {
            "email": f"deployment-{uuid4().hex}@example.com",
            "password": "Synthetic deployed research " + secrets.token_urlsafe(24),
        }
        provision(identity["email"], identity["password"])
        me = login(identity)
        identity["user_id"] = me["user"]["id"]
        identity["scope_id"] = me["workspace_id"]
        portfolio = request("GET", "/api/portfolio")
        assert portfolio["synthetic"] and portfolio["mode"] == "demo"
        risk = request("POST", "/api/v1/jobs/risk", {"parameters": {"simulations": 2000}}, 202)
        done = wait(f"/api/v1/jobs/{risk['id']}", lambda r: r["status"] == "completed")
        identity["risk_id"] = done["result_reference"]["target_id"]
        experiment = request(
            "POST", "/api/v1/ml/backtest", {"max_trees": 40, "search_candidates": 2}, 202
        )
        identity["experiment_id"] = experiment["id"]
        research = wait(
            f"/api/v1/ml/experiments/{experiment['id']}",
            lambda r: r["status"] not in {"queued", "running"},
        )
        assert (
            research["status"] == "completed"
            and research["comparison"]["matched_observations"] == 100
        )
        models = request("GET", f"/api/v1/ml/models?experiment_id={experiment['id']}")
        assert len(models) == 4
        identity["model_id"] = next(m["id"] for m in models if m["kind"] == "lightgbm")
        from app.agent.fixtures import DEBT, LIQUIDITY, pdf_bytes

        response = client.post(
            "/api/v1/research/documents",
            files={
                "file": (
                    "SYNTHETIC-deployment.pdf",
                    pdf_bytes([LIQUIDITY, DEBT]),
                    "application/pdf",
                )
            },
            data={"source": "Permitted synthetic deployed disclosure", "permitted": "true"},
        )
        assert response.status_code == 202
        identity["document_id"] = response.json()["id"]
        document = wait(
            f"/api/v1/research/documents/{identity['document_id']}",
            lambda r: r["status"] == "ready",
        )
        assert document["metadata"]["parser_isolation"]["network_filesystem_isolated"] is True
        investigation = request(
            "POST",
            "/api/v1/agent/investigate",
            {
                "question": "Summarize liquidity and refinancing risk in this uploaded disclosure",
                "document_ids": [identity["document_id"]],
            },
            202,
        )
        identity["investigation_id"] = investigation["id"]
        answer = wait(
            f"/api/v1/agent/investigations/{investigation['id']}",
            lambda r: r["status"] not in {"queued", "running"},
        )
        assert answer["answer"]["citations"] and answer["engine"] == "demo"
        optimization = request("POST", "/api/v1/optimization/run", {}, 202)
        identity["optimization_id"] = optimization["id"]
        allocation = wait(
            f"/api/v1/optimization/runs/{optimization['id']}",
            lambda r: r["status"] not in {"queued", "running"},
        )
        assert allocation["result"]["points"][0]["solution"]["feasible"]
        exported = request(
            "POST",
            "/api/v1/jobs/report",
            {"source_type": "investigation", "source_id": investigation["id"]},
            202,
        )
        export = wait(f"/api/v1/jobs/{exported['id']}", lambda r: r["status"] == "completed")
        identity["export_id"] = export["result_reference"]["artifact_id"]
        paths = [
            f"/api/v1/risk/runs/{identity['risk_id']}",
            f"/api/v1/ml/experiments/{experiment['id']}",
            f"/api/v1/research/documents/{identity['document_id']}",
            f"/api/v1/agent/investigations/{investigation['id']}",
            f"/api/v1/optimization/runs/{optimization['id']}",
        ]
        identity["saved_hashes"] = {path: digest(request("GET", path)) for path in paths}
        descriptor = os.open(args.identity_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as output:
            json.dump(identity, output, indent=2)
        assert client.post("/api/auth/logout").status_code == 200
        command(
            [
                "restart",
                "db",
                "redis",
                "backend",
                "dispatcher",
                "worker-quant",
                "worker-agent",
                "worker-evaluation",
                "frontend",
                "proxy",
            ]
        )
        wait("/api/health", lambda r: r["status"] == "ok", 120)
        login(identity)
        check_saved(identity)
        # Even platform administration must not grant confidential financial access.
        other = {
            "email": f"admin-isolation-{uuid4().hex}@example.com",
            "password": "Synthetic separate administrator " + secrets.token_urlsafe(24),
        }
        provision(other["email"], other["password"], "PLATFORM_ADMIN")
        request("POST", "/api/auth/logout")
        login(other)
        for path in paths + [
            f"/api/v1/storage/artifacts/{identity['export_id']}",
            f"/api/v1/ml/models/{identity['model_id']}/artifact",
            f"/api/v1/research/documents/{identity['document_id']}/file",
            f"/api/v1/jobs/{risk['id']}",
        ]:
            assert client.get(path).status_code == 404, path
        print(
            json.dumps(
                {
                    "passed": True,
                    "synthetic": True,
                    "https_certificate_verified": True,
                    "required_kernel_document_isolation": True,
                    "all_six_research_workflows": True,
                    "saved_hashes_after_service_restart": len(paths),
                    "risk_reproduced": True,
                    "ml_reproduced": True,
                    "optimization_reproduced": True,
                    "private_exports_accessible": True,
                    "platform_admin_financial_access_denied": True,
                    "identity_file": str(args.identity_file),
                    "live_paid_calls": False,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
