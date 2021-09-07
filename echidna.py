#!/usr/bin/python3
from gevent import monkey

monkey.patch_all()

import requests
import argparse
import re
import sys
import math
import time
import simplejson as json
from termcolor import colored
from urllib.parse import urlencode
from threading import Thread


GITHUB_API_URL = "https://api.github.com"
GITHUB_CODE_SEARCH_URL = "https://api.github.com/search/code"
GITHUB_LIMIT_URL = "https://api.github.com/rate_limit"


tokens_list = []
active_tokens = []
throttled_tokens = {}
session = requests.Session()

TOKEN_INDEX = -1

FLIP_SEARCH_DIRECTION = False
LAST_ITEM = ""


def stderr_print(msg, color=None):
    if color is None:
        sys.stderr.write(msg + "\n")
    else:
        sys.stderr.write(colored("[+] ", color) + msg + "\n")


def check_gh_token(token):
    url = GITHUB_API_URL + "/user"
    headers = {"Authorization": "token " + token}
    r = session.get(url, headers=headers)
    resp = r.json()
    if r.status_code == 200:
        stderr_print(
            "Valid token: {}, user: {}, email: {}".format(
                token, resp["login"], resp["email"]
            ),
            "green",
        )
        return True
    else:
        stderr_print("Login Failed, token: {} will be ignored".format(token), "red")
        return False


def check_gh_token_list():
    global tokens_list, active_tokens
    valid_tokens = []
    for token in tokens_list:
        if check_gh_token(token):
            valid_tokens.append(token)
    tokens_list = valid_tokens
    active_tokens = tokens_list.copy()


def token_round_robin():
    global TOKEN_INDEX
    TOKEN_INDEX = TOKEN_INDEX + 1
    if len(active_tokens) == 0:
        return
    if TOKEN_INDEX > len(active_tokens) - 1:
        TOKEN_INDEX = 0
    current_token = active_tokens[TOKEN_INDEX]
    return current_token


def check_limiter(token):
    if token != "no_token":
        headers = {"Authorization": "token " + token}
        r = session.get(GITHUB_LIMIT_URL, headers=headers)
    else:
        r = session.get(GITHUB_LIMIT_URL)
    resp = r.json()
    if resp["rate"]["remaining"] > 0:
        try:
            del throttled_tokens["token"]
        except Exception as e:
            stderr_print("Failed to throttle token: {}".format(e), "red")
            pass
        active_tokens.append(token)
        stderr_print("Token {} is no longger throttled.", "green")
    return


def check_throttled_tokens():
    while True:
        for token in throttled_tokens.keys():
            check_limiter(token)
        time.sleep(10)


def search_api(qstr, page):
    """
    Search github api
    """
    url = (
        GITHUB_CODE_SEARCH_URL
        + "?"
        + urlencode(
            {
                "q": qstr,
                "per_page": 100,
                "page": page,
                "sort": "indexed",
                "order": "asc" if FLIP_SEARCH_DIRECTION else "desc",
            }
        )
    )
    while True:
        token = token_round_robin()
        if token is None:
            stderr_print("All tokens throttled...sleeping...", "red")
            time.sleep(10)
            continue
        headers = {"Authorization": "token " + token}
        try:
            r = session.get(url, headers=headers)
        except Exception as e:
            stderr_print("Error: search_api, {}".format(e), "red")
            return
        if r.status_code == 200:
            return r.json()
        elif r.status_code == 422 and FLIP_SEARCH_DIRECTION:
            return None
        elif r.status_code == 403 and "limit" in r.text:
            throttled_tokens[token] = int(time.timestamp())
            del active_tokens[token]
            stderr_print("Error: Token throttled: {}".format(token), "red")
            continue
        else:
            stderr_print("Unknown Error: {} {}".format(r.status_code, r.text))
            return


def api_code_search(qstr, start_page=1):
    global LAST_ITEM, FLIP_SEARCH_DIRECTION
    resp = search_api(qstr, start_page)
    total = resp["total_count"]
    pages = math.ceil(total / 100)
    stderr_print("Found total: {}, pages: {}".format(total, pages), "green")
    if not args.no_prompt and int(total) > 100:
        confirm = input("Over 100 results, continue? [Y/N]")
        if confirm.lower() != "y":
            exit("Exiting...")
    while start_page <= pages:
        stderr_print("Current page: {}".format(start_page), "cyan")
        for item in resp["items"]:
            if FLIP_SEARCH_DIRECTION and item["url"] == LAST_ITEM:
                stderr_print(
                    "Reversed search order has reached the last item. All done.",
                    "green",
                )
                return
            yield {
                "path": item["path"],
                "url": item["url"],
                "html_url": item["html_url"],
                "owner_login": item["repository"]["owner"]["login"],
                "repo": item["repository"]["name"],
            }
        if total > 1000 and start_page == 10:
            LAST_ITEM = resp["items"][-1]["url"]
            FLIP_SEARCH_DIRECTION = True
            start_page = 0
            stderr_print(
                "Reached 1000th item, reversing search order to cover max 2000 results...",
                "green",
            )
        start_page += 1
        resp = search_api(qstr, start_page)
        if resp is None:
            stderr_print("Search has exhausted. All done.", "green")


