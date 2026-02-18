import streamlit as st
from google import genai
from google.genai import types
import tempfile
import os
import time
from datetime import datetime
import json
import requests
import hashlib

# Firebase初期化（オプション）
try:
    import firebase_admin
    from firebase_admin import credentials, firestore
    FIREBASE_ADMIN_AVAILABLE = True
except ImportError:
    FIREBASE_ADMIN_AVAILABLE = False

# ページ設定
st.set_page_config(
    page_title="AIボイス議事録",
    page_icon="🎙️",
    layout="wide"
)

# システムプロンプト
SYSTEM_PROMPT = """あなたはプロの議事録作成者です。提供された音声ファイルを注意深く聴き、以下の構成で議事録をまとめてください。

## 会議の目的
何のための会議か。

## 議論の要約
どのような議論が行われたか（時系列またはトピック別）。

## ネクストアクション
- [ ] 【担当者名】具体的なタスク内容（あれば期限も）

## 決定事項
合意に至った内容。

---
**注意点:**
- 発話者が特定できる場合は「Aさん：〜」のように記載してください。
- 音質が悪い箇所は推測せず、事実に忠実であること。
- 不明瞭な部分は「（聞き取り不可）」と記載してください。
"""

# Firebase Auth REST API エンドポイント
FIREBASE_AUTH_URL = "https://identitytoolkit.googleapis.com/v1/accounts"

def generate_org_id(org_name: str) -> str:
    """組織名から一意のIDを生成"""
    return hashlib.md5(org_name.lower().strip().encode()).hexdigest()[:12]

def firebase_auth_request(endpoint: str, data: dict, api_key: str):
    """Firebase Auth REST APIリクエスト"""
    url = f"{FIREBASE_AUTH_URL}:{endpoint}?key={api_key}"
    response = requests.post(url, json=data)
    return response.json()

def sign_up(email: str, password: str, api_key: str):
    """新規ユーザー登録"""
    data = {
        "email": email,
        "password": password,
        "returnSecureToken": True
    }
    return firebase_auth_request("signUp", data, api_key)

def sign_in(email: str, password: str, api_key: str):
    """ログイン"""
    data = {
        "email": email,
        "password": password,
        "returnSecureToken": True
    }
    return firebase_auth_request("signInWithPassword", data, api_key)

def reset_password(email: str, api_key: str):
    """パスワードリセットメール送信"""
    data = {
        "email": email,
        "requestType": "PASSWORD_RESET"
    }
    return firebase_auth_request("sendOobCode", data, api_key)

def init_firestore():
    """Firestore初期化"""
    if not FIREBASE_ADMIN_AVAILABLE:
        return None
    
    if firebase_admin._apps:
        return firestore.client()
    
    try:
        if "firebase" in st.secrets and "service_account" in st.secrets["firebase"]:
            cred_dict = json.loads(st.secrets["firebase"]["service_account"])
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
            return firestore.client()
    except Exception as e:
        st.warning(f"Firestore未設定: {e}")
    return None

def get_or_create_organization(db, org_name: str):
    """組織を取得または作成"""
    if db is None:
        return None
    
    org_id = generate_org_id(org_name)
    org_ref = db.collection("organizations").document(org_id)
    org_doc = org_ref.get()
    
    if not org_doc.exists:
        # 新規組織作成
        org_ref.set({
            "name": org_name.strip(),
            "created_at": datetime.now()
        })
    
    return org_id

def get_user_organization(db, user_id: str):
    """ユーザーの組織IDを取得"""
    if db is None:
        return None
    
    try:
        user_doc = db.collection("users").document(user_id).get()
        if user_doc.exists:
            return user_doc.to_dict().get("organization_id")
    except:
        pass
    return None

def save_user_organization(db, user_id: str, user_email: str, org_id: str, org_name: str):
    """ユーザーの組織情報を保存"""
    if db is None:
        return
    
    try:
        db.collection("users").document(user_id).set({
            "email": user_email,
            "organization_id": org_id,
            "organization_name": org_name,
            "created_at": datetime.now()
        })
    except Exception as e:
        st.error(f"ユーザー情報保存エラー: {e}")

