import os
import json
import threading
from flask import Flask, request, jsonify
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from dotenv import load_dotenv
from google import genai

# SNS投稿用の関数をインポート
from post_test_message import post_to_x, post_to_facebook, post_to_linkedin

load_dotenv()

app = Flask(__name__)

# SlackとAIの初期化
slack_token = os.getenv("SLACK_BOT_TOKEN")
client = WebClient(token=slack_token)

gemini_api_key = os.getenv("GEMINI_API_KEY")
gemini_client = genai.Client(api_key=gemini_api_key) if gemini_api_key else None
gemini_model = "gemini-3.1-flash-lite"

# ---------------------------------------------------------
# 1. スタンプのイベントを受け取るエンドポイント
# ---------------------------------------------------------
@app.route('/slack/events', methods=['POST'])
def slack_events():
    data = request.json
    if "challenge" in data:
        return jsonify({"challenge": data["challenge"]})
        
    if "event" in data:
        event = data["event"]
        if event.get("type") == "reaction_added":
            channel_id = event["item"]["channel"]
            message_ts = event["item"]["ts"]
            
            try:
                result = client.conversations_history(
                    channel=channel_id, latest=message_ts, limit=1, inclusive=True
                )
                messages = result.get("messages", [])
                if not messages:
                    return jsonify({"status": "ok"}), 200
                    
                original_text = messages[0].get("text", "")
                
                client.chat_postMessage(
                    channel=channel_id,
                    thread_ts=message_ts,
                    text="SNS投稿ドラフト作成の確認",
                    blocks=[
                        {
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": "🤖 この投稿からSNS投稿のドラフトを作成しますか？"}
                        },
                        {
                            "type": "actions",
                            "elements": [
                                {
                                    "type": "button",
                                    "text": {"type": "plain_text", "text": "ドラフトを作成する", "emoji": True},
                                    "style": "primary",
                                    "value": original_text,
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
# 2. ボタンやModalからの送信を受け取るエンドポイント
# ---------------------------------------------------------
@app.route('/slack/interactive', methods=['POST'])
def slack_interactive():
    if 'payload' in request.form:
        payload = json.loads(request.form['payload'])
        
        # --- A. ボタンが押された時の処理 ---
        if payload.get("type") == "block_actions":
            action = payload["actions"][0]
            action_id = action.get("action_id")
            channel_id = payload["channel"]["id"]
            message_ts = payload["message"]["ts"]
            thread_ts = payload["message"].get("thread_ts", message_ts)
            
            # 「ドラフトを作成する」が押された時
            if action_id == "approve_draft_creation":
                original_text = action.get("value", "")
                client.chat_update(channel=channel_id, ts=message_ts, text="AIがドラフト作成中...", blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": "⏳ AIがドラフトを作成しています..."}}])
                threading.Thread(target=process_ai_draft, args=(channel_id, thread_ts, original_text)).start()
                
            # 「このまま投稿」が押された時
            elif action_id == "post_approve":
                draft_text = action.get("value", "")
                client.chat_update(channel=channel_id, ts=message_ts, text="SNSへ投稿中", blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": "🚀 SNSへ自動投稿中です..."}}])
                threading.Thread(target=execute_sns_post, args=(channel_id, thread_ts, draft_text)).start()

            # 「修正して投稿」が押された時（Modalを開く）
            elif action_id == "post_edit":
                draft_text = action.get("value", "")
                trigger_id = payload["trigger_id"]
                # 投稿先情報などをModalの裏側に持たせる
                metadata = json.dumps({"channel_id": channel_id, "thread_ts": thread_ts, "message_ts": message_ts})
                
                client.views_open(
                    trigger_id=trigger_id,
                    view={
                        "type": "modal",
                        "callback_id": "edit_post_modal",
                        "private_metadata": metadata,
                        "title": {"type": "plain_text", "text": "投稿内容の修正"},
                        "submit": {"type": "plain_text", "text": "この内容で投稿"},
                        "close": {"type": "plain_text", "text": "キャンセル"},
                        "blocks": [
                            {
                                "type": "input",
                                "block_id": "draft_input_block",
                                "element": {
                                    "type": "plain_text_input",
                                    "action_id": "draft_input",
                                    "multiline": True,
                                    "initial_value": draft_text
                                },
                                "label": {"type": "plain_text", "text": "修正後の投稿テキスト"}
                            }
                        ]
                    }
                )

            # 「キャンセル」が押された時
            elif action_id == "post_cancel":
                client.chat_update(channel=channel_id, ts=message_ts, text="キャンセル完了", blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": "❌ SNSへの投稿をキャンセルしました。"}}])

        # --- B. Modalから「この内容で投稿」が送信された時の処理 ---
        elif payload.get("type") == "view_submission":
            view = payload["view"]
            if view["callback_id"] == "edit_post_modal":
                # 入力された修正後のテキストを取得
                edited_text = view["state"]["values"]["draft_input_block"]["draft_input"]["value"]
                # 裏側に持たせていたチャンネル情報を取り出す
                metadata = json.loads(view["private_metadata"])
                channel_id = metadata["channel_id"]
                thread_ts = metadata["thread_ts"]
                message_ts = metadata["message_ts"]
                
                client.chat_update(channel=channel_id, ts=message_ts, text="SNSへ投稿中", blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": "🚀 修正版テキストでSNSへ自動投稿中です..."}}])
                threading.Thread(target=execute_sns_post, args=(channel_id, thread_ts, edited_text)).start()
                
                # Modalを閉じるために空を返す
                return "", 200

        return jsonify({"status": "ok"}), 200
    return jsonify({"error": "No payload"}), 400

# ---------------------------------------------------------
# 3. AIにドラフトを生成させる関数
# ---------------------------------------------------------
def process_ai_draft(channel_id, thread_ts, original_text):
    if gemini_client is None:
        client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text="⚠️ ドラフト作成エラー: GEMINI_API_KEY が設定されていません。",
        )
        return

    prompt = f"""
【元のテキスト】から、【フォーマットのルール】に従ってSNSへの投稿ドラフトを作成してください。
プレースホルダー（[]で囲まれた部分）は元のテキストから推測して埋めてください。
埋めた後はプレースホルダーは削除してください。
埋められなかったものは、プレースホルダーを残したままにしてください。
最終的に生成する文章は、投稿する内容のみで、説明や補足は一切含めないでください。

【フォーマットのルール】
1. Type A：Podcastの場合（「Podcast」やSpotifyのURLがある場合）
✨📚Podcast 新エピソード公開📚✨
Podcast「Tech Startupの舞台裏」でお届けする[テーマ・内容の説明]。[ゲストや内容の紹介1文] 🎙️

2. Type B：投資先ニュースの場合
🚩投資先News🚩
[会社名] @[xハンドル] が、[ニュース内容の具体的説明] [元記事URL]

3. Type C-1：UTECニュース
🚩UTEC News🚩
[内容説明。@メンションがあれば含める] [URL]

【元のテキスト】
{original_text}
"""
    try:
        response = gemini_client.models.generate_content(
            model=gemini_model,
            contents=prompt,
        )
        draft_text = response.text
        
        # 承認・修正・キャンセルの3つのボタンを付けて送信
        client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text="ドラフトが完成しました",
            blocks=[
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"🤖 *ドラフトが完成しました！*\n```\n{draft_text}\n```"}
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "✅ このまま投稿", "emoji": True},
                            "style": "primary",
                            "value": draft_text,
                            "action_id": "post_approve"
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "✏️ 修正して投稿", "emoji": True},
                            "value": draft_text,
                            "action_id": "post_edit"
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "❌ キャンセル", "emoji": True},
                            "style": "danger",
                            "value": "cancel",
                            "action_id": "post_cancel"
                        }
                    ]
                }
            ]
        )
    except Exception as e:
        client.chat_postMessage(channel=channel_id, thread_ts=thread_ts, text=f"⚠️ ドラフト作成エラー: {e}")

# ---------------------------------------------------------
# 4. 各SNSへ自動投稿を実行する関数
# ---------------------------------------------------------
def execute_sns_post(channel_id, thread_ts, text):
    results = []
    
    # --- X (Twitter) へ投稿 ---
    try:
        post_to_x(text, [])
        results.append("✅ X (Twitter)")
    except BaseException as e: # ← SystemExitも捕まえるために BaseException に変更
        results.append(f"❌ X (Twitter) - エラー: {e}")
        
    # --- Facebook へ投稿 ---
    try:
        post_to_facebook(text, None, None)
        results.append("✅ Facebook")
    except BaseException as e: # ← 同上
        results.append(f"❌ Facebook - エラー: {e}")
        
    # --- LinkedIn へ投稿 ---
    try:
        post_to_linkedin(text, None)
        results.append("✅ LinkedIn")
    except BaseException as e: # ← 同上
        results.append(f"❌ LinkedIn - エラー: {e}")
        
    # スレッドに最終結果を報告
    result_text = "🎯 *SNSへの自動投稿処理が完了しました*\n\n" + "\n".join(results)
    client.chat_postMessage(channel=channel_id, thread_ts=thread_ts, text=result_text)

if __name__ == '__main__':
    app.run(port=3000, debug=True)