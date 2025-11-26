# utils.py
import requests
import logging

log = logging.getLogger("utils")

def get_token_metadata(mint, helius_api_key):
    """
    Query Helius token-metadata endpoint for a single mint.
    Returns (symbol, image_url, axiom_url)
    """
    if not mint:
        return "UNKNOWN", None, f"https://axiom.trade"
    try:
        url = f"https://api.helius.xyz/v0/token-metadata?api-key={helius_api_key}"
        resp = requests.post(url, json={"mintAccounts": [mint]}, timeout=10)
        data = resp.json()
        if isinstance(data, list) and data:
            info = data[0]
            symbol = info.get("symbol") or info.get("name") or "UNKNOWN"
            image = info.get("image")
            axiom = f"https://axiom.trade/swap?token={mint}"
            return symbol, image, axiom
        else:
            return "UNKNOWN", None, f"https://axiom.trade/swap?token={mint}"
    except Exception as e:
        log.exception("Failed to fetch token metadata: %s", e)
        return "UNKNOWN", None, f"https://axiom.trade/swap?token={mint}"


def get_latest_verified_tweet(bearer_token):
    """
    Use X/Twitter recent search endpoint to get the latest tweet from verified accounts.
    Returns (tweet_text, tweet_link). On error returns (None, None).
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
        data = r.json()
        if "data" not in data:
            return None, None
        tweet = data["data"][0]
        tweet_id = tweet.get("id")
        text = tweet.get("text")
        # find username in includes (if available)
        username = None
        includes = data.get("includes", {})
        users = includes.get("users", []) if includes else []
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
