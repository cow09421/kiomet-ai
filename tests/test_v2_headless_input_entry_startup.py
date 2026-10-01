import asyncio
import hashlib

import pytest

from tools.v2_headless_research import (
    load_input_entry_observer,
    read_controlled_document_observer_status,
    register_input_entry_before_controlled_page,
)


class StubPage:
    def __init__(self, url):
        self.url = url


class StubContext:
    def __init__(self, pages=()):
        self.pages = list(pages)
        self.events = []

    async def add_init_script(self, *, script):
        self.events.append(('init_script', script))

    async def new_page(self):
        self.events.append(('new_page', None))
        page = object()
        self.pages.append(page)
        return page


class StubObserverPage:
    def __init__(self, observed):
        self.observed = observed
        self.script = None

    async def evaluate(self, script):
        self.script = script
        return self.observed


def test_input_entry_observer_is_registered_before_controlled_page(tmp_path):
    path = tmp_path / 'input_entry.js'
    source = 'window.testInputEntryObserver = true;\n'
    path.write_bytes(source.encode('utf8'))

    loaded, digest = load_input_entry_observer(path)
    assert loaded == source
    assert digest == hashlib.sha256(source.encode('utf8')).hexdigest()

    async def create_page_with_blank(blank_pages=()):
        context = StubContext(pages=blank_pages)
        blank_count = await register_input_entry_before_controlled_page(context, loaded)
        await context.new_page()
        return context, blank_count

    empty_context, blank_count = asyncio.run(create_page_with_blank())
    assert blank_count == 0
    assert [event[0] for event in empty_context.events] == ['init_script', 'new_page']

    blank_context, blank_count = asyncio.run(create_page_with_blank([StubPage('about:blank')]))
    assert blank_count == 1
    assert [event[0] for event in blank_context.events] == ['init_script', 'new_page']

    for url in ('https://kiomet.com/', 'about:blank#fragment'):
        existing_page = StubContext(pages=[StubPage(url)])
        with pytest.raises(RuntimeError, match='after a nonblank page already exists'):
            asyncio.run(register_input_entry_before_controlled_page(existing_page, loaded))
        assert existing_page.events == []

    with pytest.raises(RuntimeError, match='source is unavailable'):
        load_input_entry_observer(tmp_path / 'missing.js')


def test_controlled_document_status_requires_untouched_loading_bootstrap():
    status = {
        'installed': True,
        'ready_state_at_install': 'loading',
        'document_loading_at_install': True,
        'armed_once': False,
        'status': 'DISARMED',
    }
    page = StubObserverPage({'controlled_document_observer_status': status,
                             'document_time_origin_ms': 12345.5})
    result = asyncio.run(read_controlled_document_observer_status(page))
    assert result == {'controlled_document_observer_status': status,
                      'document_time_origin_ms': 12345.5}
    assert 'inputEntryObserver.v1' in page.script
    assert 'status()' in page.script
    assert 'tower' not in page.script.lower()

    for changed in (
        {'installed': False},
        {'installed': True, 'status': 'ARMED'},
        {'installed': True, 'status': 'DISARMED', 'armed_once': True},
        {'installed': True, 'status': 'DISARMED', 'armed_once': False,
         'document_loading_at_install': False},
        {'installed': True, 'status': 'DISARMED', 'armed_once': False,
         'document_loading_at_install': True, 'ready_state_at_install': 'interactive'},
    ):
        invalid = StubObserverPage({'controlled_document_observer_status': changed,
                                    'document_time_origin_ms': 12345.5})
        with pytest.raises(RuntimeError, match='bootstrap status failed closed validation'):
            asyncio.run(read_controlled_document_observer_status(invalid))

    bad_origin = StubObserverPage({'controlled_document_observer_status': status,
                                   'document_time_origin_ms': True})
    with pytest.raises(RuntimeError, match='time origin is malformed'):
        asyncio.run(read_controlled_document_observer_status(bad_origin))
