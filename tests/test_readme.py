from pathlib import Path
import re


IMAGE_PATTERN = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


def test_readme_screenshot_links_are_absolute_urls():
    readme = Path("README.md").read_text(encoding="utf-8")
    image_links = IMAGE_PATTERN.findall(readme)
    screenshot_links = [link for link in image_links if "assets/screenshots/" in link]

    assert screenshot_links
    assert all(link.startswith("https://") for link in screenshot_links)
