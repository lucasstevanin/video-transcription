import os
import subprocess
import shutil
import time
import threading
from dotenv import load_dotenv
from moviepy.editor import VideoFileClip
from groq import Groq
from pydub import AudioSegment
from concurrent.futures import ThreadPoolExecutor, as_completed
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import sys
import itertools
import tempfile

# Função para obter o caminho correto do ffmpeg.exe
# def get_ffmpeg_path():
#     if getattr(sys, "frozen", False):
#         return os.path.join(sys._MEIPASS, "ffmpeg", "ffmpeg.exe")
#     else:
#         return os.path.abspath("ffmpeg/ffmpeg.exe")


def get_ffmpeg_path():
    if getattr(sys, "frozen", False):  # Verifica se está rodando como executável
        return os.path.join(sys._MEIPASS, "ffmpeg", "ffmpeg.exe")
    else:  # Caso contrário, use o caminho normal
        return os.path.abspath("ffmpeg/ffmpeg.exe")


# Definir o caminho do ffmpeg
FFMPEG_BINARY_PATH = get_ffmpeg_path()

# Inicialize o MoviePy para usar o caminho especificado do ffmpeg
VideoFileClip.ffmpeg_binary = FFMPEG_BINARY_PATH

# Carregar as variáveis de ambiente do arquivo .env
load_dotenv()

# Inicialize o cliente Groq com sua chave de API
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))


# Função para limitar requisições a 18 por minuto com um delay adicional de 3 segundos
def rate_limiter(
    last_request_time,
    requests_made,
    max_requests_per_minute=18,
    wait_time=60,
    additional_delay=3,
):
    current_time = time.time()
    if requests_made >= max_requests_per_minute:
        time_since_last_request = current_time - last_request_time
        if time_since_last_request < wait_time:
            time_to_wait = wait_time - time_since_last_request
            print(
                f"Atingido o limite de requisições, aguardando {int(time_to_wait)} segundos..."
            )
            time.sleep(time_to_wait)
        print(
            f"Aguardando {additional_delay} segundos adicionais para evitar limite..."
        )
        time.sleep(additional_delay)
        last_request_time = time.time()
        requests_made = 0
    return last_request_time, requests_made + 1


def criar_pasta_temporaria():
    pasta_temp = os.path.abspath("temp_files")
    if not os.path.exists(pasta_temp):
        os.makedirs(pasta_temp)
    return pasta_temp


def limpar_pasta_temporaria(pasta_temp):
    try:
        shutil.rmtree(pasta_temp)
        print(f"Pasta temporária '{pasta_temp}' removida.")
    except Exception as e:
        print(f"Erro ao limpar a pasta temporária: {e}")


def verificar_extensao(video_path):
    _, extensao = os.path.splitext(video_path)
    return extensao.lower()


def extrair_audio_com_ffmpeg(video_path, audio_output):
    try:
        if not os.path.exists(video_path):
            raise FileNotFoundError(
                f"O arquivo de vídeo {video_path} não foi encontrado."
            )
        comando_ffmpeg = [
            FFMPEG_BINARY_PATH,
            "-i",
            video_path,
            "-q:a",
            "0",
            "-map",
            "a",
            audio_output,
        ]
        subprocess.run(comando_ffmpeg, check=True)
        print(f"Áudio extraído e salvo como {audio_output}")
    except subprocess.CalledProcessError as e:
        print(f"Erro ao extrair o áudio com ffmpeg: {e}")


