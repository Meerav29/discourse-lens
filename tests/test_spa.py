import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.spa import spa_router


@pytest.fixture
def client(tmp_path):
    build = tmp_path / "build"
    (build / "_app").mkdir(parents=True)
    (build / "index.html").write_text("<html>app</html>")
    (build / "_app" / "main.js").write_text("console.log(1)")
    (tmp_path / "secret.txt").write_text("outside the build")

    app = FastAPI()

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    app.include_router(spa_router(build))
    return TestClient(app)


def test_static_file_is_served(client):
    r = client.get("/_app/main.js")
    assert r.status_code == 200
    assert r.text == "console.log(1)"


def test_client_routes_fall_back_to_index(client):
    for path in ("/", "/analysis/abc", "/analysis/abc/timeline"):
        r = client.get(path)
        assert r.status_code == 200, path
        assert r.text == "<html>app</html>"


def test_api_routes_win_and_unknown_api_paths_404(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/api/nope").status_code == 404


def test_cannot_escape_build_dir(client):
    r = client.get("/..%2Fsecret.txt")
    assert "outside the build" not in r.text
