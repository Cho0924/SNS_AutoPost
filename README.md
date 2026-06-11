## ファイルの役割

- `app.py`  
	Slackのボタン押下を受け取るFlaskアプリです。
- `send_test_message.py`  
	Slackにテスト用の承認メッセージを送るスクリプトです。
- `post_test_message.py`  
	X、Facebook、LinkedInへテスト投稿するスクリプトです。

## Slack とローカルの接続

このプロジェクトでは、ローカルで動く `app.py` を ngrok 経由で Slack から受け取れるようにします。`ngrok http 3000` で発行された URL を使い、Slack App の「Interactivity & Shortcuts」を ON にして、Request URL に `https://xxxx.ngrok-free.app/slack/interactive` を設定してください。Salck App の「Event Subscriptions」でも同様にしてください。

手順は次のとおりです。

1. ターミナルで `python app.py` を実行してローカルサーバーを起動します。
2. 別ターミナルで `ngrok http 3000` を実行し、公開 URL を確認します。
3. Slack AppのURLとBotの権限の設定
