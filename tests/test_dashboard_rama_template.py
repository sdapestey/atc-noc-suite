"""La página /dashboard/rama redirige al árbol OLT/LT; APIs RAMA siguen activas."""


def test_dash_rama_redirects_to_olt(client):
    r = client.get("/dashboard/rama")
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/dashboard/olt")


def test_dash_rama_redirect_preserves_query(client):
    r = client.get("/dashboard/rama", query_string={"q": "MR01-RATC"})
    assert r.status_code == 302
    loc = r.headers["Location"]
    assert "/dashboard/olt" in loc
    assert "q=MR01-RATC" in loc