def dividir_audio_em_partes(audio_path, pasta_temp, duracao_parte_ms=60 * 1000):
    audio = AudioSegment.from_wav(audio_path)
    partes = []
    for i in range(0, len(audio), duracao_parte_ms):
        parte_audio = audio[i : i + duracao_parte_ms]
        parte_caminho = os.path.join(pasta_temp, f"parte_{i // duracao_parte_ms}.wav")
        parte_audio.export(parte_caminho, format="wav")
        partes.append((i // duracao_parte_ms, parte_caminho))
    return partes


def transcrever_audio(audio_path, last_request_time, requests_made):
    try:
        last_request_time, requests_made = rate_limiter(
            last_request_time, requests_made
        )
        print(f"Iniciando a transcrição do áudio {audio_path}...")
        with open(audio_path, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                file=audio_file,
                model="whisper-large-v3",
                response_format="json",
                language="pt",
            )
        return transcription.text, last_request_time, requests_made
    except Exception as e:
        print(f"Erro na transcrição: {e}")
        return "", last_request_time, requests_made


def salvar_transcricao(texto):
    try:
        temp_file = tempfile.NamedTemporaryFile(
            delete=False, suffix=".txt", mode="w", encoding="utf-8"
        )
        temp_file.write(texto)
        temp_file.close()
        print(f"Transcrição salva em {temp_file.name}")
        return temp_file.name
    except Exception as e:
        print(f"Erro ao salvar a transcrição: {e}")
        return None


def transcrever_partes_com_limite(partes_audio, progress_bar):
    transcricoes = []
    last_request_time = time.time()
    requests_made = 0
    partes_por_lote = list(grouper(partes_audio, 18))

    for index, lote_partes in enumerate(partes_por_lote):
        futures = []
        with ThreadPoolExecutor() as executor:
            for parte in lote_partes:
                futures.append(
                    executor.submit(
                        transcrever_audio, parte[1], last_request_time, requests_made
                    )
                )

            for future, parte in zip(futures, lote_partes):
                indice = parte[0]
                try:
                    transcricao, last_request_time, requests_made = future.result()
                    transcricoes.append((indice, transcricao))
                    progress_bar.step(1)
                    progress_bar.update_idletasks()
                except Exception as exc:
                    print(f"Erro ao transcrever a parte {indice}: {exc}")

        requests_made += len(lote_partes)

        if index < len(partes_por_lote) - 1:
            print("Aguardando 1 minuto antes de enviar o próximo lote...")
            time.sleep(60)

        requests_made = 0

    transcricoes_ordenadas = sorted(transcricoes, key=lambda x: x[0])
    return [transcricao for _, transcricao in transcricoes_ordenadas]


def grouper(iterable, n):
    it = iter(iterable)
    return iter(lambda: list(itertools.islice(it, n)), [])


def transcrever_video_completo(video_path, progress_bar, time_label, timer_event):
    pasta_temp = criar_pasta_temporaria()
    audio_output = os.path.join(pasta_temp, "audio.wav")
    extensao = verificar_extensao(video_path)
    if extensao in [".mkv", ".mp4"]:
        extrair_audio_com_ffmpeg(video_path, audio_output)
    else:
        print(f"Formato {extensao} não suportado.")
        return
    partes_audio = dividir_audio_em_partes(audio_output, pasta_temp)
    progress_bar["maximum"] = len(partes_audio)

    transcricoes = transcrever_partes_com_limite(partes_audio, progress_bar)
    transcricao_completa = "\n".join(transcricoes)

    temp_file_path = salvar_transcricao(transcricao_completa)
    limpar_pasta_temporaria(pasta_temp)

    if temp_file_path:
        messagebox.showinfo("Sucesso", "Transcrição concluída!")
        timer_event.set()
        return temp_file_path
    else:
        return None


class TranscriptionApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Transcrição de Vídeo")
        self.root.geometry("600x400")
        self.video_path = None
        self.output_txt_path = None
        self.timer_event = threading.Event()

        self.upload_button = tk.Button(
            root, text="Carregar Vídeo", command=self.upload_video
        )
        self.upload_button.pack(pady=10)

        self.process_button = tk.Button(
            root,
            text="Processar Vídeo",
            command=self.process_video_threaded,
            state=tk.DISABLED,
        )
        self.process_button.pack(pady=10)

        self.progress_bar = ttk.Progressbar(
            root, orient="horizontal", length=400, mode="determinate"
        )
        self.progress_bar.pack(pady=10)

        self.time_label = tk.Label(root, text="Tempo decorrido: 0:00")
        self.time_label.pack(pady=5)

        self.download_button = tk.Button(
            root,
            text="Baixar Transcrição",
            command=self.download_file,
            state=tk.DISABLED,
        )
        self.download_button.pack(pady=10)

    def reset_timer(self):
        self.time_label.config(text="Tempo decorrido: 0:00")

    def upload_video(self):
        self.video_path = filedialog.askopenfilename(
            title="Selecione um vídeo", filetypes=[("Video Files", "*.mkv *.mp4")]
        )
        if self.video_path:
            messagebox.showinfo(
                "Arquivo Selecionado", f"Você selecionou o arquivo: {self.video_path}"
            )
            self.process_button.config(state=tk.NORMAL)

    def update_timer(self):
        start_time = time.time()
        while not self.timer_event.is_set():
            elapsed_time = time.time() - start_time
            minutes = int(elapsed_time // 60)
            seconds = int(elapsed_time % 60)
            self.time_label.config(text=f"Tempo decorrido: {minutes}:{seconds:02d}")
            time.sleep(1)

    def process_video_threaded(self):
        if self.video_path:
            # Zera o temporizador e inicia o processo
            self.timer_event.clear()
            self.process_button.config(state=tk.DISABLED)
            self.output_txt_path = None

            # Iniciar o processo de vídeo em uma thread separada
            threading.Thread(target=self.process_video).start()

            # Iniciar o timer na mesma thread do processamento
            threading.Thread(target=self.update_timer).start()
        else:
            messagebox.showwarning("Aviso", "Por favor, carregue um vídeo primeiro.")

    def process_video(self):
        # Iniciar o processamento do vídeo
        self.output_txt_path = transcrever_video_completo(
            self.video_path, self.progress_bar, self.time_label, self.timer_event
        )

        # Habilitar o botão de download quando a transcrição for concluída
        self.download_button.config(state=tk.NORMAL)

        # Parar o temporizador e resetar o tempo após a conclusão
        self.timer_event.set()  # Sinaliza para parar o timer
        self.reset_timer()  # Reseta o rótulo do timer para 0:00

    def download_file(self):
        if self.output_txt_path:
            save_path = filedialog.asksaveasfilename(
                defaultextension=".txt", filetypes=[("Text Files", "*.txt")]
            )
            if save_path:
                shutil.copy(self.output_txt_path, save_path)
                messagebox.showinfo(
                    "Sucesso", f"Arquivo transcrição salvo em: {save_path}"
                )
                os.remove(self.output_txt_path)
                self.download_button.config(state=tk.DISABLED)
                self.process_button.config(state=tk.DISABLED)
                self.reset_timer()  # Zera o timer após o download
            else:
                messagebox.showwarning(
                    "Aviso", "Nenhum local selecionado para salvar o arquivo."
                )
        else:
            messagebox.showwarning(
                "Aviso", "Nenhuma transcrição disponível para download."
            )


if __name__ == "__main__":
    root = tk.Tk()
    app = TranscriptionApp(root)
    root.mainloop()