def get_organization_name(db, org_id: str):
    """組織IDから組織名を取得"""
    if db is None:
        return None
    
    try:
        org_doc = db.collection("organizations").document(org_id).get()
        if org_doc.exists:
            return org_doc.to_dict().get("name")
    except:
        pass
    return None

def check_firebase_auth(db):
    """Firebase Authentication認証（組織対応）"""
    # セッション状態初期化
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
        st.session_state.user_email = None
        st.session_state.user_id = None
        st.session_state.organization_id = None
        st.session_state.organization_name = None
    
    # Firebase API Key確認
    if "firebase" not in st.secrets or "api_key" not in st.secrets["firebase"]:
        st.error("Firebase API Keyが設定されていません")
        st.info("secrets.tomlに[firebase]セクションを追加してください")
        return False
    
    api_key = st.secrets["firebase"]["api_key"]
    
    if st.session_state.authenticated:
        # 組織情報がまだない場合は取得
        if st.session_state.organization_id is None and db:
            org_id = get_user_organization(db, st.session_state.user_id)
            if org_id:
                st.session_state.organization_id = org_id
                st.session_state.organization_name = get_organization_name(db, org_id)
        return True
    
    # ログイン/新規登録タブ
    tab1, tab2, tab3 = st.tabs(["🔑 ログイン", "📝 新規登録", "🔄 パスワードリセット"])
    
    with tab1:
        st.subheader("ログイン")
        email = st.text_input("メールアドレス", key="login_email")
        password = st.text_input("パスワード", type="password", key="login_password")
        
        if st.button("ログイン", type="primary", use_container_width=True):
            if email and password:
                with st.spinner("ログイン中..."):
                    result = sign_in(email, password, api_key)
                
                if "idToken" in result:
                    user_id = result.get("localId")
                    st.session_state.authenticated = True
                    st.session_state.user_email = result.get("email")
                    st.session_state.user_id = user_id
                    
                    # 組織情報を取得
                    if db:
                        org_id = get_user_organization(db, user_id)
                        if org_id:
                            st.session_state.organization_id = org_id
                            st.session_state.organization_name = get_organization_name(db, org_id)
                        else:
                            st.warning("組織情報がありません。新規登録し直すか、管理者にお問い合わせください。")
                    
                    st.success("ログイン成功！")
                    st.rerun()
                else:
                    error_msg = result.get("error", {}).get("message", "不明なエラー")
                    if "INVALID_LOGIN_CREDENTIALS" in error_msg:
                        st.error("メールアドレスまたはパスワードが間違っています")
                    elif "USER_NOT_FOUND" in error_msg:
                        st.error("ユーザーが見つかりません")
                    else:
                        st.error(f"ログインエラー: {error_msg}")
            else:
                st.warning("メールアドレスとパスワードを入力してください")
    
    with tab2:
        st.subheader("新規アカウント登録")
        
        # 組織名入力
        org_name = st.text_input("組織名（会社名・チーム名）", key="signup_org",
                                  help="同じ組織名のメンバーと議事録を共有できます")
        
        new_email = st.text_input("メールアドレス", key="signup_email")
        new_password = st.text_input("パスワード", type="password", key="signup_password", 
                                      help="6文字以上")
        confirm_password = st.text_input("パスワード（確認）", type="password", key="confirm_password")
        
        if st.button("アカウント作成", type="primary", use_container_width=True):
            if org_name and new_email and new_password and confirm_password:
                if new_password != confirm_password:
                    st.error("パスワードが一致しません")
                elif len(new_password) < 6:
                    st.error("パスワードは6文字以上にしてください")
                elif len(org_name.strip()) < 2:
                    st.error("組織名を2文字以上で入力してください")
                else:
                    with st.spinner("アカウント作成中..."):
                        result = sign_up(new_email, new_password, api_key)
                    
                    if "idToken" in result:
                        user_id = result.get("localId")
                        user_email = result.get("email")
                        
                        # 組織を作成または取得
                        if db:
                            org_id = get_or_create_organization(db, org_name)
                            save_user_organization(db, user_id, user_email, org_id, org_name.strip())
                            st.session_state.organization_id = org_id
                            st.session_state.organization_name = org_name.strip()
                        
                        st.session_state.authenticated = True
                        st.session_state.user_email = user_email
                        st.session_state.user_id = user_id
                        st.success("アカウント作成成功！")
                        st.rerun()
                    else:
                        error_msg = result.get("error", {}).get("message", "不明なエラー")
                        if "EMAIL_EXISTS" in error_msg:
                            st.error("このメールアドレスは既に登録されています")
                        elif "WEAK_PASSWORD" in error_msg:
                            st.error("パスワードが弱すぎます。6文字以上にしてください")
                        elif "INVALID_EMAIL" in error_msg:
                            st.error("メールアドレスの形式が正しくありません")
                        else:
                            st.error(f"登録エラー: {error_msg}")
            else:
                st.warning("すべての項目を入力してください")
    
    with tab3:
        st.subheader("パスワードリセット")
        reset_email = st.text_input("登録済みメールアドレス", key="reset_email")
        
        if st.button("リセットメールを送信", use_container_width=True):
            if reset_email:
                with st.spinner("送信中..."):
                    result = reset_password(reset_email, api_key)
                
                if "error" not in result:
                    st.success("パスワードリセットメールを送信しました。メールを確認してください。")
                else:
                    error_msg = result.get("error", {}).get("message", "不明なエラー")
                    if "EMAIL_NOT_FOUND" in error_msg:
                        st.error("このメールアドレスは登録されていません")
                    else:
                        st.error(f"エラー: {error_msg}")
            else:
                st.warning("メールアドレスを入力してください")
    
    return False

