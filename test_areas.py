from app import AREAS, app, resolve_area


def test_areas():
    assert len(AREAS) == 7815
    assert resolve_area('Renon', 'Denpasar', 'Bali')['id'] == '449'
    assert resolve_area('Renon, Kota Denpasar, Provinsi Bali')['id'] == '449'
    assert resolve_area('Karanganyar') is None

    with app.test_client() as client:
        response = client.get('/areas/search?q=renon denpasar')
        assert response.status_code == 200
        assert response.get_json()[0]['id'] == '449'


if __name__ == '__main__':
    test_areas()
    print('Area checks passed')