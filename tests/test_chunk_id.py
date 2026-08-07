from api.pipeline import get_chunk_id


def test_get_chunk_id_is_deterministic():
    text = "FILE PATH: app.py\nEXTENSION: .py\nCODE:\nprint('hi')"

    assert get_chunk_id(text) == get_chunk_id(text)


def test_get_chunk_id_differs_for_different_content():
    a = "FILE PATH: app.py\nEXTENSION: .py\nCODE:\nprint('hi')"
    b = "FILE PATH: app.py\nEXTENSION: .py\nCODE:\nprint('bye')"

    assert get_chunk_id(a) != get_chunk_id(b)


def test_get_chunk_id_is_a_sha256_hex_digest():
    chunk_id = get_chunk_id("anything")

    assert isinstance(chunk_id, str)
    assert len(chunk_id) == 64
    assert all(c in "0123456789abcdef" for c in chunk_id)