def save_to_firestore(db, title, content, audio_filename, user_email, user_id, org_id):
    """議事録をFirestoreに保存（組織別）"""
    if db is None or org_id is None:
        return None
    
    try:
        doc_ref = db.collection("organizations").document(org_id).collection("minutes").document()
        doc_ref.set({
            "title": title,
            "content": content,
            "audio_filename": audio_filename,
            "created_by": user_email,
            "user_id": user_id,
            "created_at": datetime.now()
        })
        return doc_ref.id
    except Exception as e:
        st.error(f"保存エラー: {e}")
        return None

def get_minutes_history(db, org_id):
    """議事録履歴を取得（同一組織のみ）"""
    if db is None or org_id is None:
        return []
    
    try:
        docs = db.collection("organizations").document(org_id).collection("minutes").order_by("created_at", direction=firestore.Query.DESCENDING).limit(20).stream()
        history = []
        for doc in docs:
            data = doc.to_dict()
            data["id"] = doc.id
            history.append(data)
        return history
    except Exception as e:
        st.warning(f"履歴取得エラー: {e}")
        return []

def get_minute_by_id(db, org_id, doc_id):
    """IDで議事録を取得（組織別）"""
    if db is None or org_id is None:
        return None
    
    try:
        doc = db.collection("organizations").document(org_id).collection("minutes").document(doc_id).get()
        if doc.exists:
            data = doc.to_dict()
            data["id"] = doc.id
            return data
    except Exception as e:
        st.error(f"取得エラー: {e}")
    return None

