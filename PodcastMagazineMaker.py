import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import azure.cognitiveservices.speech as speechsdk
import requests
import os
import json
import time
import threading

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

def transcribe_audio(audio_file, progress_var, status_label):
    speech_config = speechsdk.SpeechConfig(subscription=settings['speech_key'], region=settings['speech_region'])
    speech_config.speech_recognition_language = "ja-JP"

    audio_config = speechsdk.audio.AudioConfig(filename=audio_file)
    
    speech_recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)

    done = False
    all_results = []

    def stop_cb(evt):
        print('CLOSING on {}'.format(evt))
        nonlocal done
        done = True

    def recognized_cb(evt):
        nonlocal all_results
        all_results.append(evt.result.text)
        progress_var.set(len(all_results))  # 進捗を更新
        status_label.config(text=f"文字起こし中... ({len(all_results)}文認識)")
        root.update_idletasks()

    speech_recognizer.recognized.connect(recognized_cb)
    speech_recognizer.session_stopped.connect(stop_cb)
    speech_recognizer.canceled.connect(stop_cb)

    speech_recognizer.start_continuous_recognition()

    while not done:
        time.sleep(.5)

    speech_recognizer.stop_continuous_recognition()

    return " ".join(all_results)

def generate_article(transcript, progress_var, status_label):
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

    status_label.config(text="記事生成中...")
    root.update_idletasks()

    response = requests.post(f"{settings['openai_endpoint']}/openai/deployments/{settings['openai_deployment']}/chat/completions?api-version=2023-05-15", headers=headers, json=payload)
    
    progress_var.set(100)  # 記事生成完了
    return response.json()["choices"][0]["message"]["content"]

def process_audio():
    input_file = input_path.get()
    output_file = output_path.get()

    if not input_file or not output_file:
        messagebox.showerror("エラー", "入力ファイルと出力ファイルを指定してください。")
        return

    file_extension = os.path.splitext(input_file)[1].lower()
    if file_extension not in ['.mp3', '.wav']:
        messagebox.showerror("エラー", "入力ファイルはMP3またはWAV形式である必要があります。")
        return

    progress_window = tk.Toplevel(root)
    progress_window.title("処理中")
    progress_window.geometry("300x100")

    progress_var = tk.DoubleVar()
    progress_bar = ttk.Progressbar(progress_window, variable=progress_var, maximum=100)
    progress_bar.pack(pady=10, padx=10, fill=tk.X)

    status_label = tk.Label(progress_window, text="処理開始...")
    status_label.pack(pady=5)

    def process_thread():
        try:
            status_label.config(text="文字起こし中...")
            transcript = transcribe_audio(input_file, progress_var, status_label)
            
            output_dir = os.path.dirname(output_file)
            transcription_file = os.path.join(output_dir, "文字起こし.txt")
            with open(transcription_file, "w", encoding="utf-8") as f:
                f.write(transcript)
            
            progress_var.set(50)  # 文字起こし完了

            article = generate_article(transcript, progress_var, status_label)

            with open(output_file, "w", encoding="utf-8") as f:
                f.write(article)

            progress_window.destroy()
            messagebox.showinfo("成功", f"処理が完了しました。\n文字起こし: {transcription_file}\n生成記事: {output_file}")
        except Exception as e:
            progress_window.destroy()
            messagebox.showerror("エラー", f"処理中にエラーが発生しました: {str(e)}")

    threading.Thread(target=process_thread, daemon=True).start()

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
