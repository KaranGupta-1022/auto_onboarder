from api.chunking import CHUNK_SIZE, MIN_BODY_CHARS, FILE_HEADER, chunk_file, chunk_repo_document


def test_chunk_file_below_min_body_chars_is_dropped():
    full_path = "backend/__init__.py"
    block = full_path  # nothing after the path line -> empty body

    chunks, metadatas = chunk_file(full_path, block)

    assert chunks == []
    assert metadatas == []


def test_chunk_file_at_min_body_chars_is_kept():
    full_path = "app.py"
    block = full_path + ("x" * MIN_BODY_CHARS)

    chunks, metadatas = chunk_file(full_path, block)

    assert len(chunks) == 1
    assert metadatas[0]["path"] == full_path
    assert metadatas[0]["extension"] == ".py"


def test_chunk_file_exact_multiple_of_chunk_size_has_no_trailing_empty_chunk():
    full_path = "app.py"
    block = full_path + ("x" * (2 * CHUNK_SIZE - len(full_path)))
    assert len(block) == 2 * CHUNK_SIZE

    chunks, metadatas = chunk_file(full_path, block)

    assert len(chunks) == 2
    assert len(metadatas) == 2


def test_chunk_repo_document_splits_on_file_header_and_tags_path():
    content = (
        f"{FILE_HEADER}src/app.py\n"
        + "print('hello')\n" * 5
        + f"{FILE_HEADER}README.md\n"
        + "This project does things.\n" * 5
    )

    chunks, metadatas, skipped = chunk_repo_document(content)

    assert skipped == []
    paths = {m["path"] for m in metadatas}
    assert paths == {"src/app.py", "README.md"}


def test_chunk_repo_document_skips_near_empty_file():
    content = (
        f"{FILE_HEADER}empty.py\n\n"
        f"{FILE_HEADER}app.py\n" + "x" * 100
    )

    chunks, metadatas, skipped = chunk_repo_document(content)

    assert "empty.py" in skipped
    assert all(m["path"] != "empty.py" for m in metadatas)
