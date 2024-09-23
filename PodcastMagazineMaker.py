import tkinter as tk
from tkinter import filedialog, messagebox, ttk, scrolledtext
import azure.cognitiveservices.speech as speechsdk
import requests
import os
import json
import time
import threading
from datetime import datetime, timedelta

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

def load_work_info():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    work_path = os.path.join(script_dir, 'work.json')
    try:
        with open(work_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {"input_file": "", "input_type": "audio", "output_file": ""}
    except json.JSONDecodeError:
        messagebox.showwarning("警告", "work.jsonファイルの形式が正しくありません。デフォルト値を使用します。")
        return {"input_file": "", "input_type": "audio", "output_file": ""}

def save_work_info(input_file, input_type, output_file):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    work_path = os.path.join(script_dir, 'work.json')
    work_info = {
        "input_file": input_file,
        "input_type": input_type,
        "output_file": output_file
    }
    with open(work_path, 'w') as f:
        json.dump(work_info, f, indent=2)

def transcribe_audio(audio_file, progress_var, status_label, transcription_text):
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
        result = evt.result.text
        all_results.append(result)
        progress_var.set(len(all_results))
        status_label.config(text=f"文字起こし中... ({len(all_results)}文認識)")
        transcription_text.insert(tk.END, result + "\n")
        transcription_text.see(tk.END)
        root.update_idletasks()

    def canceled_cb(evt):
        print('CANCELED: {}'.format(evt))
        if evt.reason == speechsdk.CancellationReason.Error:
            print('CANCELED: Error details: {}'.format(evt.error_details))
            raise Exception(f"音声認識エラー: {evt.error_details}")

    speech_recognizer.recognized.connect(recognized_cb)
    speech_recognizer.session_stopped.connect(stop_cb)
    speech_recognizer.canceled.connect(canceled_cb)

    speech_recognizer.start_continuous_recognition()

    try:
        while not done:
            time.sleep(.5)
    finally:
        speech_recognizer.stop_continuous_recognition()

    if not all_results:
        raise Exception("音声認識結果が得られませんでした。")

    return " ".join(all_results)

def generate_article(transcript, progress_var, status_label):
    max_tokens_per_request = 1000
    prompt = f"以下のポッドキャストの文字起こしをパソコン雑誌風の記事に変換してください。マークダウン形式で出力してください：\n\n{transcript}"

    headers = {
        "Content-Type": "application/json",
        "api-key": settings['openai_api_key']
    }

    payload = {
        "messages": [
            {"role": "system", "content": "あなたはプロのライターです。パソコン雑誌風の記事を書くのが得意です。与えられた文字起こしを元に、全体の流れを考慮しながら記事を書いてください。"},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": max_tokens_per_request
    }

    status_label.config(text="記事生成中...")
    root.update_idletasks()

    response = requests.post(f"{settings['openai_endpoint']}/openai/deployments/{settings['openai_deployment']}/chat/completions?api-version=2023-05-15", headers=headers, json=payload)
    
    if response.status_code != 200:
        raise Exception(f"OpenAI API エラー: {response.status_code} - {response.text}")

    article = response.json()["choices"][0]["message"]["content"]
    # マークダウンのコードブロック（```markdown）を削除
    article = article.replace("```markdown", "").replace("```", "").strip()

    progress_var.set(100)

    return article.strip()

def process_audio():
    input_file = input_path.get()
    input_type = input_type_var.get()
    output_file = output_path.get()

    if not input_file or not output_file:
        messagebox.showerror("エラー", "入力ファイルと出力ファイルを指定してください。")
        return

    output_dir = os.path.dirname(output_file)
    transcription_file = os.path.join(output_dir, "文字起こし.txt")

    # 出力ファイルが既に存在する場合は削除する
    if os.path.exists(output_file):
        try:
            os.remove(output_file)
        except OSError as e:
            messagebox.showerror("エラー", f"出力ファイル {output_file} を削除できませんでした: {e}")
            return
    if os.path.exists(transcription_file):
        try:
            os.remove(transcription_file)
        except OSError as e:
            messagebox.showerror("エラー", f"文字起こしファイル {transcription_file} を削除できませんでした: {e}")
            return

    progress_window = tk.Toplevel(root)
    progress_window.title("処理中")
    progress_window.geometry("500x400")

    progress_var = tk.DoubleVar()
    progress_bar = ttk.Progressbar(progress_window, variable=progress_var, maximum=100)
    progress_bar.pack(pady=10, padx=10, fill=tk.X)

    status_label = tk.Label(progress_window, text="処理開始...")
    status_label.pack(pady=5)

    transcription_text = scrolledtext.ScrolledText(progress_window, wrap=tk.WORD, width=60, height=20)
    transcription_text.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)

    def process_thread():
        try:
            start_time = datetime.now()

            if input_type == "audio":
                status_label.config(text="文字起こし中...")
                transcript = transcribe_audio(input_file, progress_var, status_label, transcription_text)
                
                if not transcript.strip():
                    raise Exception("文字起こし結果が空です。")

                with open(transcription_file, "w", encoding="utf-8") as f:
                    f.write(transcript)
            else:
                status_label.config(text="文字起こしファイル読み込み中...")
                with open(input_file, "r", encoding="utf-8") as f:
                    transcript = f.read().strip()

            progress_var.set(50)

            status_label.config(text="記事生成中...")
            transcription_text.insert(tk.END, "\n--- 記事生成開始 ---\n")
            article = generate_article(transcript, progress_var, status_label)

            with open(output_file, "w", encoding="utf-8") as f:
                f.write(article)

            save_work_info(input_file, input_type, output_file)

            end_time = datetime.now()
            process_duration = end_time - start_time

            transcription_text.insert(tk.END, "\n--- 処理完了 ---\n")
            transcription_text.insert(tk.END, f"\n開始時間: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
            transcription_text.insert(tk.END, f"\n終了時間: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
            transcription_text.insert(tk.END, f"\n処理時間: {str(process_duration)}")
            transcription_text.see(tk.END)

            progress_window.destroy()
            messagebox.showinfo("成功", f"処理が完了しました。\n文字起こし: {transcription_file}\n生成記事: {output_file}\n\n開始時間: {start_time.strftime('%Y-%m-%d %H:%M:%S')}\n終了時間: {end_time.strftime('%Y-%m-%d %H:%M:%S')}\n処理時間: {str(process_duration)}")
        except Exception as e:
            progress_window.destroy()
            messagebox.showerror("エラー", f"処理中にエラーが発生しました: {str(e)}")
            print(f"詳細なエラー情報: {e}")

    threading.Thread(target=process_thread, daemon=True).start()

# GUIの作成
root = tk.Tk()
root.title("ポッドキャスト文字起こしと記事生成")

frame = tk.Frame(root, padx=10, pady=10)
frame.pack(padx=10, pady=10)

tk.Label(frame, text="入力情報:").grid(row=0, column=0, sticky="w")
input_type_var = tk.StringVar(value="audio")
input_type_radio_audio = tk.Radiobutton(frame, text="音声ファイル", variable=input_type_var, value="audio")
input_type_radio_text = tk.Radiobutton(frame, text="文字起こし済みファイル", variable=input_type_var, value="text")
input_type_radio_audio.grid(row=0, column=1, sticky="w")
input_type_radio_text.grid(row=0, column=2, sticky="w")

tk.Label(frame, text="入力ファイル:").grid(row=1, column=0, sticky="w")
input_path = tk.Entry(frame, width=50)
input_path.grid(row=1, column=1, padx=5, pady=5)
tk.Button(frame, text="参照", command=lambda: input_path.delete(0, tk.END) or input_path.insert(0, filedialog.askopenfilename())).grid(row=1, column=2)

tk.Label(frame, text="出力テキストファイル:").grid(row=2, column=0, sticky="w")
output_path = tk.Entry(frame, width=50)
output_path.grid(row=2, column=1, padx=5, pady=5)
tk.Button(frame, text="参照", command=lambda: output_path.delete(0, tk.END) or output_path.insert(0, filedialog.asksaveasfilename(defaultextension=".md", filetypes=[("Markdown files", "*.md")]))).grid(row=2, column=2)

tk.Button(frame, text="実行", command=process_audio).grid(row=3, column=1, pady=10)

# work.json から前回の入力を読み込み
work_info = load_work_info()
input_path.insert(0, work_info["input_file"])
input_type_var.set(work_info["input_type"])
output_path.insert(0, work_info["output_file"])

root.mainloop()
