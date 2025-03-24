import os
from flask import Flask, request, abort

from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = Flask(__name__)

# 環境変数から取得するようにすると安全
CHANNEL_ACCESS_TOKEN = os.environ.get("CHANNEL_ACCESS_TOKEN", "")
CHANNEL_SECRET = os.environ.get("CHANNEL_SECRET", "")

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

@app.route("/", methods=["GET"])
def index():
    return "Hello, this is a sample LINE Bot on Render."

@app.route("/callback", methods=["POST"])
def callback():
    # リクエストヘッダから署名検証のための値を取得
    signature = request.headers["X-Line-Signature"]

    # リクエストボディを取得
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"

# メッセージ受信時のハンドラ
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    # 受け取ったメッセージをそのままオウム返し
    incoming_text = event.message.text
    reply_text = f"あなたが送ったのは: {incoming_text}"
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

if __name__ == "__main__":
    # Render ではポートが自動割り当てされるので、環境変数PORTを使う方がよい
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
