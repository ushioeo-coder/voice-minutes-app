# AIボイス議事録アプリ

音声ファイルをアップロードするだけで、AI（Gemini）が自動で議事録を作成するWebアプリです。

## 機能

- 🎙️ 音声ファイル（.mp3, .wav, .m4a, .aac, .ogg, .flac）から議事録を自動生成
- 📝 Markdown形式で出力
- ⚡ モデル選択（Gemini 2.0 Flash / 1.5 Pro）
- 🔒 複数ユーザー認証
- 💾 Firebase Firestore連携で議事録保存・共有
- 📚 履歴一覧から過去の議事録を閲覧

## セットアップ

### ローカル実行

```bash
# 依存関係インストール
pip install -r requirements.txt

# 起動
streamlit run app.py
```

### Streamlit Cloudデプロイ

1. GitHubリポジトリにプッシュ
2. [Streamlit Cloud](https://streamlit.io/cloud)でリポジトリを連携
3. Secrets設定で以下を追加:

```toml
[users]
user1 = "password1"
user2 = "password2"

[api]
google_api_key = "your_gemini_api_key"

# Firebase使用時（オプション）
[firebase]
service_account = '{"type": "service_account", "project_id": "...", ...}'
```

## Firebase設定（オプション）

1. [Firebase Console](https://console.firebase.google.com/)でプロジェクト作成
2. Firestoreデータベースを有効化
3. プロジェクト設定 > サービスアカウント > 新しい秘密鍵を生成
4. JSONの内容を`service_account`に設定

## 使い方

1. ユーザー名・パスワードでログイン
2. モデルを選択
3. 音声ファイルをアップロード
4. タイトルを入力（任意）
5. 「音声を解析して議事録作成」をクリック
6. 生成された議事録をコピーまたはダウンロード
7. Firebase連携時は自動保存され、履歴から閲覧可能
