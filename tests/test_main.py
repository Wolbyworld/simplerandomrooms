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
