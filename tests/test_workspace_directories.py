"""Directory archive and recursive deletion regression tests."""

import io
import zipfile

import pytest

from flowgraph.server.workspace import Workspace


def test_directory_archive_preserves_nested_and_empty_folders(tmp_path):
    workspace = Workspace(tmp_path)
    workspace.write("data/nested/test.txt", b"hello" * 100)
    (tmp_path / "data/empty").mkdir()
    (tmp_path / "data/link").symlink_to(tmp_path / "data/nested/test.txt")
    archive = workspace.read("data", 10000)
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        assert set(zipped.namelist()) == {
            "data/",
            "data/nested/",
            "data/nested/test.txt",
            "data/empty/",
        }
        assert zipped.read("data/nested/test.txt") == b"hello" * 100
        assert zipped.getinfo("data/nested/test.txt").compress_type == zipfile.ZIP_DEFLATED


def test_directory_archive_enforces_size_limit(tmp_path):
    workspace = Workspace(tmp_path)
    workspace.write("data/test.txt", b"x" * 1000)
    with pytest.raises(ValueError, match="download size limit"):
        workspace.read("data", 100)


def test_directory_delete_is_recursive_and_does_not_follow_links(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    workspace = Workspace(root)
    workspace.write("data/nested/test.txt", b"hello")
    outside = tmp_path / "keep.txt"
    outside.write_text("keep")
    (root / "data/link").symlink_to(outside)
    workspace.delete("data")
    assert not (root / "data").exists()
    assert outside.read_text() == "keep"


@pytest.mark.parametrize("path", [".", "..", "../outside", "/", ""])
def test_directory_actions_reject_root_and_traversal(tmp_path, path):
    workspace = Workspace(tmp_path)
    with pytest.raises(ValueError):
        workspace.read(path, 10000)
    with pytest.raises(ValueError):
        workspace.delete(path)
