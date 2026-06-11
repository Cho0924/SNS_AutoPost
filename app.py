import json
from flask import Flask, request, jsonify

app = Flask(__name__)

# Slackからのイベントを受け取るエンドポイント
@app.route('/slack/interactive', methods=['POST'])
def slack_interactive():
    # Slackからのインタラクティブペイロードはフォームデータの 'payload' キーに含まれます
    if 'payload' in request.form:
        payload = json.loads(request.form['payload'])
        
        # フェーズ3のテスト要件：コンソールに通知とJSONデータを出力する
        print("\n=========================================")
        print("🎉 ボタンが押されました！")
        print("=========================================")
        # 受け取ったJSONデータを見やすく整形して出力
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        print("=========================================\n")
        
        # Slackには3秒以内に200 OKを返す必要があります
        return jsonify({"status": "ok"}), 200
        
    return jsonify({"error": "No payload found"}), 400

if __name__ == '__main__':
    # ngrok http 3000 の設定に合わせてポート3000で起動
    app.run(port=3000, debug=True)