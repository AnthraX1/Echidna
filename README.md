# Echidna
Echidna is a highly effective GIthub API scraper used to find interesting stuff on Github...

## Description

Echidna is a highly effective Github API scraper. 
It utilizes multiple GitHub tokens in round-robin to avoid getting caught by the rate limiter.
Echidna automatically pauses and resumes the job when all tokens are throttled. 
It also bypasses GitHub API query results limit (1000 items) by using date sorted query and starts from the end
once first 1000 results are returned. Therefore the maximum number of obaintable results is 2000.
For anything larger than that, please shard the query using filters at 
https://docs.github.com/en/github/searching-for-information-on-github/getting-started-with-searching-on-github/understanding-the-search-syntax 
For example: query one language first with "KEYWORD language:python"  then move to Javascript, PHP etc...
Or remove non-code extensions with: -extension:html -extension:md -extension:txt ...etc. There are multiple ways to get the results down below 2000 and make this tool more effective.

There's no multithreading support in order to avoid the secondary rate limiter (IP and Repo based).
If you need multithreading then your query is wrong!

Getting throttled? Hint: find more Github Tokens with -q 'ghp_' -p '[A-Za-z0-9]{36,}'  ( **͡° ͜ʖ ͡°**)


## Usage

api_hunter.py [-h] -q QUERY [-t TOKEN] [-tf TOKENFILE] -p PATTERN [-o OUTPUT_FILE] [--no_prompt] [--reverse_order][--matched_only] [--start_page START_PAGE] [--json]


optional arguments:
  -h, --help            show this help message and exit
  -q QUERY, --query QUERY
                        query (required or -q)
  -t TOKEN, --token TOKEN
                        your github token (required if token file not specififed)
  -tf TOKENFILE, --tokenfile TOKENFILE
                        file containing new line separated github tokens
  -p PATTERN, --pattern PATTERN
                        Regexp pattern to further filter results. WARNING: DO NOT USE CAPTURE GROUP such as (...)
  -o OUTPUT_FILE, --output_file OUTPUT_FILE
                        output results to file name.
  --no_prompt           Disable start confirmation for large results.
  --reverse_order       Start search in reverse direct (Asc instead of Desc). Only the last 1000 results will be used.
  --matched_only        Show matched results only
  --start_page START_PAGE
                        Start from page number. Useful to continue broken search
  --json                JSON output to STDOUT