def upload_and_process_audio(audio_file, model_name, additional_instructions):
    """音声ファイルをアップロードしてGeminiで処理"""
    
    # クライアント設定
    client = genai.Client(api_key=st.secrets["api"]["google_api_key"])
    
    # 一時ファイルに保存
    suffix = os.path.splitext(audio_file.name)[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
        tmp_file.write(audio_file.getvalue())
        tmp_path = tmp_file.name
    
    try:
        # 進捗表示
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # 音声ファイルをアップロード
        status_text.text("🔄 音声ファイルをアップロード中...")
        progress_bar.progress(20)
        
        uploaded_file = client.files.upload(file=tmp_path)
        
        # ファイルがアクティブになるまで待機
        status_text.text("⏳ 音声ファイルを処理中...")
        progress_bar.progress(40)
        
        while uploaded_file.state.name == "PROCESSING":
            time.sleep(2)
            uploaded_file = client.files.get(name=uploaded_file.name)
        
        if uploaded_file.state.name == "FAILED":
            st.error("音声ファイルの処理に失敗しました。")
            return None
        
        # 議事録生成
        status_text.text("📝 議事録を生成中...")
        progress_bar.progress(60)
        
        # プロンプト構築
        prompt = SYSTEM_PROMPT
        if additional_instructions:
            prompt += f"\n\n**追加指示:**\n{additional_instructions}"
        
        response = client.models.generate_content(
            model=model_name,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_uri(
                            file_uri=uploaded_file.uri,
                            mime_type=uploaded_file.mime_type
                        ),
                        types.Part.from_text(text=prompt)
                    ]
                )
            ]
        )
        
        progress_bar.progress(100)
        status_text.text("✅ 完了！")
        
        # アップロードしたファイルを削除
        try:
            client.files.delete(name=uploaded_file.name)
        except:
            pass
        
        return response.text
        
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

