from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import re
import subprocess


_CVE_PATTERN = re.compile(r"\bCVE-\d{4}-\d{4,}\b")


def evaluate_report(report: str, allowlist_data: dict, *, today: date | None = None) -> dict:
    effective_date = today or date.today()
    findings = set(_CVE_PATTERN.findall(report))
    active: set[str] = set()
    expired: set[str] = set()
    for item in allowlist_data.get("exceptions", []):
        cve = str(item.get("id", "")).strip()
        expires = str(item.get("expires", "")).strip()
        rationale = str(item.get("rationale", "")).strip()
        if not _CVE_PATTERN.fullmatch(cve):
            raise ValueError(f"invalid CVE exception id: {cve or '<missing>'}")
        if not expires or not rationale:
            raise ValueError(f"CVE exception requires expires and rationale: {cve}")
        expiry = date.fromisoformat(expires)
        if expiry < effective_date:
            expired.add(cve)
        else:
            active.add(cve)
    return {
        "findings": sorted(findings),
        "allowed": sorted(findings & active),
        "unexpected": sorted(findings - active),
        "expired": sorted(findings & expired),
        "stale_exceptions": sorted(active - findings),
    }


def verify_image(image: str, allowlist_path: Path, *, today: date | None = None) -> dict:
    completed = subprocess.run(
        [
            "docker",
            "scout",
            "cves",
            image,
            "--only-severity",
            "critical,high",
            "--format",
            "packages",
        ],
        timeout=300,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"Docker Scout failed with exit code {completed.returncode}: {detail}")
    data = json.loads(allowlist_path.read_text(encoding="utf-8"))
    return evaluate_report(completed.stdout, data, today=today)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fail on unreviewed Critical/High CVEs in a local runner image."
    )
    parser.add_argument("--image", default="pyfixagent-runner:0.7.1")
    parser.add_argument(
        "--allowlist",
        type=Path,
        default=Path("containers/vulnerability-allowlist.json"),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = verify_image(args.image, args.allowlist)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"container security verification failed: {exc}")
        return 1
    print(
        "container security findings: "
        f"total={len(result['findings'])} allowed={len(result['allowed'])} "
        f"unexpected={len(result['unexpected'])} expired={len(result['expired'])}"
    )
    if result["stale_exceptions"]:
        print(f"stale exceptions: {', '.join(result['stale_exceptions'])}")
    if result["unexpected"]:
        print(f"unexpected CVEs: {', '.join(result['unexpected'])}")
    if result["expired"]:
        print(f"expired CVE exceptions: {', '.join(result['expired'])}")
    return 1 if result["unexpected"] or result["expired"] else 0


def cli() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    cli()
