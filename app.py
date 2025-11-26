from flask import Flask, request
def send_message(text, image=None):
data = {"chat_id": CHAT_ID, "caption": text, "parse_mode": "Markdown"}
if image:
response = requests.get(image)
files = {"photo": response.content}
requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto", data=data, files=files)
else:
requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"})


def try_send_summary(symbol):
now = time.time()
if now - last_notify[symbol] < COOLDOWN:
return


events = [e for e in token_events[symbol] if now - e[0] <= WINDOW]
if not events:
return


text = f"🔥 *Сводка покупок токена {symbol} за последнюю минуту:*
\n"
for _, buyer, sol, solscan, image, axiom_url, tweet_text, tweet_link in events:
text += (
f"💰 {sol} SOL\n"
f"👛 `{buyer}`\n"
f"🔗 [Solscan]({solscan}) | [Axiom.trade]({axiom_url})\n"
f"🐦 {tweet_text}\n"
f"🔗 {tweet_link}\n\n"
)


image = events[0][4]
send_message(text, image)
last_notify[symbol] = now
token_events[symbol] = []


@app.route("/solana", methods=["POST"])
def solana_webhook():
data = request.json
swap = data.get("events", {}).get("swap")
if not swap:
return {"status": "ignored"}


buyer = swap["user"]
from_amount = swap["fromAmount"]
from_mint = swap["fromMint"]
to_mint = swap["toMint"]
sig = data.get("signature")


if from_mint == SOL_MINT and from_amount >= 5:
symbol, image, axiom_url = get_token_metadata(to_mint)
solscan = f"https://solscan.io/tx/{sig}"
tweet_text, tweet_link = get_latest_verified_tweet(TWITTER_BEARER)


token_events[symbol].append((
time.time(), buyer, from_amount, solscan, image, axiom_url, tweet_text, tweet_link
))


try_send_summary(symbol)


return {"status": "ok"}


if __name__ == "__main__":
app.run(port=5000)