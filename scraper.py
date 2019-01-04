import re
import logging
import urllib

import bs4
import pandas
import requests

__all__ = ['get_page_info', 'try_scrape', 'redirect']

redirected_page = {}
readed_page = {}


def get_page_info(url, name=None, category=None, date=None, **kwargs):
    """Get page infos

    Parameters
    ----------
        url : str
            the url of the page to be parse
        name : str
            detected page name
        category : str
            potential page category
        date : str
            potential last modification date of the page
        kwargs : dict
            sink

    Return
    ------
        info : dict
    """
    soup = get_page(url)

    # category
    breadcrumb = soup.select('div.friendly div.path')
    if len(breadcrumb) > 0:
        category = re.sub(r'\s', '', breadcrumb[0].text)[5:]  # skip '現在位置'

    # date
    if not date:
        info_bar = soup.select('ul.info li')
        if len(info_bar) > 0:
            for item in info_bar:
                if item.text.strip().startswith('更新日期'):
                    date = item.find('span').text

    # name
    if name is None or str(name).strip() == '':
        title = soup.find('title')
        name = title.text

    return {
        'name': name,
        'url': url,
        'category': category,
        'date': date,
        'is_leaf': len(soup.select('div.cp')) > 0,  # SEEMS works
    }


def get_page(url):
    """Read the page.

    Parameters
    ----------
        url : str
            the url to be read

    Return
    ------
        soup : bs4.BeautifulSoup
            the parsed page
    """
    global readed_page, redirected_page
    logging.debug(f'Read page {url}')

    # check if the page would be redirected
    url = redirect(url)

    # use cache
    if url in readed_page:
        logging.debug(f'Returned with cache')
        return readed_page[url]

    # download
    response = requests.get(url)

    # log redirect
    if response.url != url:
        from_pat = make_matching_pattern(url)
        to_pat = make_matching_pattern(response.url)
        redirected_page[from_pat] = to_pat

    # parse & cache
    soup = bs4.BeautifulSoup(response.content, 'lxml')
    readed_page[response.url] = soup

    return soup


def make_matching_pattern(url):
    frag = urllib.parse.urlparse(url)
    pattern = (frag.scheme, frag.netloc, frag.path)

    query_set = tuple(urllib.parse.parse_qsl(frag.query))

    return pattern, query_set


def redirect(url):
    global redirected_page

    want_pat, want_qs = make_matching_pattern(url)
    want_qs = set(want_qs)
    for (from_pat, from_qs), (to_pat, to_qs) in redirected_page.items():
        from_qs = set(from_qs)
        if from_pat != want_pat:
            continue
        if not want_qs.issuperset(from_qs):
            continue

        new_qs = set(to_qs).union(want_qs - from_qs)
        query = urllib.parse.urlencode(list(new_qs))
        return f'{to_pat[0]}://{to_pat[1]}{to_pat[2]}?{query}'

    return url


def add_large_pagesize(url):
    frag = urllib.parse.urlparse(url)

    queryset = urllib.parse.parse_qsl(frag.query)
    queryset.append(('pagesize', '10000'))
    queryset = list(set(queryset))

    query = urllib.parse.urlencode(queryset)
    return f'{frag.scheme}://{frag.netloc}{frag.path}?{query}'


def try_scrape(url):
    """Check the page type.

    Return
    ------
        df : pandas.DataFrame
            a list of links with name and url fields IF successfully scraped,
            or None on fialed
    """
    try:
        return scrape_table(url)
    except TypeError:
        ...

    try:
        return scrape_album(url)
    except TypeError:
        ...

    try:
        return scrape_appendix(url)
    except TypeError:
        ...

    try:
        return scrape_list(url)
    except TypeError:
        ...

    try:
        return scrape_simple_list(url)
    except TypeError:
        ...

    return None


def scrape_sitemap(url) -> pandas.DataFrame:
    """Scrape links form the sitemap.

    Parameters
    ----------
        url : str
            the url to be parse

    Return
    ------
        df : pandas.DataFrame
            a list of links with name and url fields
    """
    # read page
    soup = get_page(url)

    # find links
    sitemap = soup.select('div.sitemap ul.mapTree')
    if len(sitemap) == 0:
        raise TypeError()

    links = sitemap[0].find_all('a')

    # parse links
    pat_text = re.compile(r'[\d\.]+\s*(?P<text>\S+)', re.RegexFlag.MULTILINE | re.RegexFlag.UNICODE)

    parsed_links = []
    for node in links:
        link_url = urllib.parse.urljoin(url, node.attrs['href'])
        match = pat_text.match(node.text)

        if match:
            name = match.group('text')
        else:
            print('ERROR:', node.text.encode('utf-8'))
            continue

        parsed_links.append({
            'name': name,
            'url': link_url,
        })

    df = pandas.DataFrame(parsed_links)
    return df


