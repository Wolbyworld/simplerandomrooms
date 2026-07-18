from pathlib import Path


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

def test_root_endpoint(client):
    response = client.get("/")
    assert response.status_code == 200
    assert 'id="draw-setup"' in response.text
    assert 'id="draw-now-button"' in response.text
    assert 'value="numbers"' in response.text
    assert 'value="list"' in response.text
    assert 'value="coin"' in response.text
    assert 'value="dice"' in response.text


def test_desktop_mode_switches_keep_the_setup_panel_stable():
    styles = Path("app/static/css/styles.css").read_text(encoding="utf-8")

    assert "@media (min-width: 781px)" in styles
    assert "height: 220px" in styles
    assert '.mode-config[data-config="list"]:not([hidden])' in styles
