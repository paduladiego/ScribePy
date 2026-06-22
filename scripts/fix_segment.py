import os
import re
import sys
import time

# Adiciona o diretório raiz do projeto ao sys.path para permitir importações de módulos locais
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pydub import AudioSegment
from google import genai
from google.genai import types
from src.audio_processor import preprocess_audio

# Configura o caminho do FFmpeg automaticamente no Windows/Mac/Linux
try:
    import static_ffmpeg
    static_ffmpeg.add_paths()
except ImportError:
    pass

# Carrega as variáveis de ambiente do .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

def run_isolated_fix():
    print("=" * 60)
    print("SCRIBEPY ISOLATED FIX — RE-TRANSCRIBING CHUNK 5")
    print("=" * 60)

    # Caminhos apontando para a raiz do projeto (um nível acima de scripts/)
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    txt_path = os.path.join(project_root, "teste_transcript.txt")
    wav_path = os.path.join(project_root, "teste_clean.wav")
    m4a_path = os.path.join(project_root, "teste.m4a")
    fix_wav_path = os.path.join(project_root, "teste_resume_fix.wav")
    glossary_path = os.path.join(project_root, "glossario.txt")

    # 1. Trunca o arquivo teste_transcript.txt para 710 linhas (ponto limpo em 38:09)
    if not os.path.exists(txt_path):
        print(f"Error: {txt_path} not found.")
        sys.exit(1)

    print(f"Reading '{os.path.basename(txt_path)}'...")
    with open(txt_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    if len(lines) > 710:
        print(f"Truncating file from {len(lines)} lines down to 710 lines...")
        lines = lines[:710]
        with open(txt_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        print(f"Successfully truncated. Last line is now:\n  {lines[-1].strip()}")
    else:
        print(f"File already has {len(lines)} lines (<= 710). Skipping truncation.")

    # 2. Prepara e fatia o áudio a partir de 37:59 (2279 segundos) até o fim
    if not os.path.exists(wav_path):
        if os.path.exists(m4a_path):
            print(f"'{os.path.basename(wav_path)}' not found. Generating it using preprocess_audio...")
            preprocess_audio(m4a_path, wav_path)
        else:
            print(f"Error: Neither '{os.path.basename(wav_path)}' nor '{os.path.basename(m4a_path)}' was found.")
            sys.exit(1)

    print(f"Loading '{os.path.basename(wav_path)}' to slice remaining segment...")
    audio = AudioSegment.from_wav(wav_path)
    start_seconds = 2279.0  # 37:59 (10 segundos de overlap com o offset de 38:09)
    start_ms = int(start_seconds * 1000)
    
    sliced = audio[start_ms:]
    sliced.export(fix_wav_path, format="wav")
    print(f"Audio sliced successfully starting from {start_seconds}s and saved to '{os.path.basename(fix_wav_path)}'")

    # 3. Transcreve o segmento fatiado usando Gemini API diretamente
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY is not set in environment.")
        sys.exit(1)

    model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    print(f"Using model: {model_name}")

    client = genai.Client()

    print(f"Uploading '{os.path.basename(fix_wav_path)}' to Gemini File API...")
    uploaded_file = client.files.upload(file=fix_wav_path)
    print(f"Upload complete. URI: {uploaded_file.uri}")

    try:
        # Aguarda processamento
        print("Waiting for audio processing on backend...", end="", flush=True)
        while uploaded_file.state.name == "PROCESSING":
            print(".", end="", flush=True)
            time.sleep(2)
            uploaded_file = client.files.get(name=uploaded_file.name)
        print(" [Done]")

        if uploaded_file.state.name == "FAILED":
            raise RuntimeError("Gemini File API processing failed.")

        # Glossário técnico
        glossary = (
            "Aluminum sublimation factory, sublimated profiles, sublimation film (filme sublimático), "
            "heat presses, curing ovens, extrusion, anodizing, lacquer coating, metal profiles."
        )
        if os.path.exists(glossary_path):
            try:
                with open(glossary_path, "r", encoding="utf-8") as gf:
                    content = gf.read().strip()
                    if content:
                        glossary = content
                        print("Custom glossary loaded from glossario.txt")
            except Exception:
                pass

        # Instruções do sistema com o offset de tempo
        system_instruction = (
            "Você é um transcritor industrial especialista. Seu trabalho é ouvir o arquivo de áudio e "
            "transcrevê-lo com precisão em português (PT-BR), corrigindo erros de reconhecimento de fala "
            "com base no contexto e no glossário técnico fornecido abaixo.\n\n"
            f"Contexto e Glossário Técnico:\n{glossary}\n"
            "\nIMPORTANTE — OFFSET DE TIMESTAMP: Este clipe de áudio começa em 38:09 da gravação original. "
            "TODOS os timestamps DEVEM iniciar em [38:09] e contar a partir daí. NÃO reinicie do [00:00].\n\n"
            "Instruções cruciais de formatação:\n"
            "1. Identifique os falantes e separe-os obrigatoriamente como 'Participante 1', 'Participante 2', 'Participante 3', etc.\n"
            "2. Adicione timestamps precisos no início de cada fala no formato [MM:SS - MM:SS] (indicando quando a fala começou e terminou).\n"
            "3. A estrutura de cada linha deve ser exatamente: [MM:SS - MM:SS] Participante X - Texto da fala\n"
            "   Exemplo:\n"
            "   [38:09 - 38:15] Participante 1 - Exemplo de fala\n"
            "4. Corrija incompreensões fonéticas usando o contexto do glossário.\n"
            "5. Retorne APENAS a transcrição estruturada e limpa. Não inclua notas ou comentários."
        )

        prompt = (
            "Gere a transcrição completa do áudio enviado em português (PT-BR).\n"
            "Separe as falas por participantes (Participante 1, Participante 2...) e formate cada linha "
            "exatamente como: [MM:SS - MM:SS] Participante X - Texto da fala, baseando-se nas instruções do sistema."
        )

        print("Requesting transcript from Gemini (this might take a minute)...")
        response = client.models.generate_content(
            model=model_name,
            contents=[uploaded_file, prompt],
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.2,
                max_output_tokens=65536
            )
        )

        transcript_text = response.text if response else ""
        if not transcript_text or not transcript_text.strip():
            raise RuntimeError("Gemini returned an empty response.")

        print("✓ Transcription succeeded! Appending to file...")

        # 4. Grava no teste_transcript.txt e adiciona --- FIM ---
        with open(txt_path, "a", encoding="utf-8") as f:
            f.write("\n")
            f.write(transcript_text)
            f.write("\n\n--- FIM ---\n")

        print(f"Successfully fixed. File '{os.path.basename(txt_path)}' updated and finalized.")

    finally:
        # Limpeza do arquivo remoto
        print("Cleaning up remote file from Gemini File API...")
        try:
            client.files.delete(name=uploaded_file.name)
            print("Remote file deleted.")
        except Exception as e:
            print(f"Warning: Could not delete remote file: {e}")

        # Limpeza do WAV fatiado local
        if os.path.exists(fix_wav_path):
            try:
                os.remove(fix_wav_path)
                print(f"Local temporary file '{os.path.basename(fix_wav_path)}' deleted.")
            except Exception as e:
                print(f"Warning: Could not delete local temp file: {e}")

if __name__ == "__main__":
    run_isolated_fix()
