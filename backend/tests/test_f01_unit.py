"""Expansion Feature 1 unit tests: the pure vocabulary of the
device/recovery layer — code shape and normalisation, the
shown-once output contract, and the schema guards (no money
columns, additive-only session binding). Service behaviour lives
in the integration suite; refusal paths in the security suite.
"""
from __future__ import annotations

import re

from app.security.devices import (
    CODE_ALPHABET, CODE_COUNT_MAX, CODE_COUNT_MIN, _new_code,
    _normalize_code, device_to_dict,
)


def test_recovery_code_shape_and_alphabet():
    for _ in range(50):
        code = _new_code()
        assert re.fullmatch(r"[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}", code), code
        raw = code.replace("-", "")
        assert all(ch in CODE_ALPHABET for ch in raw)


def test_code_alphabet_has_no_confusables():
    for ch in "01OIL":
        assert ch not in CODE_ALPHABET
    # 23 unambiguous letters + digits 2-9: 31 symbols, no duplicates.
    assert len(set(CODE_ALPHABET)) == len(CODE_ALPHABET) == 31


def test_code_normalisation_accepts_owner_transcription():
    assert _normalize_code("ab3d-ef5g-hj7k") == "AB3DEF5GHJ7K"
    assert _normalize_code(" AB3D EF5G HJ7K ") == "AB3DEF5GHJ7K"
    assert _normalize_code("AB3DEF5GHJ7K") == "AB3DEF5GHJ7K"
    assert _normalize_code("") == ""
    assert _normalize_code(None) == ""  # type: ignore[arg-type]


def test_code_count_bounds_are_sane():
    assert CODE_COUNT_MIN >= 1
    assert CODE_COUNT_MAX <= 50  # a batch stays human-manageable


def test_device_dict_never_carries_credential_material():
    from app.database.models.security import SecurityDevice
    row = SecurityDevice(
        id="d1", principal_type="owner", principal_id="owner",
        label="Laptop", secret_hash="f" * 64, trust_status="trusted")
    out = device_to_dict(row)
    assert "secret_hash" not in out
    assert "device_secret" not in out
    assert out["trust_status"] == "trusted"
    assert out["principal"] == "owner:owner"


def test_metadata_registers_exactly_two_new_tables():
    from app.database.models.base import Base
    import app.database.models  # noqa: F401

    # Expansion F03 disclosure: +4 voice tables (231 total).
    # Expansion F06 disclosure: +3 knowledge tables (234 total).
    assert len(Base.metadata.tables) == 234  # 223 pre-F01 + 2 F01 + 2 F02 + 4 F03 + 3 F06
    assert {"security_devices", "security_recovery_codes"} <= set(
        Base.metadata.tables)


def test_schema_guard_no_money_columns_and_nullable_binding():
    from app.database.models.base import Base
    import app.database.models  # noqa: F401

    money_fragments = ("amount", "price", "balance", "minor", "currency",
                       "revenue", "cost", "fee", "payment")
    for table_name in ("security_devices", "security_recovery_codes"):
        for column in Base.metadata.tables[table_name].columns:
            for fragment in money_fragments:
                assert fragment not in column.name, \
                    f"{table_name}.{column.name} looks like a money column"
    device_id = Base.metadata.tables["app_sessions"].columns["device_id"]
    assert device_id.nullable is True  # additive: legacy rows stay valid
