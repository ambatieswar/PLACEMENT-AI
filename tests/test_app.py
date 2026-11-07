import pytest

from app import create_app


@pytest.fixture()
def client(tmp_path):
    app = create_app({
        'TESTING': True,
        'SECRET_KEY': 'test-secret',
        'GEMINI_API_KEY': '',
        'MISTRAL_API_KEY': '',
        'FALLBACK_STORAGE_MODE': 'memory',
        'FALLBACK_STORAGE_PATH': str(tmp_path / 'store.json'),
    })
    return app.test_client()


def csrf(client):
    response = client.get('/login')
    assert response.status_code == 200
    with client.session_transaction() as session:
        return session['_csrf_token']


def test_status_reports_local_fallback(client):
    response = client.get('/api/status')
    assert response.status_code == 200
    assert response.json['dependencies']['mongodb']['fallback'] is True


def test_signup_and_login_require_csrf(client):
    payload = {
        'email': 'test@example.com',
        'fullname': 'Test User',
        'password': 'StrongPass123!',
        'confirm_password': 'StrongPass123!',
    }
    assert client.post('/signup', data=payload).status_code == 400

    token = csrf(client)
    payload['csrf_token'] = token
    assert client.post('/signup', data=payload).status_code == 302
    assert client.post('/login', data={
        'csrf_token': token,
        'email': payload['email'],
        'password': payload['password'],
    }).status_code == 302


def test_ai_endpoint_reports_missing_provider(client):
    token = csrf(client)
    payload = {
        'csrf_token': token,
        'email': 'ai@example.com',
        'fullname': 'AI User',
        'password': 'StrongPass123!',
        'confirm_password': 'StrongPass123!',
    }
    client.post('/signup', data=payload)
    client.post('/login', data=payload)
    response = client.post(
        '/api/placement-predictor',
        headers={'X-CSRFToken': token},
        json={'skills': []},
    )
    assert response.status_code == 503
    assert 'GEMINI_API_KEY' in response.json['error']
