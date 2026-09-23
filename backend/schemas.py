"""请求模型与输入校验。

任何非法输入都以 HTTP 422 返回, 每条错误带可定位到字段的 loc,
风格与 FastAPI/Pydantic 的校验错误一致, 例如:
    {"loc": ["body", "fragments", 3, "payload"], "msg": "...", "type": "value_error"}
"""

from __future__ import annotations

import re
from typing import Any

from .solver import Fragment

MIN_TARGET = 1
MAX_TARGET = 512
MIN_FRAGMENTS = 2
MAX_FRAGMENTS = 28
MIN_WEIGHT = 1
MAX_WEIGHT = 1_000_000

_HEX_RE = re.compile(r"^[0-9a-fA-F]+$")


class ValidationError(Exception):
    """收集式校验错误: 一次返回全部问题。"""

    def __init__(self, errors: list[dict[str, Any]]):
        self.errors = errors
        super().__init__(f"{len(errors)} 个校验错误")


def _is_int(value: Any) -> bool:
    # bool 是 int 的子类, 显式排除 true/false。
    return isinstance(value, int) and not isinstance(value, bool)


def _err(loc: list[Any], msg: str, err_type: str = "value_error") -> dict[str, Any]:
    return {"loc": ["body", *loc], "msg": msg, "type": err_type}


def parse_request(payload: Any) -> tuple[int, list[Fragment]]:
    """把原始 JSON 解析为 (目标长度, 片段列表), 非法即抛 ValidationError。"""

    errors: list[dict[str, Any]] = []

    if not isinstance(payload, dict):
        raise ValidationError(
            [_err([], "请求体必须是 JSON 对象", "type_error")]
        )

    if "target_length" not in payload:
        errors.append(_err(["target_length"], "字段必填", "missing"))
        target_length: int | None = None
    else:
        raw_length = payload["target_length"]
        if not _is_int(raw_length):
            errors.append(
                _err(["target_length"], "必须是整数", "type_error.integer")
            )
            target_length = None
        elif not (MIN_TARGET <= raw_length <= MAX_TARGET):
            errors.append(
                _err(
                    ["target_length"],
                    f"必须在 {MIN_TARGET} 至 {MAX_TARGET} 之间",
                    "value_error.range",
                )
            )
            target_length = None
        else:
            target_length = raw_length

    if "fragments" not in payload:
        errors.append(_err(["fragments"], "字段必填", "missing"))
        raise ValidationError(errors)

    raw_fragments = payload["fragments"]
    if not isinstance(raw_fragments, list):
        errors.append(
            _err(["fragments"], "必须是数组", "type_error.list")
        )
        raise ValidationError(errors)

    if not (MIN_FRAGMENTS <= len(raw_fragments) <= MAX_FRAGMENTS):
        errors.append(
            _err(
                ["fragments"],
                f"片段数量必须在 {MIN_FRAGMENTS} 至 {MAX_FRAGMENTS} 之间, "
                f"当前为 {len(raw_fragments)}",
                "value_error.count",
            )
        )
        # 数量非法时不再逐条检查, 避免噪声式错误。
        raise ValidationError(errors)

    parsed: list[tuple[int, str, int, bytes, int] | None] = []
    seen_ids: dict[str, int] = {}

    for index, item in enumerate(raw_fragments):
        base = ["fragments", index]
        if not isinstance(item, dict):
            errors.append(_err(base, "片段必须是对象", "type_error"))
            parsed.append(None)
            continue

        # ---- id ----
        frag_id: str | None = None
        if "id" not in item:
            errors.append(_err([*base, "id"], "字段必填", "missing"))
        else:
            raw_id = item["id"]
            if not isinstance(raw_id, str) or not raw_id.strip():
                errors.append(
                    _err([*base, "id"], "必须是非空字符串", "value_error")
                )
            else:
                frag_id = raw_id
                if raw_id in seen_ids:
                    errors.append(
                        _err(
                            [*base, "id"],
                            f"编号重复: {raw_id!r} 首次出现于 "
                            f"fragments[{seen_ids[raw_id]}]",
                            "value_error.duplicate",
                        )
                    )
                else:
                    seen_ids[raw_id] = index

        # ---- offset ----
        offset: int | None = None
        if "offset" not in item:
            errors.append(_err([*base, "offset"], "字段必填", "missing"))
        elif not _is_int(item["offset"]):
            errors.append(
                _err([*base, "offset"], "必须是从零起算的整数", "type_error.integer")
            )
        elif item["offset"] < 0:
            errors.append(
                _err([*base, "offset"], "不能为负数", "value_error.range")
            )
        else:
            offset = item["offset"]

        # ---- payload ----
        data: bytes | None = None
        if "payload" not in item:
            errors.append(_err([*base, "payload"], "字段必填", "missing"))
        else:
            raw_payload = item["payload"]
            if not isinstance(raw_payload, str):
                errors.append(
                    _err(
                        [*base, "payload"],
                        "必须是十六进制字符串",
                        "type_error.hex",
                    )
                )
            elif not raw_payload:
                errors.append(
                    _err([*base, "payload"], "载荷不能为空", "value_error.empty")
                )
            elif len(raw_payload) % 2 != 0:
                errors.append(
                    _err(
                        [*base, "payload"],
                        "十六进制长度必须为偶数(整数字节)",
                        "value_error.hex",
                    )
                )
            elif not _HEX_RE.match(raw_payload):
                errors.append(
                    _err(
                        [*base, "payload"],
                        "含有非十六进制字符(仅允许 0-9 a-f A-F)",
                        "value_error.hex",
                    )
                )
            else:
                data = bytes.fromhex(raw_payload)

        # ---- weight ----
        weight: int | None = None
        if "weight" not in item:
            errors.append(_err([*base, "weight"], "字段必填", "missing"))
        elif not _is_int(item["weight"]):
            errors.append(
                _err([*base, "weight"], "必须是整数", "type_error.integer")
            )
        elif not (MIN_WEIGHT <= item["weight"] <= MAX_WEIGHT):
            errors.append(
                _err(
                    [*base, "weight"],
                    f"必须在 {MIN_WEIGHT} 至 {MAX_WEIGHT} 之间",
                    "value_error.range",
                )
            )
        else:
            weight = item["weight"]

        if frag_id is not None and offset is not None and data is not None and weight is not None:
            parsed.append((index, frag_id, offset, data, weight))
        else:
            parsed.append(None)

    if errors:
        raise ValidationError(errors)

    # 字段全部合法后再做跨字段的越界检查(此时 target_length 必有效)。
    fragments: list[Fragment] = []
    for entry in parsed:
        assert entry is not None
        index, frag_id, offset, data, weight = entry
        end = offset + len(data)
        if end > target_length:  # type: ignore[operator]
            errors.append(
                _err(
                    ["fragments", index, "offset"],
                    f"片段越界: offset({offset}) + 载荷字节数({len(data)}) "
                    f"= {end}, 超出目标长度 {target_length}",
                    "value_error.bounds",
                )
            )
            continue
        fragments.append(Fragment(id=frag_id, offset=offset, payload=data, weight=weight))

    if errors:
        raise ValidationError(errors)

    return target_length, fragments  # type: ignore[return-value]
