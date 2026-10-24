"""Dependency-free checks for the public pages and their discovery paths."""
import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://thelastie.github.io/Gruzovoz/'
SLUGS = ('', 'perevozka-mebeli-ufa/', 'kvartirnyy-pereezd-ufa/',
         'gazel-s-gruzchikami-ufa/', 'mezhgorod-iz-ufy/')


class Page(HTMLParser):
    def __init__(self, path):
        super().__init__()
        self.links, self.ids, self.canonicals, self.descriptions = [], [], [], []
        self.h1 = 0
        self.title, self.schema = '', []
        self.in_title = self.in_schema = False
        self.schema_text = ''
        self.feed(path.read_text(encoding='utf-8'))

    def handle_starttag(self, tag, pairs):
        attrs = dict(pairs)
        if 'id' in attrs:
            self.ids.append(attrs['id'])
        if tag == 'h1':
            self.h1 += 1
        if tag == 'title':
            self.in_title = True
        if tag == 'link' and attrs.get('rel') == 'canonical':
            self.canonicals.append(attrs.get('href'))
        if tag == 'meta' and attrs.get('name') == 'description':
            self.descriptions.append(attrs.get('content', ''))
        if tag == 'meta' and attrs.get('name') == 'robots':
            assert 'noindex' not in attrs.get('content', '').lower()
        if tag == 'a' and 'href' in attrs:
            self.links.append(attrs['href'])
        if tag in ('img', 'script', 'iframe') and attrs.get('src'):
            self.links.append(attrs['src'])
        if tag == 'link' and attrs.get('rel') == 'stylesheet':
            self.links.append(attrs['href'])
        if tag == 'script' and attrs.get('type') == 'application/ld+json':
            self.in_schema, self.schema_text = True, ''

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        if self.in_schema:
            self.schema_text += data

    def handle_endtag(self, tag):
        if tag == 'title':
            self.in_title = False
        if tag == 'script' and self.in_schema:
            self.schema.append(json.loads(self.schema_text))
            self.in_schema = False


def verify():
    pages = {slug: Page(ROOT / slug / 'index.html') for slug in SLUGS}
    sitemap = ET.parse(ROOT / 'sitemap.xml')
    urls = [node.text for node in sitemap.findall('.//{*}loc')]
    assert set(urls) == {BASE + slug for slug in SLUGS}, 'sitemap URL mismatch'
    assert len(urls) == len(set(urls)), 'duplicate sitemap URLs'
    assert len({p.title for p in pages.values()}) == len(pages), 'duplicate titles'
    assert len({p.descriptions[0] for p in pages.values()}) == len(pages), 'duplicate descriptions'
    checked = 0
    for slug, page in pages.items():
        assert page.h1 == 1, f'{slug}: expected one h1'
        assert page.canonicals == [BASE + slug], f'{slug}: canonical'
        assert len(page.descriptions) == 1 and page.descriptions[0], f'{slug}: description'
        assert page.title and page.schema, f'{slug}: missing metadata'
        assert len(page.ids) == len(set(page.ids)), f'{slug}: duplicate id'
        nodes = [node for doc in page.schema for node in doc.get('@graph', [doc])]
        if slug:
            service = next(node for node in nodes if node.get('@type') == 'Service')
            assert service['provider']['@id'] == BASE + '#business'
            crumbs = next(node for node in nodes if node.get('@type') == 'BreadcrumbList')
            assert crumbs['itemListElement'][-1]['item'] == BASE + slug
        else:
            business = next(node for node in nodes if node.get('@type') == 'MovingCompany')
            assert business['@id'] == BASE + '#business'
            assert business['telephone'].replace('-', '') == '+79872526511'
        for href in page.links:
            url = urlsplit(href)
            if url.scheme or url.netloc:
                continue
            target = (ROOT / slug / unquote(url.path)).resolve()
            assert target.is_relative_to(ROOT), f'{slug}: escapes project: {href}'
            if target.is_dir():
                target /= 'index.html'
            assert target.is_file(), f'{slug}: broken target {href}'
            if url.fragment and target.suffix == '.html':
                dest = Page(target)
                assert unquote(url.fragment) in dest.ids, f'{slug}: broken fragment {href}'
            checked += 1
        print(f'PASS {slug or "/"}: title, canonical, h1, schema and links')
    for slug in SLUGS[1:]:
        assert slug in pages[''].links, f'not discoverable from home: {slug}'
        assert '../' in pages[slug].links, f'no return link: {slug}'
    print(f'PASS sitemap: {len(urls)} URLs; {checked} local targets; discovery links')


if __name__ == '__main__':
    verify()
