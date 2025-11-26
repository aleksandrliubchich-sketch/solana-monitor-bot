import requests
import logging

log = logging.getLogger("utils")


def get_token_metadata(mint, helius_api_key):
    """
    Fetch token metadata from Helius.
    Always returns (symbol, image_url, axiom_url), never crashes.
    """
    if not mint or not helius_api_key:
        return "UNKNOWN", None, f"https://axiom.trade/swap?token={mint}"

    try:
        url = f"https://api.helius.xyz/v0/token-metadata?api-key={helius_api_key}"
        payload = {"mintAccounts": [mint]}
        resp = requests.post(url, json=payload, timeout=10)

        if resp.status_code != 200:
            log.warning("Helius metadata error %s: %s", resp.status_code, resp.text)
            return "UNKNOWN", None, f"https://axiom.trade/swap?token={mint}"

        data = resp.json()

        if not isinstance(data, list) or not data:
            return "UNKNOWN", None, f"https://axiom.trade/swap?token={mint}"

        info = data[0]
        symbol = info.get("symbol") or info.get("name") or "UNKNOWN"
        image_url = info.get("image")
        axiom_url = f"https://axiom.trade/swap?token={mint}"

        return symbol, image_url, axiom_url

    except Exception as e:
        log.exception("Failed to fetch token metadata: %s", e)
        return "UNKNOWN", None, f"https://axiom.trade/swap?token={mint}"


def get_latest_verified_tweet(bearer_token):
    """
    Fetch latest tweet from verified accounts.
    Always returns (text, link) or (None, None) if unavailable.
    """
    if not bearer_token:
        return None, None

    try:
        url = "https://api.twitter.com/2/tweets/search/recent"
        headers = {"Authorization": f"Bearer {bearer_token}"}
        params = {
            "query": "is:verified -is:retweet lang:en",
            "tweet.fields": "created_at,text,author_id",
            "expansions": "author_id",
            "user.fields": "username",
            "max_results": 5
        }

        r = requests.get(url, headers=headers, params=params, timeout=10)

        if r.status_code != 200:
            log.warning("Twitter API error %s: %s", r.status_code, r.text)
            return None, None

        data = r.json()

        if "data" not in data or not data["data"]:
            return None, None

        tweet = data["data"][0]
        tweet_id = tweet.get("id")
        text = tweet.get("text", "")

        # username extraction
        username = None
        users = data.get("includes", {}).get("users", [])
        if users:
            username = users[0].get("username")

        if username:
            link = f"https://x.com/{username}/status/{tweet_id}"
        else:
            link = f"https://x.com/i/web/status/{tweet_id}"

        return text, link

    except Exception as e:
        log.exception("Failed to fetch latest verified tweet: %s", e)
        return None, None