def main():
    st.title("🎙️ AIボイス議事録")
    st.markdown("音声ファイルをアップロードするだけで、AIが自動で議事録を作成します。")
    
    # Firestore初期化
    db = init_firestore()
    
    # Firebase Authentication（組織対応）
    if not check_firebase_auth(db):
        return
    
    # 組織情報確認
    org_id = st.session_state.organization_id
    org_name = st.session_state.organization_name
    
    # 組織未登録の場合は登録画面を表示
    if org_id is None and db:
        st.warning("⚠️ 組織情報が登録されていません")
        st.markdown("### 組織の登録")
        st.markdown("議事録を保存・共有するには組織（会社名・チーム名）の登録が必要です。")
        
        new_org_name = st.text_input("組織名（会社名・チーム名）", 
                                      placeholder="例：株式会社ABC / 営業チーム",
                                      help="同じ組織名のメンバーと議事録を共有できます")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("組織を登録", type="primary", use_container_width=True):
                if new_org_name and len(new_org_name.strip()) >= 2:
                    with st.spinner("登録中..."):
                        org_id = get_or_create_organization(db, new_org_name)
                        save_user_organization(
                            db, 
                            st.session_state.user_id, 
                            st.session_state.user_email, 
                            org_id, 
                            new_org_name.strip()
                        )
                        st.session_state.organization_id = org_id
                        st.session_state.organization_name = new_org_name.strip()
                    st.success("組織を登録しました！")
                    st.rerun()
                else:
                    st.error("組織名を2文字以上で入力してください")
        with col2:
            if st.button("ログアウト", use_container_width=True):
                st.session_state.authenticated = False
                st.session_state.user_email = None
                st.session_state.user_id = None
                st.session_state.organization_id = None
                st.session_state.organization_name = None
                st.rerun()
        return
    
    # サイドバー
    st.sidebar.header("⚙️ 設定")
    st.sidebar.success(f"✅ {st.session_state.user_email}")
    if org_name:
        st.sidebar.info(f"🏢 {org_name}")
    
    # ログアウトボタン
    if st.sidebar.button("ログアウト"):
        st.session_state.authenticated = False
        st.session_state.user_email = None
        st.session_state.user_id = None
        st.session_state.organization_id = None
        st.session_state.organization_name = None
        st.rerun()
    
    st.sidebar.markdown("---")
    
    # モデル選択
    model_option = st.sidebar.selectbox(
        "モデル選択",
        options=["gemini-2.0-flash", "gemini-1.5-pro"],
        format_func=lambda x: "Gemini 2.0 Flash（高速・安価）" if "flash" in x else "Gemini 1.5 Pro（高精度）"
    )
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("""
    **対応形式:** .mp3, .wav, .m4a  
    **最大サイズ:** 500MB
    """)
    
    # 履歴表示（同一組織のみ）
    if db and org_id:
        st.sidebar.markdown("---")
        st.sidebar.subheader("📚 議事録履歴")
        history = get_minutes_history(db, org_id)
        
        if history:
            for item in history:
                created_at = item.get("created_at")
                if created_at:
                    date_str = created_at.strftime("%m/%d %H:%M")
                else:
                    date_str = "日時不明"
                
                label = f"{date_str} - {item.get('title', '無題')[:15]}"
                if st.sidebar.button(label, key=item["id"]):
                    st.session_state.selected_minute = item["id"]
                    st.rerun()
        else:
            st.sidebar.caption("履歴がありません")
    
    # メインエリア
    if "selected_minute" in st.session_state and st.session_state.selected_minute and db and org_id:
        minute = get_minute_by_id(db, org_id, st.session_state.selected_minute)
        if minute:
            st.markdown("## 📋 過去の議事録")
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"**タイトル:** {minute.get('title', '無題')}")
                st.markdown(f"**作成者:** {minute.get('created_by', '不明')}")
                if minute.get("created_at"):
                    st.markdown(f"**作成日時:** {minute['created_at'].strftime('%Y-%m-%d %H:%M')}")
            with col2:
                if st.button("🆕 新規作成に戻る"):
                    st.session_state.selected_minute = None
                    st.rerun()
            
            st.markdown("---")
            st.markdown(minute.get("content", ""))
            
            st.markdown("---")
            st.code(minute.get("content", ""), language="markdown")
            return
    
    # 新規議事録作成
    col1, col2 = st.columns([2, 1])
    
    with col1:
        uploaded_file = st.file_uploader(
            "音声ファイルをアップロード",
            type=["mp3", "wav", "m4a"],
            help="会議の音声ファイルをドラッグ＆ドロップしてください"
        )
        
        if uploaded_file:
            st.audio(uploaded_file)
            st.caption(f"📁 {uploaded_file.name} ({uploaded_file.size / 1024 / 1024:.2f} MB)")
    
    with col2:
        title = st.text_input(
            "議事録タイトル",
            placeholder="例：週次定例会議 2024/01/25"
        )
        
        additional_instructions = st.text_area(
            "追加指示（任意）",
            placeholder="例：専門用語が多いので、技術的な文脈を重視して",
            height=80
        )
    
    # 実行ボタン
    if st.button("🚀 音声を解析して議事録作成", type="primary", use_container_width=True):
        if not uploaded_file:
            st.error("音声ファイルをアップロードしてください")
            return
        
        if not org_id:
            st.error("組織情報がありません。ログアウトして再度登録してください。")
            return
        
        with st.spinner("議事録を生成中..."):
            result = upload_and_process_audio(
                uploaded_file, 
                model_option, 
                additional_instructions
            )
        
        if result:
            st.success("議事録が生成されました！")
            
            # Firestoreに保存
            if db:
                doc_title = title if title else uploaded_file.name
                doc_id = save_to_firestore(
                    db, 
                    doc_title, 
                    result, 
                    uploaded_file.name,
                    st.session_state.user_email,
                    st.session_state.user_id,
                    org_id
                )
                if doc_id:
                    st.info("💾 議事録を保存しました")
            
            # 結果表示
            st.markdown("---")
            st.markdown("## 📋 生成された議事録")
            st.markdown(result)
            
            st.markdown("---")
            st.markdown("### 📝 コピー用（Markdown形式）")
            st.code(result, language="markdown")
            
            st.download_button(
                label="📥 議事録をダウンロード (.md)",
                data=result,
                file_name="meeting_minutes.md",
                mime="text/markdown"
            )

if __name__ == "__main__":
    main()
