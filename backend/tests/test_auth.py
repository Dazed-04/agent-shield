import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient

from app.auth import Principal, authenticate, require_admin, require_user
from tests.conftest import ADMIN_KEY, DS_KEY, STD_KEY

app = FastAPI()


@app.get("/me")
def me(p: Principal = Depends(require_user)):
    return {"user": p.user, "role": p.role, "admin": p.is_admin}


@app.get("/admin")
def admin(p: Principal = Depends(require_admin)):
    return {"user": p.user}


@app.get("/stream")
def stream(request: Request):
    return {"user": authenticate(request, allow_query_key=True).user}


c = TestClient(app)


def H(key, iface="web"):
    return {"X-API-Key": key, "X-Client-Interface": iface}


def test_production_is_the_default():
    assert c.get("/me").status_code == 401


def test_plaintext_and_hashed_keys_both_work():
    assert c.get("/me", headers=H(ADMIN_KEY)).json() == {"user": "alice", "role": "Domain Admins", "admin": True}
    assert c.get("/me", headers=H(STD_KEY)).json()["user"] == "sam"  # stored only as a sha256 hash


def test_bad_and_placeholder_keys_rejected():
    assert c.get("/me", headers=H("nope")).status_code == 401
    assert c.get("/me", headers=H("REPLACE_ME_ADMIN_KEY")).status_code == 401


def test_admin_requires_admin_role():
    assert c.get("/admin", headers=H(STD_KEY)).status_code == 403
    assert c.get("/admin", headers=H(DS_KEY)).status_code == 403
    assert c.get("/admin", headers=H(ADMIN_KEY)).status_code == 200


def test_interface_entitlements():
    assert c.get("/me", headers=H(STD_KEY, "cli")).status_code == 403
    assert c.get("/me", headers=H(ADMIN_KEY, "cli")).status_code == 200


def test_query_key_only_where_explicitly_allowed():
    assert c.get(f"/stream?api_key={ADMIN_KEY}").json() == {"user": "alice"}
    assert c.get(f"/me?api_key={ADMIN_KEY}").status_code == 401


def test_development_mode_is_open(dev_mode):
    assert c.get("/admin").status_code == 200


@pytest.mark.parametrize("mode", ["production", "PRODUCTION"])
def test_mode_is_case_insensitive(monkeypatch, mode):
    monkeypatch.setenv("SECURITY_ENV", mode)
    assert c.get("/me").status_code == 401
