"""Write-permit artifacts for guarded wiki and root-vault mutations."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from kb_creator.contracts import Result


PERMIT_ENV_KEY = "KB_WRITE_PERMIT_KEY"
PERMIT_VERSION = 1


@dataclass(frozen=True)
class PermitScope:
    """Supported write-permit scopes."""

    name: str


BUILD_BOOK_SCOPE = PermitScope("build-book")
APPLY_ROOT_PROMOTION_SCOPE = PermitScope("apply-root-promotion")


def _canonical_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _permit_secret() -> str | None:
    value = os.environ.get(PERMIT_ENV_KEY, "").strip()
    return value or None


def _permit_signature(payload: dict[str, Any], secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), _canonical_payload(payload).encode("utf-8"), hashlib.sha256)
    return digest.hexdigest()


def _permit_slug(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in value.strip().lower())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or "permit"


def issue_write_permit(
    vault_root: Path,
    *,
    scope: PermitScope,
    target: str,
    issuer: str = "debug-cli",
    expires_in_seconds: int = 3600,
    artifacts_dir: Path | None = None,
) -> Result:
    """Issue one signed write-permit artifact for a specific scope/target."""
    result = Result(
        ok=True,
        action="issue_write_permit",
        inputs={
            "vault_root": str(vault_root.resolve()),
            "scope": scope.name,
            "target": target,
            "issuer": issuer,
            "expires_in_seconds": expires_in_seconds,
        },
    )
    secret = _permit_secret()
    if secret is None:
        return Result(
            ok=False,
            action="issue_write_permit",
            inputs=result.inputs,
            errors=[f"{PERMIT_ENV_KEY} must be set to issue signed write permits"],
        )

    now = datetime.now(timezone.utc)
    payload = {
        "version": PERMIT_VERSION,
        "scope": scope.name,
        "target": target,
        "issuer": issuer,
        "issued_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=max(1, expires_in_seconds))).isoformat(),
        "nonce": secrets.token_hex(8),
        "vault_root": str(vault_root.resolve()),
    }
    signature = _permit_signature(payload, secret)
    permit = dict(payload)
    permit["signature"] = signature

    root = vault_root.resolve()
    artifact_root = artifacts_dir.resolve() if artifacts_dir else root / ".kb-artifacts"
    permit_dir = artifact_root / "permits"
    permit_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{scope.name}-{_permit_slug(target)}.json"
    permit_path = permit_dir / filename
    permit_path.write_text(json.dumps(permit, ensure_ascii=False, indent=2), encoding="utf-8")

    result.outputs = {
        "permit_path": str(permit_path),
        "scope": scope.name,
        "target": target,
        "expires_at": permit["expires_at"],
    }
    return result


def validate_write_permit(
    permit_path: Path,
    *,
    expected_scope: PermitScope,
    expected_target: str,
    vault_root: Path,
) -> tuple[bool, str]:
    """Validate one permit against scope, target, signature, and expiry."""
    if not permit_path.exists():
        return False, f"write permit not found: {permit_path}"
    secret = _permit_secret()
    if secret is None:
        return False, f"{PERMIT_ENV_KEY} must be set to validate signed write permits"

    try:
        permit = json.loads(permit_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return False, f"invalid write permit JSON: {exc}"

    signature = permit.pop("signature", "")
    if not isinstance(signature, str) or not signature:
        return False, "write permit missing signature"

    required = ("version", "scope", "target", "issuer", "issued_at", "expires_at", "nonce", "vault_root")
    missing = [field for field in required if field not in permit]
    if missing:
        return False, f"write permit missing fields: {', '.join(missing)}"
    if permit["version"] != PERMIT_VERSION:
        return False, f"unsupported write permit version: {permit['version']}"
    if permit["scope"] != expected_scope.name:
        return False, f"write permit scope mismatch: expected {expected_scope.name}, got {permit['scope']}"
    if permit["target"] != expected_target:
        return False, f"write permit target mismatch: expected {expected_target}, got {permit['target']}"
    if permit["vault_root"] != str(vault_root.resolve()):
        return False, "write permit vault root mismatch"
    expected_signature = _permit_signature(permit, secret)
    if not hmac.compare_digest(signature, expected_signature):
        return False, "write permit signature mismatch"
    try:
        expires_at = datetime.fromisoformat(permit["expires_at"])
    except ValueError:
        return False, "write permit has invalid expires_at timestamp"
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        return False, "write permit expired"
    return True, ""
