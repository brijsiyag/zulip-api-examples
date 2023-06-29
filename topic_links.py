import re
import zulip
from urllib import parse

DEVELOPMENT = False

global client
global host
import logging
import datetime

logging.basicConfig(
    filename=f"{datetime.datetime.now().strftime('%d-%m-%Y-%H:%M')}.log",
    format="%(asctime)s %(message)s",
    filemode="w",
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

if DEVELOPMENT:
    logger.info("In development env...")
    client = zulip.Client(config_file="./zuliprc")
    BOT_REGEX = r"(.*)-bot@(zulipdev.com|zulip.com)$"
else:
    BOT_REGEX = r"(.*)-bot@(chat.zulip.org|zulip.com)$"
    client = zulip.Client(config_file="/home/ubuntu/zuliprc")

stream_list = []


def update_streams_list():
    stream_list.clear()
    response = client.get_subscriptions()
    streams = response["subscriptions"]
    for stream in streams:
        stream_list.append(stream["name"])
    logger.info(stream_list)


hash_replacements = {
    ".": ".2E",
    "%": ".",
    "(": ".28",
    ")": ".29",
}


def encode_hash_component(id):
    encoded_id = parse.quote(id, safe="")
    for k, v in hash_replacements.items():
        encoded_id = encoded_id.replace(k, v)
    return encoded_id


parsed_url = parse.urlparse(client.base_url)
host = parsed_url.scheme + "://" + parsed_url.netloc
logger.info(host)


def get_near_link(msg_id, stream_id, stream_name, topic):
    stream_name = stream_name.replace(" ", "-")
    msg_id = encode_hash_component(str(msg_id))
    stream_slug = encode_hash_component(f"{stream_id}-{stream_name}")
    topic_slug = encode_hash_component(topic)
    return host + f"/#narrow/stream/{stream_slug}/topic/{topic_slug}/near/{msg_id}"


def send(content, topic, stream):
    # https://zulip.com/api/send-message
    request = {
        "type": "stream",
        "to": stream,
        "topic": topic,
        "content": content,
    }
    client.send_message(request)
    logger.info(f"sent->{content}")


def handle_message(msg):
    if msg["type"] != "stream":
        return
    if re.match(BOT_REGEX, msg["sender_email"]):
        return

    TOPIC_LINK_RE = r"(\#\*\*(.*?)>(.*?)\*\*)"

    content = msg["content"]

    stream = msg["display_recipient"]
    stream_id = msg["stream_id"]
    topic = msg["subject"]

    if stream not in stream_list:
        return

    from_topic_link = f"#**{stream}>{topic}**"
    user_id = msg["sender_id"]
    user_name = msg["sender_full_name"]

    sender = f"@_**{user_name}|{user_id}**"

    msg_id = msg["id"]

    near_link = get_near_link(msg_id, stream_id, stream, topic)
    for tagged_topic_link, tagged_stream, tagged_topic in re.findall(
        TOPIC_LINK_RE, content
    ):
        if tagged_topic_link == from_topic_link or tagged_stream not in stream_list:
            continue
        msg = (
            f"{sender} mentioned this topic in **[#{stream} > {topic}]({near_link})**."
        )
        send(msg, tagged_topic, tagged_stream)


def handle_reaction(reaction):
    emoji_name = reaction["emoji_name"]
    message_id = reaction["message_id"]
    op = reaction["op"]
    user_email = reaction["user"]["email"]
    message = client.get_raw_message(message_id)

    if message.get("message")["sender_email"] != client.email:
        return
    if op != "add" or emoji_name != "-1":
        return

    response = client.delete_message(message_id)
    if response["result"] == "error":
        logger.info(
            f"Unable to delete the message {message_id} by attempted by {user_email}"
        )
    else:
        logger.warning(f"{user_email} deleted message {message_id} by reacting.")


def watch_messages():
    def handle_event(event):
        event_type = event["type"]
        if event_type == "message":
            handle_message(event["message"])
        elif event_type == "reaction":
            handle_reaction(event)
        elif event_type == "subscription":
            update_streams_list()

    update_streams_list()
    # https://zulip.com/api/real-time-events
    client.call_on_each_event(handle_event)


watch_messages()