def scrape_simple_list(url):
    """Scrape links from a simple list.

    Parameters
    ----------
        url : str
            the url of the page to be parse

    Return
    ------
        df : pandas.DataFrame
            a list of links with name and url fields
    """
    soup = get_page(url)

    links = soup.select('div.node ul a')
    if len(links) == 0:
        raise TypeError()

    parsed_links = []
    for link in links:
        link_url = urllib.parse.urljoin(url, link.attrs['href'])
        parsed_links.append({
            'name': link.text,
            'url': link_url,
        })

    df = pandas.DataFrame(parsed_links)
    logging.debug(f'Successfully parse simple list and get {len(df)} items')
    return df


def scrape_list(url):
    """Scrape links from the list.

    Parameters
    ----------
        url : str
            the url of the page to be parse

    Return
    ------
        df : pandas.DataFrame
            a list of links with name and url fields
    """
    soup = get_page(url)
    if len(soup.select('div.list ul')) == 0:
        raise TypeError()

    # hacky way to retrieve all content
    soup = get_page(add_large_pagesize(url))

    page_links = soup.select('div.page ul')
    if len(page_links) == 0:
        raise TypeError()

    page_links = page_links[0]
    assert len(page_links.find_all('a')) == 0

    # find list
    items = soup.select('div.list ul')[0]

    parsed_links = []
    for link in items.find_all('a'):
        link_url = urllib.parse.urljoin(url, link.attrs['href'])
        parsed_links.append({
            'name': link.text,
            'url': link_url,
        })

    df = pandas.DataFrame(parsed_links)
    logging.debug(f'Successfully parse list and get {len(df)} items')
    return df


def scrape_table(url):
    """Scrape links from the table.

    Parameters
    ----------
        url : str
            the url of the page to be parse

    Return
    ------
        df : pandas.DataFrame
            a list of links with name and url fields
    """
    soup = get_page(url)
    if len(soup.select('div.list table')) == 0:
        raise TypeError()

    # ensure only one page fetched
    soup = get_page(add_large_pagesize(url))

    page_links = soup.select('div.page ul')[0]
    assert len(page_links.find_all('a')) == 0

    # find table
    table = soup.select('div.list table')[0]

    # sometimes it has date info
    date_index = None
    for i, th in enumerate(table.select('th')):
        if th.text.strip() == '張貼日':
            date_index = i
            break

    # find breadcrumb
    breadcrumb = soup.select('div.friendly div.path')
    category = None

    if len(breadcrumb) > 0:
        category = re.sub(r'\s', '', breadcrumb[0].text)[5:]  # skip '現在位置'

    # parse links
    parsed_links = []
    for node in table.find_all('tr'):
        link = node.find('a')
        if link is None:
            continue

        link_url = urllib.parse.urljoin(url, link.attrs['href'])

        if date_index is None:
            parsed_links.append({
                'name': link.text,
                'url': link_url,
                'category': category,
            })

        else:
            date = node.find_all('td')[date_index]
            parsed_links.append({
                'name': link.text,
                'url': link_url,
                'date': date.text,
                'category': category,
            })

    df = pandas.DataFrame(parsed_links)
    logging.debug(f'Successfully parse table and get {len(df)} items')
    return df


def scrape_album(url):
    """Scrape links from the album.

    Parameters
    ----------
        url : str
            the url of the page to be parse

    Return
    ------
        df : pandas.DataFrame
            a list of links with name and url fields
    """
    soup = get_page(url)
    if len(soup.select('div.thumbnail div.image')) == 0:
        raise TypeError()

    # ensure only one page fetched
    soup = get_page(add_large_pagesize(url))

    page_links = soup.select('div.page ul')[0]
    assert len(page_links.find_all('a')) == 0

    # find breadcrumb
    breadcrumb = soup.select('div.friendly div.path')
    category = None

    if len(breadcrumb) > 0:
        category = re.sub(r'\s', '', breadcrumb[0].text)[5:]  # skip '現在位置'

    # find table
    table = soup.select('div.thumbnail')[0]

    # parse links
    parsed_links = []
    for node in table.select('div.image'):
        link = node.find_all('a')[-1]
        link_url = urllib.parse.urljoin(url, link.attrs['href'])
        parsed_links.append({
            'name': link.text,
            'url': link_url,
            'category': category,
        })

    df = pandas.DataFrame(parsed_links)
    logging.debug(f'Successfully parse album and get {len(df)} items')
    return df


def scrape_appendix(url):
    """Scrape links from the appendix.

    Parameters
    ----------
        url : str
            the url of the page to be parse

    Return
    ------
        df : pandas.DataFrame
            a list of links with name and url fields
    """
    soup = get_page(url)
    if len(soup.select('div.appendix')) == 0:
        raise TypeError()

    # find category
    breadcrumb = soup.select('div.friendly div.path')
    category = None

    if len(breadcrumb) > 0:
        category = re.sub(r'\s', '', breadcrumb[0].text)[5:]  # skip '現在位置'

    # parse links
    parsed_links = []
    for link in soup.select('div.appendix ul a'):
        link_url = urllib.parse.urljoin(url, link.attrs['href'])
        parsed_links.append({
            'name': link.text,
            'url': link_url,
            'category': category,
        })

    df = pandas.DataFrame(parsed_links)
    logging.debug(f'Successfully parse appendix and get {len(df)} items')
    return df
