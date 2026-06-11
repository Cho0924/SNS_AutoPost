import os
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from dotenv import load_dotenv

# ⚠️ 注意: 実際の運用ではフェーズ2で作成した .env ファイルから読み込むことを推奨します [cite: 242]
# 引き継ぎドキュメントに記載されている xoxb-... から始まるトークンを入力してください [cite: 285]
load_dotenv()
slack_token = os.getenv("SLACK_BOT_TOKEN")
client = WebClient(token=slack_token)

# 送信先のチャンネルID（#pf_pr_sns）を指定します [cite: 9, 10]
channel_id = "C051F309CCT" 

try:
    # Block Kitを使ってボタン付きメッセージを組み立てます
    response = client.chat_postMessage(
        channel=channel_id,
        text="自動投稿の承認テスト", # 通知バッジ用のフォールバックテキスト
        blocks=[
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "🤖 *テスト:* Podcastの新しいエピソードが検出されました。ドラフトを作成して投稿しますか？"
                }
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "承認する",
                            "emoji": True
                        },
                        "style": "primary", # ボタンを緑色にします
                        "value": "approve_podcast_test",
                        "action_id": "approve_button_clicked" # 押下時に特定するためのID
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "キャンセル",
                            "emoji": True
                        },
                        "style": "danger", # ボタンを赤色にします
                        "value": "cancel_test",
                        "action_id": "cancel_button_clicked"
                    }
                ]
            }
        ]
    )
    print("✅ Slackにテストメッセージを送信しました！")
    
except SlackApiError as e:
    print(f"⚠️ エラーが発生しました: {e.response['error']}")