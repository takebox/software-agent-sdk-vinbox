from handprint.sdk.context import Track


def test_load_markdown_without_frontmatter(tmp_path):
    """Test loading a markdown file without frontmatter."""
    content = "# Test Content\nThis is a test markdown file without frontmatter."
    path = tmp_path / "test.md"
    path.write_text(content)

    track = Track.load(path=path)

    # Verify it's loaded as a repo track with default values
    assert track.trigger is None
    assert track.name == "test"  # Name comes from path.stem
    assert track.content == content


def test_load_markdown_with_empty_frontmatter(tmp_path):
    """Test loading a markdown file with empty frontmatter."""
    content = (
        "---\n---\n# Test Content\nThis is a test markdown file with empty frontmatter."
    )
    path = tmp_path / "test.md"
    path.write_text(content)

    track = Track.load(path=path)

    # Verify it's loaded as a repo track with default values
    assert track.trigger is None
    assert track.name == "test"  # Name comes from path.stem
    assert (
        track.content
        == "# Test Content\nThis is a test markdown file with empty frontmatter."
    )


def test_load_markdown_with_partial_frontmatter(tmp_path):
    """Test loading a markdown file with partial frontmatter."""
    content = """---
name: custom_name
---
# Test Content
This is a test markdown file with partial frontmatter."""
    path = tmp_path / "test.md"
    path.write_text(content)

    track = Track.load(path=path)

    # Verify it uses provided name but default values for other fields
    assert track.trigger is None
    assert track.name == "custom_name"
    assert (
        track.content
        == "# Test Content\nThis is a test markdown file with partial frontmatter."
    )


def test_load_markdown_with_full_frontmatter(tmp_path):
    """Test loading a markdown file with full frontmatter still works."""
    content = """---
name: test_agent
type: repo
agent: CustomAgent
version: 2.0.0
---
# Test Content
This is a test markdown file with full frontmatter."""
    path = tmp_path / "test.md"
    path.write_text(content)

    track = Track.load(path=path)

    # Verify all provided values are used
    assert track.trigger is None
    assert track.name == "test_agent"
    assert (
        track.content
        == "# Test Content\nThis is a test markdown file with full frontmatter."
    )
