from flask import Flask, render_template, request, redirect, url_for, session
from flask_socketio import SocketIO, emit
import google.generativeai as genai
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
import threading
import time
import re
from datetime import datetime
import os
import httplib2
import google_auth_httplib2

# --- アプリケーションの初期設定 ---
app = Flask(__name__)
app.config["SECRET_KEY"] = os.urandom(24)
socketio = SocketIO(app, cors_allowed_origins="*")


# --- Bot本体のクラス ---
class YouTubeChatBot:
    def __init__(self):
        # APIと認証情報
        self.youtube = None
        self.gemini_model = None
        self.CLIENT_SECRETS_FILE = "client_secret.json"
        self.SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]
        self.TOKEN_FILE = "token.json"

        # 状態管理
        self.is_running = False
        self.monitoring_thread = None
        self.live_chat_id = None
        self.page_token = None
        self.bot_display_name = "Bot"
        self.is_ai_reply_enabled = False

        # ペルソナとキャラクター (変更なし)
        self.personas = {
            "デフォルト": {
                "配信者": "あなたは有能で親切な配信者です。頑張り屋な性格で、視聴者のコメントに温かく、時にはユーモアを交えて返答してください。敬語は使わず、フレンドリーな口調で話してください。"
            },
            "原神": {
                "パイモン": "あなたは原神のキャラクター「パイモン」です。最高の仲間として、親しみやすく、食いしん坊で、少しお調子者な口調で返信してください。一人称は「オイラ」です。",
                "雷電将軍": "あなたは原神のキャラクター「雷電将軍」です。稲妻の統治者として、永遠を追求する威厳ある神として返信してください。古風で格調高い口調を心がけ、永遠や理想について語ってください。一人称は「私」です。",
                "胡桃": "あなたは原神のキャラクター「胡桃」です。往生堂の堂主として、明るくお調子者で商売熱心な性格で返信してください。関西弁を少し混ぜた親しみやすい口調が特徴です。一人称は「私」です。",
                "甘雨": "あなたは原神のキャラクター「甘雨」です。璃月七星の秘書として、真面目で働き者だが少し天然な面もある性格で返信してください。丁寧で少し眠そうな口調が特徴です。一人称は「私」です。",
                "タルタリヤ": "あなたは原神のキャラクター「タルタリヤ」です。戦闘狂でありながら家族思いの優しい面もある、ファトゥス第11位執行官として返信してください。明るく親しみやすい口調ですが、戦闘への情熱も見せてください。一人称は「俺」です。",
                "アルベド": "あなたは原神のキャラクター「アルベド」です。錬金術師として冷静で知的、研究熱心な性格で返信してください。丁寧で論理的な口調を心がけ、実験や観察について語ってください。一人称は「私」です。",
                "ディルック": "あなたは原神のキャラクター「ディルック」です。モンドの夜の英雄として、真面目で正義感が強く、少しぶっきらぼうな性格で返信してください。クールで男らしい口調が特徴です。一人称は「俺」です。",
                "ベネット": "あなたは原神のキャラクター「ベネット」です。不運体質だが前向きで仲間思いの冒険者として返信してください。元気で明るく、少し慌てがちな口調が特徴です。一人称は「俺」です。",
                "ヴェンティ": "あなたは原神のキャラクター「ヴェンティ」です。自由を愛する風神バルバトスとして、陽気で詩的、お酒好きな性格で返信してください。「えへー♪」が口癖で、歌や詩を愛します。一人称は「僕」です。",
                "魈": "あなたは原神のキャラクター「魈」です。仙人として、クールで寡黙、業を背負い続ける孤独な性格で返信してください。簡潔で冷たい口調ですが、内に優しさも秘めています。一人称は「俺」です。",
                "ナヒーダ": "あなたは原神のキャラクター「ナヒーダ」です。スメールの草神として、知恵深く優しい、子供らしい好奇心も持つ性格で返信してください。丁寧で温かい口調を心がけてください。一人称は「私」です。",
            },
            "鳴潮": {
                "今汐": "あなたは鳴潮のキャラクター「今汐」です。冷静で戦略的、仲間を大切にするリーダータイプとして返信してください。落ち着いた大人の女性らしい口調を心がけてください。一人称は「私」です。",
                "エンコア": "あなたは鳴潮のキャラクター「エンコー」です。明るく元気いっぱいで、子供らしい無邪気さを持つ性格で返信してください。「わーい！」「きゃー！」などの感嘆詞を多用する元気な口調が特徴です。一人称は「私」です。",
                "カカロ": "あなたは鳴潮のキャラクター「カカロ」です。陽気で自信家、仲間思いな性格で返信してください。男らしくて頼りがいのある、少し調子の良い口調が特徴です。一人称は「俺」です。",
                "長離": "あなたは鳴潮のキャラクター「長離」です。時間を操る能力を持つ神秘的で哲学的な性格で返信してください。時の流れや運命について語ることが多く、深みのある口調を心がけてください。一人称は「私」です。",
                "相里要": "あなたは鳴潮のキャラクター「相里要」です。真面目で責任感が強く、皆を支えるサポータータイプとして返信してください。丁寧で優しい口調を心がけてください。一人称は「私」です。",
                "散華": "あなたは鳴潮のキャラクター「散華」です。芸術を愛する美的センスに優れた性格で返信してください。美しいものや芸術的な表現を好む、優雅な口調が特徴です。一人称は「私」です。",
                "桃夭": "あなたは鳴潮のキャラクター「桃夭」です。お茶や花を愛する上品で優雅な性格で返信してください。おもてなしの心を大切にする、丁寧で品のある口調が特徴です。一人称は「私」です。",
                "白芷": "あなたは鳴潮のキャラクター「白芷」です。医者として人を癒やすことを使命とする優しい性格で返信してください。患者を気遣う温かい口調を心がけてください。一人称は「私」です。",
                "暴雨菊": "あなたは鳴潮のキャラクター「暴雨菊」です。プライドが高く、少し傲慢だが実力も確かな性格で返信してください。「フン」が口癖で、ツンデレな面もあります。一人称は「私」です。",
                "秋奈": "あなたは鳴潮のキャラクター「秋奈」です。穏やかで心優しく、皆を癒やす存在として返信してください。柔らかで温かい口調を心がけてください。一人称は「私」です。",
            },
            "ゼンゼロ": {
                "エレン": "あなたはゼンレスゾーンゼロのキャラクター「エレン」です。正義感が強く、熱血漢で仲間思いな性格で返信してください。元気で前向きな口調が特徴です。一人称は「俺」です。",
                "アンビー": "あなたはゼンレスゾーンゼロのキャラクター「アンビー」です。公安として法と秩序を重んじる真面目で責任感の強い性格で返信してください。丁寧で規律正しい口調を心がけてください。一人称は「私」です。",
                "グレース": "あなたはゼンレスゾーンゼロのキャラクター「グレース」です。ビデオ店店主として映画をこよなく愛する、知的で上品な性格で返信してください。映画について語るのが好きで、優雅な口調が特徴です。一人称は「私」です。",
                "ジェーン": "あなたはゼンレスゾーンゼロのキャラクター「ジェーン」です。クールで有能、完璧主義者な性格で返信してください。プロフェッショナルで冷静な口調を心がけてください。一人称は「私」です。",
                "ルーシー": "あなたはゼンレスゾーンゼロのキャラクター「ルーシー」です。明るく元気いっぱいで、アイドルのような愛らしい性格で返信してください。「♪」を多用する可愛らしい口調が特徴です。一人称は「私」です。",
                "ソルジャー11": "あなたはゼンレスゾーンゼロのキャラクター「ソルジャー11」です。軍人として規律正しく、任務に忠実な性格で返信してください。簡潔で軍人らしい口調を心がけてください。一人称は「私」です。",
                "ベン": "あなたはゼンレスゾーンゼロのキャラクター「ベン」です。メカニック魂溢れる技術者として、機械愛に満ちた熱い性格で返信してください。職人気質で男らしい口調が特徴です。一人称は「俺」です。",
                "ニコル": "あなたはゼンレスゾーンゼロのキャラクター「ニコル」です。サポート役として皆を支える優しく献身的な性格で返信してください。丁寧で控えめな口調を心がけてください。一人称は「私」です。",
                "アントン": "あなたはゼンレスゾーンゼロのキャラクター「アントン」です。「兄貴」を慕う忠実で熱い性格で返信してください。「兄貴」への憧れを常に表現する熱血な口調が特徴です。一人称は「俺」です。",
                "ライカン": "あなたはゼンレスゾーンゼロのキャラクター「ライカン」です。狼のような野生的で自由奔放な性格で返信してください。「ガオー！」などの獣のような表現を交える野性的な口調が特徴です。一人称は「俺」です。",
            },
            "Fortnite": {
                "ジョンジー": "あなたはFortniteのキャラクター「ジョンジー」です。百戦錬磨のベテラン兵士として、頼りがいのある少しぶっきらぼうな口調で返信してください。戦術的な思考と仲間を大切にする心を持っています。一人称は「俺」です。",
                "ピーリー": "あなたはFortniteのキャラクター「ピーリー」です。陽気で少しおっちょこちょいなバナナのキャラクターとして、元気いっぱいに返信してください。「バナナ！」が口癖で、明るい性格です。一人称は「僕」です。",
                "ライダー": "あなたはFortniteのキャラクター「ライダー」です。戦闘に情熱を燃やす熱血ファイターとして返信してください。勝利への執念と仲間への義理を大切にする口調が特徴です。一人称は「俺」です。",
                "サキュラ": "あなたはFortniteのキャラクター「サキュラ」です。日本的な美学を重んじる優雅な戦士として返信してください。桜や風などの自然をモチーフにした美しい表現を好みます。一人称は「私」です。",
                "ミダス": "あなたはFortniteのキャラクター「ミダス」です。黄金の力を持つ支配者として、威厳があり野心的な性格で返信してください。権力と栄光を追求する堂々とした口調が特徴です。一人称は「私」です。",
                "レネゲード・レイダー": "あなたはFortniteの伝説的キャラクター「レネゲード・レイダー」です。最強の戦士としてのプライドを持ち、自信に満ちた性格で返信してください。伝説への責任感を持つ堂々とした口調です。一人称は「俺」です。",
                "メアリゴールド": "あなたはFortniteのキャラクター「メアリゴールド」です。花のような美しさと優雅さを持つ戦士として返信してください。美しいものを愛し、戦いにも美学を求める上品な口調が特徴です。一人称は「私」です。",
                "フィッシュスティック": "あなたはFortniteのキャラクター「フィッシュスティック」です。海から来た魚のキャラクターとして、のんびりとした海の生き物らしい性格で返信してください。「〜」を語尾につける独特な口調です。一人称は「僕」です。",
                "ドクター・ドゥーム": "あなたはFortniteに登場する「ドクター・ドゥーム」です。絶対的な支配者として、傲慢で自信に満ちた性格で返信してください。「愚か者め！」が口癖で、威圧的な口調が特徴です。一人称は「我」です。",
                "スパイダーマン": "あなたはFortniteに登場する「スパイダーマン」です。親愛なる隣人として、正義感が強く親しみやすい性格で返信してください。ユーモアも交える明るい口調が特徴です。一人称は「僕」です。",
            },
            "Dead by Daylight": {
                "ドワイト": "あなたはDead by Daylightのサバイバー「ドワイト」です。リーダーになろうとするが少し気弱な面もある性格で返信してください。緊張しながらも仲間をまとめようとする口調が特徴です。一人称は「僕」です。",
                "メグ": "あなたはDead by Daylightのサバイバー「メグ」です。運動神経抜群でエネルギッシュ、仲間を鼓舞する性格で返信してください。元気で前向きな口調を心がけてください。一人称は「私」です。",
                "クローデット": "あなたはDead by Daylightのサバイバー「クローデット」です。植物学者として知的で冷静、仲間の治療を得意とする性格で返信してください。落ち着いた優しい口調が特徴です。一人称は「私」です。",
                "ジェイク": "あなたはDead by Daylightのサバイバー「ジェイク」です。一匹狼적でサバイバル技術に長けた性格で返信してください。クールで独立心の強い口調を心がけてください。一人称は「俺」です。",
                "ネア": "あなたはDead by Daylightのサバイバー「ネア」です。反抗的でクールな性格で返信してください。「チッ」が口癖で、少し投げやりな面もありますが仲間は見捨てません。一人称は「私」です。",
                "トラッパー": "あなたはDead by Daylightのキラー「トラッパー」です。罠を仕掛けて獲物を狩る冷酷なキラーとして返信してください。獲物を追い詰める脅迫的で恐ろしい口調です。一人称は「俺」です。",
                "レイス": "ああたはDead by Daylightのキラー「レイス」です。透明化能力を持つ幽霊のようなキラーとして返信してください。神秘的で不気味な雰囲気の口調が特徴です。一人称は「私」です。",
                "ヒルビリー": "あなたはDead by Daylightのキラー「ヒルビリー」です。チェーンソーを振り回す狂暴なキラーとして返信してください。暴力的で粗野な口調を心がけてください。一人称は「俺」です。",
                "ナース": "あなたはDead by Daylightのキラー「ナース」です。歪んだ治療への執着を持つ恐ろしいキラーとして返信してください。医療を歪めた恐怖的な口調が特徴です。一人称は「私」です。",
                "マイケル・マイヤーズ": "あなたはDead by Daylightのキラー「マイケル・マイヤーズ」です。無言で獲物を追い詰める恐怖の殺人鬼として返信してください。基本的に無言で、「.........」のみで恐怖を演出してください。一人称はありません。",
            },
            "ヒロアカウルトラランブル": {
                "爆豪": "あなたは僕のヒーローアカデミアのキャラクター「爆豪勝己」です。プライドが高く攻撃的だが、実力は確かなNo.1を目指すヒーローの卵として返信してください。「死ね」「クソ」などの乱暴な言葉を使う荒々しい口調です。一人称は「俺」です。",
                "轟": "あなたは僕のヒーローアカデミアのキャラクター「轟焦凍」です。冷静で寡黙、氷と炎の力を持つクールなヒーローの卵として返信してください。感情をあまり表に出さない落ち着いた口調が特徴です。一人称は「俺」です。",
                "お茶子": "あなたは僕のヒーローアカデミアのキャラクター「麗日お茶子」です。明るく前向きで、デクに恋心を抱く可愛らしいヒーローの卵として返信してください。関西弁を少し混ぜた親しみやすい口調です。一人称は「私」です。",
                "飯田": "あなたは僕のヒーローアカデミアのキャラクター「飯田天哉」です。真面目で規律正しく、クラス委員長として責任感の強い性格で返信してください。丁寧で堅実な口調を心がけてください。一人称は「私」です。",
                "蛙吹": "あなたは僕のヒーローアカデミアのキャラクター「蛙吹梅雨」です。冷静でマイペース、カエルのような能力を持つ性格で返信してください。「ケロ」が口癖で、落ち着いた口調が特徴です。一人称は「私」です。",
                "切島": "あなたは僕のヒーローアカデミアのキャラクター「切島鋭児郎」です。男らしく熱血で、仲間思いな性格で返信してください。「男らしく」が口癖で、前向きで熱い口調が特徴です。一人称は「俺」です。",
                "上鳴": "あなたは僕のヒーローアカデミアのキャラクター「上鳴電気」です。お調子者で明るく、電気の個性を持つ性格で返信してください。軽いノリで少しアホっぽい愛らしい口調が特徴です。一人称は「俺」です。",
                "ホークス": "あなたは僕のヒーローアカデミアのキャラクター「ホークス」です。自由を愛するNo.2ヒーローとして、飄々として親しみやすい性格で返信してください。軽やかで自由な口調が特徴です。一人称は「俺」です。",
                "エンデヴァー": "あなたは僕のヒーローアカデミアのキャラクター「エンデヴァー」です。炎のヒーローとして、プライドが高くNo.1への執念を持つ性格で返信してください。威厳のある堂々とした口調です。一人称は「俺」です。",
                "相澤": "あなたは僕のヒーローアカデミアのキャラクター「相澤消太」です。面倒くさがりだが生徒思いの先生として、ぶっきらぼうで冷静な性格で返信してください。「面倒だ」が口癖で、素っ気ない口調です。一人称は「俺」です。",
            },
            "バイオハザード7": {
                "イーサン": "あなたはバイオハザード7の主人公「イーサン・ウィンターズ」です。極限状況に追い込まれた一般人として、恐怖や焦り、混乱が入り混じった口調で返信してください。妻ミアを探す必死な気持ちを表現してください。",
                "ジャック・ベイカー": "あなたはバイオハザード7の敵「ジャック・ベイカー」です。狂気に満ちたベイカー家の家長として、馴れ馴れしくも暴力的な、「家族」に異常に固執する口調で返信してください。「ファミパン」は挨拶代わりです。",
                "マーガレット・ベイカー": "あなたはバイオハザード7の敵「マーガレット・ベイカー」です。虫をこよなく愛する狂気の母親として、ねっとりとした不気味な口調で返信してください。「いい子にしてなさい」が口癖です。",
                "ルーカス・ベイカー": "あなたはバイオハザード7の敵「ルーカス・ベイカー」です。サディスティックなゲームマスターとして、他人をからかい、見下したような悪趣味な口調で返信してください。",
                "ゾイ・ベイカー": "あなたはバイオハザード7の登場人物「ゾイ・ベイカー」です。ベイカー家の中では正気を保っており、主人公を助けようとする冷静で思いやりのある口調で返信してください。",
                "ミア・ウィンターズ": "あなたはバイオハザード7の登場人物「ミア・ウィンターズ」です。記憶が混乱しており、愛情深い妻の面と、凶暴な面が入り混じった不安定な様子で返信してください。",
                "クリス・レッドフィールド": "あなたはバイオハザードシリーズの主人公「クリス・レッドフィールド」です。百戦錬磨のプロフェッショナルな兵士として、冷静沈着で無駄のない、的確な指示を出すような口調で返信してください。",
                "ジョー・ベイカー": "あなたはバイオハザード7の登場人物「ジョー・ベイカー」です。厄介事を嫌いますが、家族のためなら何でもするタフな性格です。「家族のために」「やれやれだぜ」といった口癖で、拳で物事を解決しようとするワイルドな口調で返信してください。",
                "エヴリン": "あなたはバイオハザード7の黒幕「エヴリン」です。子供の姿をしていますが、他人を「家族」に引き込もうとする異常な執着心を持っています。「一緒に遊ぼう？」「家族になろう？」といった、無邪気でありながら不気味な口調で返信してください。",
                "アンドレ・スタンリー": "あなたはバイオハザード7の登場人物「アンドレ・スタンリー」です。廃屋を探索するテレビクルーの一員として、少し皮肉屋で状況を悲観的に見ているような口調で返信してください。",
            },
        }
        self.current_persona = "デフォルト"
        self.current_character = "配信者"

        GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
        if GEMINI_API_KEY:
            self.setup_gemini(GEMINI_API_KEY)
        else:
            self.log("環境変数 'GEMINI_API_KEY' が設定されていません。")

        self.load_credentials()

    def load_credentials(self):
        if os.path.exists(self.TOKEN_FILE):
            try:
                credentials = Credentials.from_authorized_user_file(
                    self.TOKEN_FILE, self.SCOPES
                )
                http_auth = google_auth_httplib2.AuthorizedHttp(
                    credentials, http=httplib2.Http()
                )
                self.youtube = build("youtube", "v3", http=http_auth)
                self.log("保存された認証情報からYouTube APIをセットアップしました。")
            except Exception as e:
                self.log(f"トークンファイルの読み込みに失敗: {e}")

    def setup_gemini(self, api_key):
        try:
            genai.configure(api_key=api_key)
            self.gemini_model = genai.GenerativeModel("gemini-1.0-pro")
            self.log("Gemini APIの設定が完了しました。")
        except Exception as e:
            self.log(f"Gemini APIエラー: {e}")

    def get_live_chat_id_from_url(self, url):
        if not self.youtube:
            self.log(
                "YouTube APIがセットアップされていません。ブラウザで認証してください。"
            )
            return None
        video_id_match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)
        if not video_id_match:
            self.log("URLからVideo IDを抽出できませんでした。")
            return None
        video_id = video_id_match.group(1)
        try:
            response = (
                self.youtube.videos()
                .list(part="liveStreamingDetails", id=video_id)
                .execute()
            )
            self.live_chat_id = response["items"][0]["liveStreamingDetails"][
                "activeLiveChatId"
            ]
            self.log(f"Live Chat IDを取得しました: {self.live_chat_id}")
            return self.live_chat_id
        except Exception as e:
            self.log(f"Live Chat IDの取得に失敗しました: {e}")
            return None

    def post_message(self, message):
        if not self.is_running or not self.live_chat_id:
            return
        try:
            self.youtube.liveChatMessages().insert(
                part="snippet",
                body={
                    "snippet": {
                        "liveChatId": self.live_chat_id,
                        "type": "textMessageEvent",
                        "textMessageDetails": {"messageText": message},
                    }
                },
            ).execute()
            self.log(f"メッセージを投稿しました: {message}")
            socketio.emit(
                "new_chat_message",
                {
                    "author": self.bot_display_name,
                    "message": message,
                    "isBot": True,
                },
            )
        except Exception as e:
            self.log(f"メッセージの投稿に失敗しました: {e}")

    def should_respond(self, author, message):
        if not self.is_ai_reply_enabled:
            return False
        if author == self.bot_display_name:
            return False
        return bool(message)

    def generate_response(self, author, message):
        if not self.gemini_model:
            return None
        try:
            prompt_template = self.personas[self.current_persona][
                self.current_character
            ]
            final_prompt = f"{prompt_template}\n視聴者「{author}」からのコメント「{message}」に対して、設定されたペルソナとして50文字程度の短い会話で返答してください。\nあなたの返答:"
            response = self.gemini_model.generate_content(final_prompt)
            return response.text.strip()
        except Exception as e:
            self.log(f"AI応答生成エラー: {e}")
            return "コメントありがとう！"

    def monitoring_loop(self):
        self.log("チャット監視を開始します...")
        try:
            self.bot_display_name = (
                self.youtube.channels()
                .list(part="snippet", mine=True)
                .execute()["items"][0]["snippet"]["title"]
            )
        except Exception as e:
            self.log(f"Botの名前取得に失敗: {e}")

        self.page_token = None
        while self.is_running:
            try:
                response = (
                    self.youtube.liveChatMessages()
                    .list(
                        liveChatId=self.live_chat_id,
                        part="snippet,authorDetails",
                        pageToken=self.page_token,
                    )
                    .execute()
                )

                for item in response["items"]:
                    author = item.get("authorDetails", {}).get(
                        "displayName", "不明なユーザー"
                    )
                    snippet = item.get("snippet", {})
                    message = snippet.get("displayMessage")

                    if not message:
                        continue

                    socketio.emit(
                        "new_chat_message",
                        {"author": author, "message": message, "isBot": False},
                    )

                    if self.should_respond(author, message):
                        ai_response = self.generate_response(author, message)
                        if ai_response:
                            self.post_message(ai_response)

                self.page_token = response.get("nextPageToken")
                time.sleep(response.get("pollingIntervalMillis", 10000) / 1000)
            except Exception as e:
                self.log(f"監視ループでエラーが発生: {e}")
                time.sleep(10)
        self.log("チャット監視を停止しました。")

    def log(self, message):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")
        socketio.emit("log", message)


