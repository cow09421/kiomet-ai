import asyncio

import pytest

from kiomet_ai.v2.observe.extractor import ClientExtractor, is_official_client_url


@pytest.mark.parametrize("url", [
    "https://kiomet.com/",
    "https://kiomet.com/ABCDEF/",  # Synthetic boundary value, not an invite code.
])
def test_official_client_url_accepts_only_documented_route_shapes(url):
    assert is_official_client_url(url)


@pytest.mark.parametrize("url", [
    "http://kiomet.com/",
    "https://KIOMET.com/",
    "https://kiomet.com/abcdef/",
    "https://kiomet.com/ABCDE/",
    "https://kiomet.com/ABCDEFG/",
    "https://kiomet.com/ABCDEF",
    "https://kiomet.com/ABCDEF/extra/",
    "https://kiomet.com/%2FABCDEF/",
    "https://kiomet.com/ABC%2FDE/",
    "https://kiomet.com/ABCDEF/?x=1",
    "https://kiomet.com/ABCDEF/#fragment",
    "https://kiomet.com:443/ABCDEF/",
    "https://user@kiomet.com/ABCDEF/",
    "https://www.kiomet.com/ABCDEF/",
    "https://kiomet.com.evil.example/ABCDEF/",
    None,
    7,
])
def test_official_client_url_rejects_unapproved_origin_or_path_variants(url):
    assert not is_official_client_url(url)


def test_attach_rejects_unapproved_route_before_opening_cdp_session():
    class Context:
        calls = 0

        async def new_cdp_session(self, _page):
            self.calls += 1
            raise AssertionError("URL rejection must precede CDP attachment")

    class Page:
        url = "https://kiomet.com/ABCDEF/?x=1"
        context = Context()

    extractor = ClientExtractor(Page())
    with pytest.raises(ValueError, match="official client page required"):
        asyncio.run(extractor.attach())
    assert extractor.cdp is None
    assert Page.context.calls == 0
