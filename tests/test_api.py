"""/api/reconstruct 的 HTTP 层测试, 重点核对 422 与字段位置。"""

from __future__ import annotations

import pytest

from backend.main import app
from fastapi.testclient import TestClient


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=True)


def _frag(fid: str, offset: int, payload: str, weight: int) -> dict:
    return {"id": fid, "offset": offset, "payload": payload, "weight": weight}


def test_healthz(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_happy_path_unique(client: TestClient) -> None:
    body = {
        "target_length": 4,
        "fragments": [
            _frag("A", 0, "1122", 10),
            _frag("B", 2, "2233", 10),
        ],
    }
    resp = client.post("/api/reconstruct", json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "UNIQUE"
    assert data["optimal"] == {"total_weight": 20, "fragment_count": 2}
    assert data["bodies"][0]["hex"] == "11222233"


def test_duplicate_id_reports_both_positions(client: TestClient) -> None:
    body = {
        "target_length": 4,
        "fragments": [
            _frag("DUP", 0, "11", 1),
            _frag("DUP", 1, "22", 1),
        ],
    }
    resp = client.post("/api/reconstruct", json=body)
    assert resp.status_code == 422
    errors = resp.json()["detail"]
    dup_errors = [e for e in errors if e["type"] == "value_error.duplicate"]
    assert len(dup_errors) == 1
    assert dup_errors[0]["loc"] == ["body", "fragments", 1, "id"]


def test_malformed_hex_points_at_payload(client: TestClient) -> None:
    body = {
        "target_length": 2,
        "fragments": [
            _frag("A", 0, "XYZ!", 1),
            _frag("B", 0, "AB", 1),
        ],
    }
    resp = client.post("/api/reconstruct", json=body)
    assert resp.status_code == 422
    locs = [tuple(e["loc"]) for e in resp.json()["detail"]]
    assert ("body", "fragments", 0, "payload") in locs


def test_odd_hex_length_rejected(client: TestClient) -> None:
    body = {
        "target_length": 2,
        "fragments": [
            _frag("A", 0, "ABC", 1),
            _frag("B", 0, "AB", 1),
        ],
    }
    resp = client.post("/api/reconstruct", json=body)
    assert resp.status_code == 422


def test_empty_payload_rejected(client: TestClient) -> None:
    body = {
        "target_length": 2,
        "fragments": [
            _frag("A", 0, "", 1),
            _frag("B", 0, "AB", 1),
        ],
    }
    resp = client.post("/api/reconstruct", json=body)
    assert resp.status_code == 422
    assert resp.json()["detail"][0]["loc"][-1] == "payload"


def test_out_of_bounds_points_at_offset(client: TestClient) -> None:
    body = {
        "target_length": 2,
        "fragments": [
            _frag("A", 1, "AABB", 1),  # 1 + 2 = 3 > 2
            _frag("B", 0, "CC", 1),
        ],
    }
    resp = client.post("/api/reconstruct", json=body)
    assert resp.status_code == 422
    errors = resp.json()["detail"]
    assert any(
        e["loc"] == ["body", "fragments", 0, "offset"]
        and e["type"] == "value_error.bounds"
        for e in errors
    )


def test_negative_offset_rejected(client: TestClient) -> None:
    body = {
        "target_length": 2,
        "fragments": [
            _frag("A", -1, "AB", 1),
            _frag("B", 0, "CC", 1),
        ],
    }
    resp = client.post("/api/reconstruct", json=body)
    assert resp.status_code == 422


def test_weight_out_of_range_rejected(client: TestClient) -> None:
    body = {
        "target_length": 1,
        "fragments": [
            _frag("A", 0, "AB", 0),
            _frag("B", 0, "AB", 1_000_001),
        ],
    }
    resp = client.post("/api/reconstruct", json=body)
    assert resp.status_code == 422
    locs = [tuple(e["loc"]) for e in resp.json()["detail"]]
    assert ("body", "fragments", 0, "weight") in locs
    assert ("body", "fragments", 1, "weight") in locs


def test_weight_one_million_accepted(client: TestClient) -> None:
    body = {
        "target_length": 1,
        "fragments": [
            _frag("A", 0, "AB", 1_000_000),
            _frag("B", 0, "AB", 1),
        ],
    }
    resp = client.post("/api/reconstruct", json=body)
    assert resp.status_code == 200
    assert resp.json()["optimal"]["total_weight"] == 1_000_001


@pytest.mark.parametrize(
    "length",
    [0, -1, 513],
)
def test_target_length_bounds(client: TestClient, length: int) -> None:
    body = {
        "target_length": length,
        "fragments": [_frag("A", 0, "00", 1), _frag("B", 0, "00", 1)],
    }
    resp = client.post("/api/reconstruct", json=body)
    assert resp.status_code == 422


@pytest.mark.parametrize("count", [1, 29])
def test_fragment_count_bounds(client: TestClient, count: int) -> None:
    body = {
        "target_length": 1,
        "fragments": [_frag(f"F{i}", 0, "00", 1) for i in range(count)],
    }
    resp = client.post("/api/reconstruct", json=body)
    assert resp.status_code == 422
    assert resp.json()["detail"][0]["loc"] == ["body", "fragments"]


def test_missing_field_loc(client: TestClient) -> None:
    body = {
        "target_length": 1,
        "fragments": [
            {"id": "A", "offset": 0, "payload": "00"},  # 缺 weight
            {"id": "B", "offset": 0, "payload": "00", "weight": 1},
        ],
    }
    resp = client.post("/api/reconstruct", json=body)
    assert resp.status_code == 422
    assert resp.json()["detail"][0]["loc"] == ["body", "fragments", 0, "weight"]


def test_bool_is_not_integer(client: TestClient) -> None:
    body = {
        "target_length": 1,
        "fragments": [
            {"id": "A", "offset": True, "payload": "00", "weight": 1},
            {"id": "B", "offset": 0, "payload": "00", "weight": 1},
        ],
    }
    resp = client.post("/api/reconstruct", json=body)
    assert resp.status_code == 422


def test_invalid_json_body(client: TestClient) -> None:
    resp = client.post(
        "/api/reconstruct",
        content="{not json",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"][0]["type"] == "parse_error"


def test_gap_scenario(client: TestClient) -> None:
    body = {
        "target_length": 3,
        "fragments": [
            _frag("A", 0, "00", 10),
            _frag("B", 2, "22", 10),
        ],
    }
    resp = client.post("/api/reconstruct", json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "IMPOSSIBLE"
    assert data["impossible_reason"] == "GAP"
    assert data["uncovered_positions"] == [1]


def test_ambiguous_scenario(client: TestClient) -> None:
    body = {
        "target_length": 1,
        "fragments": [
            _frag("A", 0, "10", 5),
            _frag("B", 0, "20", 5),
        ],
    }
    resp = client.post("/api/reconstruct", json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "AMBIGUOUS"
    assert [b["hex"] for b in data["bodies"]] == ["10", "20"]


# ---------- 候选阶梯 ----------

def test_response_without_ladder_size_has_no_ladder_key(client: TestClient) -> None:
    # 未启用阶梯时响应与原契约完全一致。
    body = {
        "target_length": 4,
        "fragments": [
            _frag("A", 0, "1122", 10),
            _frag("B", 2, "2233", 10),
        ],
    }
    resp = client.post("/api/reconstruct", json=body)
    assert resp.status_code == 200
    assert "ladder" not in resp.json()


def test_ladder_returns_top_n_distinct_bodies(client: TestClient) -> None:
    body = {
        "target_length": 2,
        "ladder_size": 3,
        "fragments": [
            _frag("X", 0, "00", 100),
            _frag("Y", 0, "01", 99),
            _frag("W", 0, "02", 98),
            _frag("Z", 1, "FF", 1),
        ],
    }
    resp = client.post("/api/reconstruct", json=body)
    assert resp.status_code == 200
    data = resp.json()
    ladder = data["ladder"]
    assert ladder["requested"] == 3
    assert ladder["exhausted"] is True
    entries = ladder["entries"]
    assert [(e["rank"], e["hex"], e["total_weight"], e["fragment_count"]) for e in entries] == [
        (1, "00FF", 101, 2),
        (2, "01FF", 100, 2),
        (3, "02FF", 99, 2),
    ]
    assert [e["diff_from_prev"] for e in entries] == [None, 0, 0]
    assert entries[0]["witness_fragment_ids"] == ["X", "Z"]
    # 原有裁决字段不受阶梯影响。
    assert data["status"] == "UNIQUE"
    assert data["optimal"] == {"total_weight": 101, "fragment_count": 2}


def test_ladder_dedupes_same_body_coverings(client: TestClient) -> None:
    body = {
        "target_length": 2,
        "ladder_size": 5,
        "fragments": [
            _frag("MAIN", 0, "0000", 10),
            _frag("DUP1", 0, "00", 5),
            _frag("DUP2", 1, "00", 5),
            _frag("ALT", 0, "0101", 9),
        ],
    }
    resp = client.post("/api/reconstruct", json=body)
    assert resp.status_code == 200
    ladder = resp.json()["ladder"]
    assert [e["hex"] for e in ladder["entries"]] == ["0000", "0101"]
    assert ladder["entries"][0]["witness_fragment_ids"] == ["DUP1", "DUP2", "MAIN"]
    assert ladder["exhausted"] is True


def test_ladder_empty_and_exhausted_when_impossible(client: TestClient) -> None:
    body = {
        "target_length": 3,
        "ladder_size": 4,
        "fragments": [
            _frag("A", 0, "00", 10),
            _frag("B", 2, "22", 10),
        ],
    }
    resp = client.post("/api/reconstruct", json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "IMPOSSIBLE"
    assert data["ladder"] == {"requested": 4, "exhausted": True, "entries": []}


@pytest.mark.parametrize("bad", [1, 6, "3", True, 2.5])
def test_ladder_size_validation_points_at_field(client: TestClient, bad: object) -> None:
    body = {
        "target_length": 2,
        "ladder_size": bad,
        "fragments": [
            _frag("A", 0, "00", 1),
            _frag("B", 1, "11", 1),
        ],
    }
    resp = client.post("/api/reconstruct", json=body)
    assert resp.status_code == 422
    locs = [tuple(e["loc"]) for e in resp.json()["detail"]]
    assert ("body", "ladder_size") in locs


def test_ladder_size_boundary_values_accepted(client: TestClient) -> None:
    for size in (2, 5):
        body = {
            "target_length": 2,
            "ladder_size": size,
            "fragments": [
                _frag("A", 0, "00", 1),
                _frag("B", 1, "11", 1),
            ],
        }
        resp = client.post("/api/reconstruct", json=body)
        assert resp.status_code == 200
        assert resp.json()["ladder"]["requested"] == size