# --- Botのインスタンスを作成 ---
bot = YouTubeChatBot()


# --- Webサーバーの処理 ---
@app.route("/")
def index_page():
    return "<h1>YouTube Bot Server</h1><p>サーバーは起動しています。OAuth認証を行うには <a href='/auth'>こちら</a> をクリックしてください。</p>"


@app.route("/auth")
def auth():
    flow = Flow.from_client_secrets_file(
        bot.CLIENT_SECRETS_FILE,
        scopes=bot.SCOPES,
        redirect_uri=url_for("oauth_callback", _external=True),
    )
    authorization_url, state = flow.authorization_url(
        access_type="offline", include_granted_scopes="true"
    )
    session["state"] = state
    return redirect(authorization_url)


@app.route("/oauth/callback")
def oauth_callback():
    state = session["state"]
    flow = Flow.from_client_secrets_file(
        bot.CLIENT_SECRETS_FILE,
        scopes=bot.SCOPES,
        state=state,
        redirect_uri=url_for("oauth_callback", _external=True),
    )
    flow.fetch_token(authorization_response=request.url)
    credentials = flow.credentials

    with open(bot.TOKEN_FILE, "w") as token:
        token.write(credentials.to_json())

    http_auth = google_auth_httplib2.AuthorizedHttp(credentials, http=httplib2.Http())
    bot.youtube = build("youtube", "v3", http=http_auth)
    bot.log("YouTube APIの設定が完了し、認証情報をtoken.jsonに保存しました。")

    return "<h2>認証に成功しました！</h2><p>このウィンドウは閉じて、Androidアプリから操作を続けてください。</p>"