# TODO: refactor
def get_code_file(url):
    while True:
        try:
            token = token_round_robin()
            if token:
                headers = {"Authorization": "token " + token}
                r = session.get(url, headers=headers)
            else:
                if "no_token" in throttled_tokens:
                    stderr_print(
                        "All tokens and anonymous login are throttled..sleeping...",
                        "red",
                    )
                    time.sleep(10)
                    continue
                r = session.get(url)
            resp = r.json()
        except Exception as e:
            print(r.status_code, r.text, e.type, e)
            continue
        if r.status_code == 200:
            break
        if r.status_code == 403 and "limit" in resp["message"]:
            stderr_print("Hit rate limiter... Using token: {} ".format(token), "red")
            if token:
                throttled_tokens[token] = int(time.timestamp())
                del active_tokens[token]
            else:
                throttled_tokens["no_token"] = int(time.timestamp())
            continue
    raw_file_url = resp["download_url"]
    try:
        r = session.get(raw_file_url)
        return r.text
    except Exception as e:
        print(r.status_code, r.text, e.type, e)
        return


def match_code_block(code, regex):
    results = {}
    m_list = re.findall(regex, code)
    re_code_block = ".*" + regex + ".*"
    if len(m_list) > 0:
        bm_list = re.findall(re_code_block, code, re.MULTILINE)
        results["exact_match"] = list(set(m_list))
        if len(bm_list) > 0:
            results["code_block"] = list(set(bm_list))
        return results
    return


def start_search():
    if args.output_file:
        f = open(args.output_file, "a")
    for item in api_code_search(args.query, args.start_page):
        code = get_code_file(item["url"])
        if code is None:
            continue
        results = match_code_block(code, args.pattern)
        if results:
            stderr_print("Code block found in: {}".format(item["html_url"]), "blue")
            stderr_print("Matches: {}".format(results["exact_match"]), "blue")
            stderr_print("Matched block: {}".format(results["code_block"]), "blue")
            item.update(results)
            if args.json:
                print(json.dumps(item))
            if args.output_file:
                f.write(json.dumps(item) + "\n")
        elif not args.matched_only:
            stderr_print("No match from: {}".format(item["html_url"]), "yellow")
            pass


if __name__ == "__main__":
    helper_text = """
Echidna is a highly effective Github API scraper. 
It utilizes multiple GitHub tokens in round-robin to avoid getting caught by the rate limiter.
Echidna automatically pauses and resumes the job when all tokens are throttled. It also bypasses
GitHub API query results limit (1000 items) by using date sorted query and starts from the end
once first 1000 results are returned. Therefore the maximum number of obaintable results is 2000.
For anything larger than that, please shard the query using filters at 
https://docs.github.com/en/github/searching-for-information-on-github/getting-started-with-searching-on-github/understanding-the-search-syntax 
For example: query one language first with "KEYWORD language:python" 
then move to Javascript, PHP etc...Or remove non-code extensions with:
-extension:html -extension:md -extension:txt ...etc. There are multiple ways to get the results
down below 2000 and make this tool more effective.

There's no multithreading support in order to avoid the secondary rate limiter (IP and Repo based).
If you need multithreading then your query is wrong!

Getting throttled? Hint: find more Github Tokens with -q 'ghp_' -p '[A-Za-z0-9]{36,}'
    """
    parser = argparse.ArgumentParser(epilog=helper_text,formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-q", "--query", help="query (required or -q)", required=True)
    parser.add_argument(
        "-t",
        "--token",
        help="your github token (required if token file not specififed)",
    )
    parser.add_argument(
        "-tf", "--tokenfile", help="file containing new line separated github tokens"
    )
    parser.add_argument(
        "-p",
        "--pattern",
        help="Regexp pattern to further filter results. WARNING: DO NOT USE CAPTURE GROUP such as (...)",
        required=True,
    )
    parser.add_argument("-o", "--output_file", help="output results to file name.")
    parser.add_argument(
        "--no_prompt",
        help="Disable start confirmation for large results.",
        action="store_true",
    )

    parser.add_argument(
        "--reverse_order",
        help="Start search in reverse direct (Asc instead of Desc). Only the last 1000 results will be used.",
        action="store_true",
    )
    parser.add_argument(
        "--matched_only",
        help="Show matched results only",
        action="store_true",
    )
    parser.add_argument(
        "--start_page",
        help="Start from page number. Useful to continue broken search",
        type=int,
        default=1,
    )
    parser.add_argument("--json", help="JSON output to STDOUT", action="store_true")
    args = parser.parse_args()

    # TOKEN ARGUMENT LOGIC
    if args.token:
        tokens_list = args.token.split(",")
    if args.tokenfile:
        with open(args.tokenfile) as f:
            tokens_list = [i.strip() for i in f.read().splitlines() if i.strip()]
    if args.token is None and args.tokenfile is None:
        exit("Please specifiy at least one GitHub Token using -t or -tf")
    if args.reverse_order:
        FLIP_SEARCH_DIRECTION = True
        stderr_print("Reversing search order, starting from the end...")
    check_gh_token_list()
    requests_per_minute = (len(tokens_list) * 30) - 1
    th = Thread(target=check_throttled_tokens)
    th.daemon = True
    th.start()
    stderr_print("Token refresher background task started", "green")
    start_search()
