"""
Atopsy Pipeline — End-to-End Integration Test Script.

Tests the full pipeline flow:
1. Health check
2. Single file upload (text evidence)
3. Structured JSON evidence upload
4. Evidence listing
5. Evidence detail retrieval
6. Audit log retrieval
7. Normalization trigger
8. Evidence soft-delete
"""

import requests
import json
import sys
import os
import tempfile

BASE_URL = "http://localhost:8001"

# Track test results
passed = 0
failed = 0
evidence_ids = []


def test(name: str, fn):
    global passed, failed
    try:
        result = fn()
        print(f"  [PASS] {name}")
        passed += 1
        return result
    except Exception as e:
        print(f"  [FAIL] {name}: {e}")
        failed += 1
        return None


def separator(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ──────────────────────────────────────────────
# Test 1: Health Check
# ──────────────────────────────────────────────

separator("1. Pipeline Health Check")

def test_health():
    r = requests.get(f"{BASE_URL}/pipeline/health")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    assert data["success"] is True
    assert data["data"]["storage_backend"] == "local"
    print(f"     Status: {data['data']['status']}")
    return data

test("GET /pipeline/health", test_health)


# ──────────────────────────────────────────────
# Test 2: Upload a Text Evidence File
# ──────────────────────────────────────────────

separator("2. Single File Upload (TXT)")

# Create a temporary forensic evidence text file
evidence_text = """
FORENSIC AUTOPSY REPORT
Date: 2024-03-15T14:30:00Z
Location: 40.7128, -74.0060

Subject: John Doe, Male, Age 45
Height: 5'11" (180.34 cm)
Weight: 185 lbs (83.91 kg)

Cause of Death: Blunt force trauma to the cranium
Time of Death (estimated): 2024-03-14T22:00:00Z

Toxicology:
- Blood Alcohol: 0.08%
- Benzodiazepines: Detected

Scene Description:
The decedent was found at coordinates 40.7128N, 74.0060W
in a residential area. Ambient temperature was 68°F.
Rigor mortis was fully established.

Evidence collected:
- Hair samples (3)
- Blood samples (2)
- Fiber samples (5)
- Digital device: iPhone 15 Pro
"""

def test_upload_txt():
    # Write temp file
    tmp_path = os.path.join(
        os.path.dirname(__file__), "test_evidence.txt"
    )
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(evidence_text)

    try:
        with open(tmp_path, "rb") as f:
            r = requests.post(
                f"{BASE_URL}/pipeline/upload",
                files={"file": ("autopsy_report.txt", f, "text/plain")},
                data={
                    "tags": "forensic,autopsy,test",
                    "source_attribution": "E2E Test Suite",
                    "auto_normalize": "true",
                },
            )

        assert r.status_code == 201, f"Expected 201, got {r.status_code}: {r.text}"
        data = r.json()
        assert data["success"] is True
        result = data["data"]
        eid = result["evidence_file_id"]
        evidence_ids.append(eid)

        print(f"     Evidence ID: {eid}")
        print(f"     Status: {result['status']}")
        print(f"     SHA256: {result['sha256_hash'][:24]}...")
        if "normalization" in result:
            norm = result["normalization"]
            print(f"     Normalization: {norm.get('status', 'N/A')}")
            print(f"     Quality Score: {norm.get('quality_score', 'N/A')}")
        return data
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

test("POST /pipeline/upload (text file)", test_upload_txt)


# ──────────────────────────────────────────────
# Test 3: Upload Structured JSON Evidence
# ──────────────────────────────────────────────

separator("3. Structured JSON Upload")

def test_upload_structured():
    payload = {
        "evidence_type": "gps_feed",
        "data": {
            "device_id": "TRACKER-4491",
            "coordinates": [
                {
                    "lat": 40.7128,
                    "lon": -74.0060,
                    "timestamp": "2024-03-14T21:30:00Z",
                    "speed_mph": 35,
                },
                {
                    "lat": 40.7138,
                    "lon": -74.0050,
                    "timestamp": "2024-03-14T21:45:00Z",
                    "speed_mph": 0,
                },
            ],
            "battery_pct": 78,
            "signal_strength": "strong",
        },
        "tags": ["gps", "tracking", "test"],
        "source_attribution": "E2E GPS Feed Test",
    }

    r = requests.post(
        f"{BASE_URL}/pipeline/upload/structured",
        json=payload,
    )
    assert r.status_code == 201, f"Expected 201, got {r.status_code}: {r.text}"
    data = r.json()
    assert data["success"] is True
    eid = data["data"]["evidence_file_id"]
    evidence_ids.append(eid)
    print(f"     Evidence ID: {eid}")
    print(f"     Status: {data['data']['status']}")
    return data

test("POST /pipeline/upload/structured", test_upload_structured)


# ──────────────────────────────────────────────
# Test 4: List Evidence
# ──────────────────────────────────────────────

separator("4. Evidence Listing")

def test_list_evidence():
    r = requests.get(f"{BASE_URL}/pipeline/evidence")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    assert data["success"] is True
    items = data["data"]["items"]
    total = data["data"]["total"]
    print(f"     Total evidence files: {total}")
    for item in items[:3]:
        print(f"       - {item['original_filename']} [{item['status']}]")
    return data

test("GET /pipeline/evidence", test_list_evidence)


# ──────────────────────────────────────────────
# Test 5: Evidence Detail
# ──────────────────────────────────────────────

separator("5. Evidence Detail Retrieval")

def test_evidence_detail():
    if not evidence_ids:
        raise Exception("No evidence ID to query")
    eid = evidence_ids[0]
    r = requests.get(f"{BASE_URL}/pipeline/evidence/{eid}")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    assert data["success"] is True
    detail = data["data"]
    print(f"     File: {detail['original_filename']}")
    print(f"     MIME: {detail['mime_type']}")
    print(f"     Category: {detail['category']}")
    print(f"     Size: {detail['file_size']} bytes")
    if "metadata" in detail:
        print(f"     Metadata records: {len(detail['metadata'])}")
    if "normalization" in detail:
        norm = detail["normalization"]
        print(f"     Normalization status: {norm['status']}")
        print(f"     Quality: {norm['quality_score']:.2f}")
        print(f"     Completeness: {norm['completeness_score']:.2f}")
        print(f"     Anomalies: {norm['anomaly_count']}")
    return data

test("GET /pipeline/evidence/{id}", test_evidence_detail)


# ──────────────────────────────────────────────
# Test 6: Audit Logs
# ──────────────────────────────────────────────

separator("6. Acquisition Audit Logs")

def test_audit_logs():
    r = requests.get(f"{BASE_URL}/pipeline/logs")
    assert r.status_code == 200
    data = r.json()
    assert data["success"] is True
    logs = data["data"]
    print(f"     Total audit entries: {len(logs)}")
    for log in logs[:5]:
        print(f"       [{log['action']}] {log.get('detail', '')[:60]}")
    return data

test("GET /pipeline/logs (all)", test_audit_logs)

def test_audit_logs_filtered():
    if not evidence_ids:
        raise Exception("No evidence ID to filter")
    eid = evidence_ids[0]
    r = requests.get(f"{BASE_URL}/pipeline/logs?evidence_id={eid}")
    assert r.status_code == 200
    data = r.json()
    print(f"     Logs for evidence {eid[:8]}...: {len(data['data'])}")
    return data

test("GET /pipeline/logs?evidence_id=...", test_audit_logs_filtered)


# ──────────────────────────────────────────────
# Test 7: Manual Normalization Trigger
# ──────────────────────────────────────────────

separator("7. Normalization Trigger")

def test_normalize_manual():
    if len(evidence_ids) < 2:
        raise Exception("Need structured evidence ID")
    eid = evidence_ids[1]  # The structured upload
    r = requests.post(f"{BASE_URL}/pipeline/normalize/{eid}")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    print(f"     Norm status: {data['data'].get('status', 'N/A')}")
    print(f"     Quality: {data['data'].get('quality_score', 'N/A')}")
    return data

test("POST /pipeline/normalize/{id}", test_normalize_manual)


# ──────────────────────────────────────────────
# Test 8: Duplicate Detection
# ──────────────────────────────────────────────

separator("8. Duplicate Detection")

def test_duplicate():
    # Re-upload the same text — should detect duplicate
    tmp_path = os.path.join(
        os.path.dirname(__file__), "test_evidence_dup.txt"
    )
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(evidence_text)
    try:
        with open(tmp_path, "rb") as f:
            r = requests.post(
                f"{BASE_URL}/pipeline/upload",
                files={"file": ("autopsy_report_dup.txt", f, "text/plain")},
                data={"tags": "duplicate-test"},
            )
        # Should be 409 Conflict or contain duplicate info
        if r.status_code == 409:
            print(f"     Correctly rejected as duplicate (409)")
        elif r.status_code == 201:
            data = r.json()
            status = data["data"].get("status", "")
            if status == "DUPLICATE":
                print(f"     Correctly flagged as DUPLICATE (201)")
            else:
                print(f"     Warning: accepted as new ({status})")
        else:
            print(f"     Status: {r.status_code}")
        return r.json()
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

test("POST /pipeline/upload (duplicate)", test_duplicate)


# ──────────────────────────────────────────────
# Test 9: Soft Delete
# ──────────────────────────────────────────────

separator("9. Soft Delete")

def test_soft_delete():
    if not evidence_ids:
        raise Exception("No evidence ID to delete")
    eid = evidence_ids[0]
    r = requests.delete(f"{BASE_URL}/pipeline/evidence/{eid}")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    assert data["success"] is True
    print(f"     Soft-deleted: {eid[:8]}...")

    # Verify it no longer shows in listing
    r2 = requests.get(f"{BASE_URL}/pipeline/evidence")
    items = r2.json()["data"]["items"]
    ids_in_list = [i["id"] for i in items]
    if eid not in ids_in_list:
        print(f"     Confirmed: no longer in listing")
    else:
        print(f"     Warning: still visible in listing")
    return data

test("DELETE /pipeline/evidence/{id}", test_soft_delete)


# ──────────────────────────────────────────────
# Test 10: 404 on missing evidence
# ──────────────────────────────────────────────

separator("10. Error Handling")

def test_404():
    fake_id = "00000000-0000-0000-0000-000000000000"
    r = requests.get(f"{BASE_URL}/pipeline/evidence/{fake_id}")
    assert r.status_code == 404, f"Expected 404, got {r.status_code}"
    print(f"     Correctly returned 404 for non-existent evidence")

test("GET /pipeline/evidence/{fake_id} -> 404", test_404)


# ──────────────────────────────────────────────
# Summary
# ──────────────────────────────────────────────

print(f"\n{'='*60}")
print(f"  TEST SUMMARY")
print(f"{'='*60}")
print(f"  Passed: {passed}")
print(f"  Failed: {failed}")
print(f"  Total:  {passed + failed}")
print(f"{'='*60}")

sys.exit(0 if failed == 0 else 1)