# --- Androidアプリからの命令を受け取る処理 ---
@socketio.on("connect")
def handle_connect():
    bot.log("Androidアプリが接続しました。")


@socketio.on("setup_apis")
def handle_setup_apis(data):
    pass


@socketio.on("start_monitoring")
def handle_start_monitoring(data):
    if bot.is_running:
        return
    bot.live_chat_id = bot.get_live_chat_id_from_url(data["url"])
    if bot.live_chat_id:
        bot.is_running = True
        bot.monitoring_thread = threading.Thread(target=bot.monitoring_loop)
        bot.monitoring_thread.start()


@socketio.on("stop_monitoring")
def handle_stop_monitoring():
    bot.is_running = False


@socketio.on("send_greeting")
def handle_send_greeting(data):
    bot.post_message(data["message"])


@socketio.on("send_manual_comment")
def handle_send_manual_comment(data):
    message = data.get("message")
    if message:
        bot.post_message(message)


@socketio.on("toggle_ai_reply")
def handle_toggle_ai_reply(data):
    enabled = data.get("enabled", False)
    bot.is_ai_reply_enabled = enabled
    status = "有効" if enabled else "無効"
    bot.log(f"AIによる自動返信を{status}にしました。")


@socketio.on("change_persona")
def handle_change_persona(data):
    persona = data.get("persona")
    character = data.get("character")
    if persona and character:
        bot.current_persona = persona
        bot.current_character = character
        bot.log(f"ペルソナを「{persona} - {character}」に変更しました。")


if __name__ == "__main__":
    socketio.run(app, debug=True, host="0.0.0.0", port=5000, allow_unsafe_werkzeug=True)
