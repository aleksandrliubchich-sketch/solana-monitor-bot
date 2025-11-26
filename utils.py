import requests


# Получаем metadata токена
def get_token_metadata(mint):
url = f"https://api.helius.xyz/v0/token-metadata?api-key={HELIUS_API_KEY}"
r = requests.post(url, json={"mintAccounts": [mint]})
data = r.json()


try:
symbol = data[0]["symbol"]
image = data[0]["image"]
except:
symbol = "Unknown"
image = None


axiom_url = f"https://axiom.trade/swap?token={mint}"
return symbol, image, axiom_url


# Получаем последнюю новость Verified X
def get_latest_verified_tweet(TWITTER_BEARER):
headers = {"Authorization": f"Bearer {TWITTER_BEARER}"}
url = "https://api.twitter.com/2/tweets/search/recent"
params = {
"query": "is:verified -is:retweet",
"tweet.fields": "created_at,text,author_id",
"expansions": "author_id",
"max_results": 5
}
r = requests.get(url, headers=headers, params=params)
data = r.json()
if "data" not in data:
return "Twitter API unavailable", "https://x.com"


tweet = data["data"][0]
tweet_id = tweet["id"]
author_id = tweet["author_id"]
text = tweet["text"]
link = f"https://x.com/{author_id}/status/{tweet_id}"
return text, link