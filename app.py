# app.py
import os
import time
import threading
import logging
from collections import defaultdict
from flask import Flask, request, jsonify
import requests

from utils import get_token_metadata, get_latest_verified_tweet

# Logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("solana-monitor-bot")

# Config from env
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")         # from BotFather
CHAT_ID = os.getenv("CHAT_ID")                       # numeric or @channel
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY")         # Helius key
TWITTER_BEARER = os.getenv("TWITTER_BEARER")         # X/Twitter bearer token

# Constants
SOL_MINT = "So11111111111111111111111111111111111111112"
WINDOW = 60          # seconds: collect events by token for this window
COOLDOWN = 300       # seconds: per-token cooldown (5 minutes)
SWEEPER_INTERVAL = 15  # seconds: how often background sweeper runs

app = Flask(__name__)

# In-memory stores (simple, not persistent)
token_events = defaultdict(list)   # mint -> list of events
last_notify = defaultdict(lambda: 0)  # mint -> last notify timestamp
lock = threading.Lock()


def send_telegram_photo(photo_url, caption):
    """
    Send a photo message (photo URL accepted) with caption to Telegram.
    """
    if not TELEGRAM_TOKEN or not CHAT_ID:
        log.warning("Telegram token or chat id not configured; skipping send.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    data = {
        "chat_id": CHAT_ID,
        "photo": photo_url if photo_url else "",
        "caption": caption,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    try:
        r = requests.post(url, data=data, timeout=10)
        if r.status_code != 200:
            log.warning("Telegram sendPhoto returned %s: %s", r.status_code, r.text)
            return False
        return True
    except Exception as e:
        log.exception("Failed to send telegram photo: %s", e)
        return False


def send_telegram_text(text):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        log.warning("Telegram token or chat id not configured; skipping send.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    try:
        r = requests.post(url, data=data, timeout=10)
        if r.status_code != 200:
            log.warning("Telegram sendMessage returned %s: %s", r.status_code, r.text)
            return False
        return True
    except Exception as e:
        log.exception("Failed to send telegram message: %s", e)
        return False


def format_event_summary(symbol, events):
    """
    Build a Markdown message summarizing events for a token.
    events: list of event tuples:
      (ts, buyer, sol, to_amount, signature, image_url, axiom_url, tweet_text, tweet_link, mint)
    """
    total_sol = sum(e[2] for e in events)
    buyers_count = len(events)
    mint = events[0][9]
    image = events[0][5]
    header = f"🔥 *{symbol}* — {buyers_count} buys aggregated • {total_sol:.4f} SOL total\n\n"
    items = ""
    for ts, buyer, sol, to_amount, signature, image_url, axiom_url, tweet_text, tweet_link, mint in events:
        solscan = f"https://solscan.io/tx/{signature}" if signature else "N/A"
        items += (
            f"💰 {sol:.4f} SOL — `{buyer}`\n"
            f"📦 {to_amount}\n"
            f"🔗 [Solscan]({solscan}) | [Buy on Axiom]({axiom_url})\n\n"
        )
    # tweet summary (use first event's tweet)
    tweet_section = ""
    if events[0][7]:
        tweet_section = f"🐦 *Latest Verified tweet:*\n{events[0][7]}\n🔗 {events[0][8]}\n\n"
    footer = f"🪪 Mint: `{mint}`"
    caption = header + items + tweet_section + footer
    return caption, image


def try_send_for_token(mint):
    """
    Try to send a summary for a given mint if conditions are met.
    """
    with lock:
        events = token_events.get(mint, [])
        if not events:
            return

        now = time.time()
        # remove old events older than WINDOW
        events = [e for e in events if now - e[0] <= WINDOW]
        token_events[mint] = events  # update

        if not events:
            return

        # if we have recent notification less than COOLDOWN -> skip
        if now - last_notify[mint] < COOLDOWN:
            log.info("Skipping notify for %s: cooldown active", mint)
            return

        # if earliest event older than WINDOW/ or immediate send allowed
        first_ts = events[0][0]
        if now - first_ts < WINDOW:
            # not enough time to aggregate yet; wait for sweeper
            log.debug("Waiting to aggregate events for %s (%.1fs left)", mint, WINDOW - (now - first_ts))
            return

        # get symbol and tweet for inclusion already stored in events
        symbol = events[0][10] if len(events[0]) > 10 else "UNKNOWN"
        caption, image = format_event_summary(symbol, events)
        sent = False
        if image:
            sent = send_telegram_photo(image, caption)
        if not sent:
            send_telegram_text(caption)

        last_notify[mint] = now
        token_events[mint] = []  # reset buffer
        log.info("Sent summary for %s (events: %d)", mint, len(events))


def sweeper_loop():
    """
    Background thread: every SWEEPER_INTERVAL seconds checks tokens and sends summaries.
    """
    log.info("Sweeper thread started, window=%s sec, cooldown=%s sec", WINDOW, COOLDOWN)
    while True:
        try:
            with lock:
                mints = list(token_events.keys())
            for mint in mints:
                try_send_for_token(mint)
        except Exception:
            log.exception("Error in sweeper loop")
        time.sleep(SWEEPER_INTERVAL)


@app.route("/solana", methods=["POST"])
def solana_webhook():
    """
    Endpoint to receive Helius Enhanced Transactions webhook.
    Expects JSON; looks for events.swap with structure produced by Helius.
    """
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"status": "bad request"}), 400

    # signature
    signature = payload.get("signature") or payload.get("txHash") or None

    # Helius enhanced -> events.swap
    events_block = payload.get("events", {})
    swap = events_block.get("swap")
    if not swap:
        # ignore non-swap events
        return jsonify({"status": "ignored"}), 200

    buyer = swap.get("user") or swap.get("signer") or payload.get("meta", {}).get("signer") or "unknown"
    from_mint = swap.get("fromMint")
    to_mint = swap.get("toMint")
    from_amount = swap.get("fromAmount") or swap.get("amountIn") or 0
    to_amount = swap.get("toAmount") or swap.get("amountOut") or 0

    # filter: only swaps where input mint is SOL and amount >= 5
    try:
        from_amount = float(from_amount)
    except Exception:
        from_amount = 0.0

    if from_mint != SOL_MINT or from_amount < 5:
        return jsonify({"status": "ignored"}), 200

    # fetch token metadata (symbol, image) using Helius
    symbol, image_url, axiom_url = get_token_metadata(to_mint, HELIUS_API_KEY)

    # fetch latest verified tweet
    tweet_text, tweet_link = get_latest_verified_tweet(TWITTER_BEARER)

    event = (
        time.time(),         # 0 timestamp
        buyer,               # 1 buyer
        from_amount,         # 2 sol used
        to_amount,           # 3 token amount
        signature,           # 4 signature
        image_url,           # 5 image url
        axiom_url,           # 6 axiom buy url
        tweet_text,          # 7 tweet text
        tweet_link,          # 8 tweet link
        to_mint,             # 9 mint
        symbol               # 10 symbol
    )

    with lock:
        token_events[to_mint].append(event)
        # ensure events sorted by time just in case
        token_events[to_mint].sort(key=lambda e: e[0])

    log.info("Recorded event %s: %s %s SOL -> %s", signature, symbol, from_amount, to_mint)
    # Immediately try to send if cooldown passed and window already elapsed
    try_send_for_token(to_mint)

    return jsonify({"status": "ok"}), 200


@app.route("/", methods=["GET"])
def index():
    return "Solana Monitor Bot is running."


def start_background_sweeper():
    t = threading.Thread(target=sweeper_loop, daemon=True)
    t.start()


# Start sweeper when app starts (works with Railway, Flask 3.x)
@app.before_serving
def startup():
    print("App started!")
    start_background_sweeper()


if __name__ == "__main__":
    # Local run
    start_background_sweeper()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))





