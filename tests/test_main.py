def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

# This test will fail until we create the index.html template
def test_root_endpoint(client):
    response = client.get("/")
    assert response.status_code == 200
