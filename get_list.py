import argparse
import logging

import tqdm
import pandas

import scraper

DOMAIN = 'cga.gov.tw'
SKIP_EXT = ['.pdf', '.doc', '.docx', '.odt', '.xls', '.xlsx', '.ods']


def main():
    # parse args
    parser = argparse.ArgumentParser()

    parser.add_argument(
        '--url', default='https://www.cga.gov.tw/GipOpen/wSite/sitemap?mp=9997', help='URL to the sitemap')
    parser.add_argument('--verbose', '-v', action='store_true', help='Set logging level to verbose')
    parser.add_argument('--output', '-o', default='site.csv', help='File to save all the sites')
    parser.add_argument('--logfile', '-l', help='File to store verbose log')

    args = parser.parse_args()

    # verbose
    if args.verbose:
        set_logger(logging.DEBUG, args.logfile)
    else:
        set_logger(logging.INFO, args.logfile)

    # load sitemap
    logging.info('Loading sitemap')

    new_pages = scraper.scrape_sitemap(args.url)

    # iterate through pages
    finished_pages = []
    failed_pages = []

    n_tier = 0
    while len(new_pages) > 0:
        # drop external domain
        new_pages = new_pages[new_pages['url'].map(lambda u: DOMAIN in u)]

        # redirect
        new_pages['url'] = new_pages['url'].map(scraper.redirect)

        # duplicated pages
        new_pages = new_pages.drop_duplicates('url')

        finished_urls = [item['url'] for item in finished_pages]
        new_pages = new_pages[~new_pages['url'].isin(finished_urls)]

        # failed-to-parsed pages
        failed_urls = [url for _, url in failed_pages]
        new_pages = new_pages[~new_pages['url'].isin(failed_urls)]

        # files
        new_pages = new_pages[new_pages['url'].map(lambda u: not any(u.endswith(ext) for ext in SKIP_EXT))]

        # swap
        current_targets = new_pages.reset_index(drop=True)
        new_pages = []

        # log
        n_tier += 1
        logging.info(f'Start tier {n_tier}; {len(current_targets)} pages')
        for idx, row in current_targets.iterrows():
            logging.debug(f'[{idx}] {row["name"]}\t{row["url"]}')

        # iterate
        for _, row in tqdm.tqdm(
                current_targets.iterrows(),
                desc=f'tier {n_tier}',
                total=len(current_targets),
                ascii=True,
        ):
            url = row['url']

            page_info = scraper.get_page_info(**row)
            finished_pages.append(page_info)

            if page_info['is_leaf']:
                continue

            df = scraper.try_scrape(url)
            if df is not None:
                new_pages.append(df)
                continue

            logging.critical(f'NOT ABLE TO PARSE: {page_info["name"]}; URL: {url}')
            failed_pages.append((page_info["name"], url))

        if new_pages:
            new_pages = pandas.concat(new_pages, sort=False)

    # save
    finished_pages = pandas.DataFrame(finished_pages, columns=['name', 'date', 'category', 'url'])
    finished_pages.to_csv(args.output)

    logging.info(f'Data saved to {args.output}')

    # output
    if failed_pages:
        logging.warning('Pages that are failed to be parsed:')
        for title, url in failed_pages:
            logging.warning(f'{title}\t{url}')

    logging.info('Program finished.')


def set_logger(level=logging.INFO, logfile=None):
    # get dependency
    try:
        import colorlog
    except ImportError:
        colorlog = None

    # set file output
    if logfile:
        logging.basicConfig(filename=logfile, level=logging.DEBUG)

    # set logger
    logging.captureWarnings(True)
    logger = logging.getLogger('')

    if not logfile:
        logger.setLevel(logging.DEBUG)

    # set format
    if colorlog:
        console = colorlog.StreamHandler()
        formatter = colorlog.ColoredFormatter('%(log_color)s[%(asctime)s][%(levelname)s] %(message)s')
    else:
        console = logging.StreamHandler()
        formatter = logging.Formatter('[%(asctime)s][%(levelname)s] %(message)s')

    # set handler
    console.setLevel(level)
    console.setFormatter(formatter)
    logger.addHandler(console)


if __name__ == '__main__':
    main()
