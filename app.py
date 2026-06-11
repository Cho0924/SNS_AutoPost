import os
import json
import threading
from flask import Flask, request, jsonify
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from dotenv import load_dotenv
import google.genai as genai

load_dotenv()

app = Flask(__name__)

# SlackとAIの初期化
slack_token = os.getenv("SLACK_BOT_TOKEN")
client = WebClient(token=slack_token)

gemini_api_key = os.getenv("GEMINI_API_KEY")
genai_client = None
if gemini_api_key:
    genai_client = genai.Client(api_key=gemini_api_key)

# ---------------------------------------------------------
# 1. スタンプ（リアクション）のイベントを受け取るエンドポイント
# ---------------------------------------------------------
@app.route('/slack/events', methods=['POST'])
def slack_events():
    data = request.json
    
    # Slackからの初期認証テスト（URL Verification）への応答
    if "challenge" in data:
        return jsonify({"challenge": data["challenge"]})
        
    if "event" in data:
        event = data["event"]
        
        # 誰かがスタンプ（リアクション）を押した時
        if event.get("type") == "reaction_added":
            channel_id = event["item"]["channel"]
            message_ts = event["item"]["ts"]
            
            # 元のメッセージのテキストを取得する
            try:
                result = client.conversations_history(
                    channel=channel_id,
                    latest=message_ts,
                    limit=1,
                    inclusive=True
                )
                messages = result.get("messages", [])
                if not messages:
                    return jsonify({"status": "ok"}), 200
                    
                original_text = messages[0].get("text", "")
                
                # 承認ボタンをスレッドに送信
                client.chat_postMessage(
                    channel=channel_id,
                    thread_ts=message_ts,  # スタンプが押された投稿のスレッドに返信
                    text="SNS投稿ドラフト作成の確認",
                    blocks=[
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": "🤖 この投稿からSNS投稿のドラフトを作成しますか？"
                            }
                        },
                        {
                            "type": "actions",
                            "elements": [
                                {
                                    "type": "button",
                                    "text": {"type": "plain_text", "text": "ドラフトを作成する", "emoji": True},
                                    "style": "primary",
                                    "value": original_text, # 元のテキストデータをボタンの裏側に隠し持つ
                                    "action_id": "approve_draft_creation"
                                }
                            ]
                        }
                    ]
                )
            except SlackApiError as e:
                print(f"Slack API エラー: {e}")
                
    return jsonify({"status": "ok"}), 200

# ---------------------------------------------------------
# 2. ボタンが押された時のエンドポイント
# ---------------------------------------------------------
@app.route('/slack/interactive', methods=['POST'])
def slack_interactive():
    if 'payload' in request.form:
        payload = json.loads(request.form['payload'])
        
        if payload.get("type") == "block_actions":
            action = payload["actions"][0]
            
            # 「ドラフトを作成する」ボタンが押された時
            if action.get("action_id") == "approve_draft_creation":
                original_text = action.get("value", "")
                channel_id = payload["channel"]["id"]
                thread_ts = payload["message"]["thread_ts"]
                
                # AIの処理は数秒かかるため、先に「処理中」を通知する（Slackのタイムアウト回避）
                client.chat_postMessage(channel=channel_id, thread_ts=thread_ts, text="⏳ AIがドラフトを作成しています...")
                
                # 裏側（別スレッド）でAIにドラフトを作らせる
                threading.Thread(
                    target=process_ai_draft, 
                    args=(channel_id, thread_ts, original_text)
                ).start()
                
        # Slackにはすぐに200 OKを返す
        return jsonify({"status": "ok"}), 200
    return jsonify({"error": "No payload"}), 400

# ---------------------------------------------------------
# 3. AIにドラフトを生成させる関数
# ---------------------------------------------------------
def process_ai_draft(channel_id, thread_ts, original_text):
    prompt = f"""
以下の社内Slackの投稿テキストから、SNSへの投稿ドラフトを作成してください。
投稿のフォーマットは、内容を判断して以下の4つのルールのいずれかから適切なものを選択してください。
プレースホルダー（[]で囲まれた部分）は元のテキストから推測して埋めてください。

【フォーマットのルール】
1. Type A：Podcastの場合（「Podcast」などの単語やSpotifyのURLがある場合）
✨📚Podcast 新エピソード公開📚✨
Podcast「Tech Startupの舞台裏」でお届けする[テーマ・内容の説明]。[ゲストや内容の紹介1文] 🎙️

2. Type B：投資先ニュースの場合（投資先企業のニュース・調達・提携など）
🚩投資先News🚩
[会社名] @[xハンドル] が、[ニュース内容の具体的説明] [元記事URL]

3. Type C-1：UTECニュース（メディア掲載等）
🚩UTEC News🚩
[内容説明。@メンションがあれば含める] [適切な絵文字] [URL]

4. Type C-2：UTEC自社大型発表（ファンド組成など）
📢[発表タイトル一言]📢
[発表内容の説明。具体的な名称・数字を含める] [URL]

【元のテキスト】
{original_text}
"""
    try:
        if not gemini_api_key:
            draft_text = "⚠️ GeminiのAPIキーが設定されていません。"
        else:
            response = genai_client.models.generate_content(
                model="gemini-2.5-flash-lite",
                contents=prompt,
            )
            draft_text = response.text
            
        # 完成したドラフトをSlackに送信する
        client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text="ドラフトが完成しました",
            blocks=[
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"🤖 ドラフトが完成しました！\n\n```\n{draft_text}\n```"}
                }
            ]
        )
    except Exception as e:
        client.chat_postMessage(channel=channel_id, thread_ts=thread_ts, text=f"⚠️ ドラフト作成中にエラーが発生しました: {e}")

if __name__ == '__main__':
    app.run(port=3000, debug=True)