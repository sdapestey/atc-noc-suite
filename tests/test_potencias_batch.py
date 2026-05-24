"""POST /potencias/batch para consulta masiva."""


def test_potencias_batch_parallel_tokens(client, monkeypatch):
    calls = []

    def fake_rama(rama):
        calls.append(rama)
        return [{"AID": rama, "TX": 1.0, "RX": -20.0}]

    monkeypatch.setattr("web.routes.consultar_rama_potencias", fake_rama)

    r = client.post(
        "/potencias/batch",
        json={"values": ["SI03-RATC-0-000405", "SI03-RATC-0-000406"]},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert "items" in data
    assert len(data["items"]) == 2
    assert data["items"]["SI03-RATC-0-000405"][0]["AID"] == "SI03-RATC-0-000405"
    assert set(calls) == {"SI03-RATC-0-000405", "SI03-RATC-0-000406"}


def test_potencias_batch_requires_values(client):
    r = client.post("/potencias/batch", json={"values": []})
    assert r.status_code == 400
