\
from __future__ import annotations

import re

_SAFE_REF_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_-]{20,125}$")
_OPERATION_RE = re.compile(r"^op_[A-Za-z0-9_-]{20,125}$")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def normalize_query(query: str) -> str:
    value = query.strip()
    if not value:
        raise ValueError("query não pode ser vazia")
    if len(value) > 256:
        raise ValueError("query excede 256 caracteres")
    if _CONTROL_RE.search(value):
        raise ValueError("query contém caracteres de controle não permitidos")
    return value


def normalize_safe_ref(value: str, *, expected_prefix: str) -> str:
    ref = value.strip()
    if not _SAFE_REF_RE.fullmatch(ref) or not ref.startswith(expected_prefix + "_"):
        raise ValueError(f"{expected_prefix}_ref inválida")
    return ref


def normalize_user_ref(user_ref: str) -> str:
    return normalize_safe_ref(user_ref, expected_prefix="usr")


def normalize_device_ref(device_ref: str) -> str:
    return normalize_safe_ref(device_ref, expected_prefix="dev")


def normalize_operation_id(operation_id: str) -> str:
    value = operation_id.strip()
    if not _OPERATION_RE.fullmatch(value):
        raise ValueError("operation_id inválido")
    return value
