import tkinter as tk
from tkinter import filedialog, messagebox
import azure.cognitiveservices.speech as speechsdk
import requests
import os
import json
import time

def load_settings():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    settings_path = os.path.join(script_dir, 'setting.json')
    try:
        with open(settings_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        messagebox.showerror("エラー", "setting.jsonファイルが見つかりません。")
        return None
    except json.JSONDecodeError:
        messagebox.showerror("エラー", "setting.jsonファイルの形式が正しくありません。")
        return None

settings = load_settings()
if not settings:
    exit()

def transcribe_audio(audio_file):
    speech_config = speechsdk.SpeechConfig(subscription=settings['speech_key'], region=settings['speech_region'])
    speech_config.speech_recognition_language = "ja-JP"

    audio_config = speechsdk.audio.AudioConfig(filename=audio_file)
    
    # 連続認識のためのオブジェクトを作成
    speech_recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)

    done = False
    all_results = []

    def stop_cb(evt):
        """認識停止のコールバック"""
        print('CLOSING on {}'.format(evt))
        nonlocal done
        done = True

    # 認識結果のコールバック
    def recognized_cb(evt):
        nonlocal all_results
        all_results.append(evt.result.text)

    # イベントハンドラを接続
    speech_recognizer.recognized.connect(recognized_cb)
    speech_recognizer.session_stopped.connect(stop_cb)
    speech_recognizer.canceled.connect(stop_cb)

    # 連続認識を開始
    speech_recognizer.start_continuous_recognition()

    while not done:
        time.sleep(.5)

    speech_recognizer.stop_continuous_recognition()

    return " ".join(all_results)

def generate_article(transcript):
    prompt = f"以下のポッドキャストの文字起こしをパソコン雑誌風の記事に変換してください。章立てを行い、マークダウン形式で出力してください：\n\n{transcript}"

    headers = {
        "Content-Type": "application/json",
        "api-key": settings['openai_api_key']
    }

    payload = {
        "messages": [
            {"role": "system", "content": "あなたはプロのライターです。パソコン雑誌風の記事を書くのが得意です。"},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 1000
    }

    response = requests.post(f"{settings['openai_endpoint']}/openai/deployments/{settings['openai_deployment']}/chat/completions?api-version=2023-05-15", headers=headers, json=payload)
    return response.json()["choices"][0]["message"]["content"]

def process_audio():
    input_file = input_path.get()
    output_file = output_path.get()

    if not input_file or not output_file:
        messagebox.showerror("エラー", "入力ファイルと出力ファイルを指定してください。")
        return

    # 入力ファイルの拡張子チェック
    file_extension = os.path.splitext(input_file)[1].lower()
    if file_extension not in ['.mp3', '.wav']:
        messagebox.showerror("エラー", "入力ファイルはMP3またはWAV形式である必要があります。")
        return

    try:
        # 文字起こし
        transcript = transcribe_audio(input_file)
        
        # 文字起こしテキストを保存
        output_dir = os.path.dirname(output_file)
        transcription_file = os.path.join(output_dir, "文字起こし.txt")
        with open(transcription_file, "w", encoding="utf-8") as f:
            f.write(transcript)
        
        # 記事生成
        article = generate_article(transcript)

        # 生成された記事を保存
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(article)

        messagebox.showinfo("成功", f"処理が完了しました。\n文字起こし: {transcription_file}\n生成記事: {output_file}")
    except Exception as e:
        messagebox.showerror("エラー", f"処理中にエラーが発生しました: {str(e)}")

# GUIの作成
root = tk.Tk()
root.title("ポッドキャスト文字起こしと記事生成")

frame = tk.Frame(root, padx=10, pady=10)
frame.pack(padx=10, pady=10)

tk.Label(frame, text="入力音声ファイル (MP3 または WAV):").grid(row=0, column=0, sticky="w")
input_path = tk.Entry(frame, width=50)
input_path.grid(row=0, column=1, padx=5, pady=5)
tk.Button(frame, text="参照", command=lambda: input_path.insert(0, filedialog.askopenfilename(filetypes=[("音声ファイル", "*.mp3 *.wav")]))).grid(row=0, column=2)

tk.Label(frame, text="出力テキストファイル:").grid(row=1, column=0, sticky="w")
output_path = tk.Entry(frame, width=50)
output_path.grid(row=1, column=1, padx=5, pady=5)
tk.Button(frame, text="参照", command=lambda: output_path.insert(0, filedialog.asksaveasfilename(defaultextension=".md", filetypes=[("Markdown files", "*.md")]))).grid(row=1, column=2)

tk.Button(frame, text="実行", command=process_audio).grid(row=2, column=1, pady=10)

root.mainloop()