import os

from app import AREAS, app, get_dashscope_base_url, resolve_area


def test_areas():
    assert len(AREAS) == 7815
    assert resolve_area('Renon', 'Denpasar', 'Bali')['id'] == '449'
    assert resolve_area('Renon, Kota Denpasar, Provinsi Bali')['id'] == '449'
    assert resolve_area('Karanganyar') is None

    with app.test_client() as client:
        response = client.get('/areas/search?q=renon denpasar')
        assert response.status_code == 200
        assert response.get_json()[0]['id'] == '449'


def test_dashscope_base_url():
    original_url = os.environ.get('SG_DASHSCOPE_URL')
    try:
        os.environ['SG_DASHSCOPE_URL'] = 'https://example.com/api/v1/'
        assert get_dashscope_base_url() == 'https://example.com/api/v1'

        os.environ['SG_DASHSCOPE_URL'] = 'https://example.com/compatible-mode/v1'
        assert get_dashscope_base_url() == 'https://example.com/api/v1'
    finally:
        if original_url is None:
            os.environ.pop('SG_DASHSCOPE_URL', None)
        else:
            os.environ['SG_DASHSCOPE_URL'] = original_url


if __name__ == '__main__':
    test_areas()
    test_dashscope_base_url()
    print('Area checks passed')
