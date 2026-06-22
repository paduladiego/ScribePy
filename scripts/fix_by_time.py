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
from src.spinner import TerminalSpinner

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

def time_str_to_seconds(t_str: str) -> float:
    """Converte MM:SS ou H:MM:SS para segundos."""
    parts = list(map(int, t_str.split(":")))
    if len(parts) == 2:
        return float(parts[0] * 60 + parts[1])
    elif len(parts) == 3:
        return float(parts[0] * 3600 + parts[1] * 60 + parts[2])
    else:
        raise ValueError("Formato de tempo inválido. Use MM:SS.")

def run_fix_by_time():
    print("=" * 60)
    print("SCRIBEPY SURGICAL FIX — RE-TRANSCRIBE RANGES FROM TXT")
    print("=" * 60)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(script_dir, ".."))

    # Verifica se o arquivo de audio foi passado via terminal
    if len(sys.argv) < 2:
        print("Uso: .venv/Scripts/python scripts/fix_by_time.py <caminho_do_audio_ou_base_name>")
        print("Exemplo: .venv/Scripts/python scripts/fix_by_time.py Qualidade-Joao.m4a")
        print("\nArquivos de áudio disponíveis na raiz do projeto:")
        try:
            audio_files = [f for f in os.listdir(project_root) if f.endswith(".m4a") or (f.endswith(".wav") and not f.endswith("_clean.wav") and not f.endswith("_resume.wav"))]
            for f in audio_files:
                print(f"  - {f}")
        except Exception:
            pass
        return

    input_arg = sys.argv[1]
    # Remove a extensao se o usuario passou com .m4a ou .wav
    base_name = os.path.splitext(os.path.basename(input_arg))[0]
    # Se o base_name termina com "_clean", removemos para achar o audio original
    if base_name.endswith("_clean"):
        base_name = base_name[:-6]
    
    ranges_file = os.path.join(script_dir, "fix_ranges.txt")
    converted_dir = os.path.join(project_root, "converted")
    os.makedirs(converted_dir, exist_ok=True)
    
    txt_path = os.path.join(converted_dir, f"{base_name}_transcript.txt")
    wav_path = os.path.join(converted_dir, f"{base_name}_clean.wav")
    
    # Procura pelo arquivo de audio original na raiz, na pasta converted ou usando o argumento direto
    if os.path.exists(os.path.join(project_root, input_arg)):
        m4a_path = os.path.join(project_root, input_arg)
    elif os.path.exists(os.path.join(converted_dir, input_arg)):
        m4a_path = os.path.join(converted_dir, input_arg)
    elif os.path.exists(input_arg):
        m4a_path = os.path.abspath(input_arg)
    else:
        m4a_path = os.path.join(converted_dir, f"{base_name}.m4a")
        
    output_correcoes_path = os.path.join(converted_dir, f"{base_name}_transcript_correcoes.txt")
    glossary_path = os.path.join(project_root, "glossario.txt")

    # 1. Verifica/Cria o arquivo de configuração de intervalos
    if not os.path.exists(ranges_file):
        print(f"Criando arquivo de exemplo em: {ranges_file}")
        with open(ranges_file, "w", encoding="utf-8") as f:
            f.write("# Escreva os intervalos que deseja corrigir, um por linha.\n")
            f.write("# Formato: tempo_inicio - tempo_fim\n")
            f.write("# Exemplo:\n")
            f.write("26:10 - 26:30\n")
            f.write("37:50 - 38:15\n")
        print("Edite o arquivo 'scripts/fix_ranges.txt' com os intervalos desejados e rode o script novamente.")
        return

    # 2. Lê e interpreta os intervalos do arquivo
    ranges = []
    with open(ranges_file, "r", encoding="utf-8") as f:
        for line in f:
            line_str = line.strip()
            if not line_str or line_str.startswith("#"):
                continue
            match = re.match(r"^([\d:]+)\s*-\s*([\d:]+|fim)$", line_str, re.IGNORECASE)
            if match:
                ranges.append((match.group(1).strip(), match.group(2).strip()))

    if not ranges:
        print("Error: Nenhum intervalo válido encontrado em 'scripts/fix_ranges.txt'.")
        print("Adicione linhas no formato: MM:SS - MM:SS")
        return

    # 3. Verifica e prepara o WAV completo (com redução de ruído)
    if not os.path.exists(wav_path):
        if os.path.exists(m4a_path):
            print(f"'{os.path.basename(wav_path)}' not found. Generating it using preprocess_audio...")
            preprocess_audio(m4a_path, wav_path)
        else:
            print(f"Error: Neither '{os.path.basename(wav_path)}' nor '{os.path.basename(m4a_path)}' was found.")
            sys.exit(1)

    print(f"Loading '{os.path.basename(wav_path)}'...")
    audio = AudioSegment.from_wav(wav_path)
    audio_duration = len(audio) / 1000.0

    # Inicializa/limpa o arquivo de correções
    with open(output_correcoes_path, "w", encoding="utf-8") as out_f:
        out_f.write("============================================================\n")
        out_f.write(" TRECHOS RE-TRANSCRITOS E CORRIGIDOS\n")
        out_f.write("============================================================\n\n")

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY is not set.")
        sys.exit(1)

    model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    client = genai.Client()

    # 4. Processa cada intervalo individualmente
    for start_str, end_str in ranges:
        try:
            start_seconds = time_str_to_seconds(start_str)
            if end_str.lower() == "fim":
                end_seconds = audio_duration
            else:
                end_seconds = time_str_to_seconds(end_str)

            print("\n" + "-" * 60)
            print(f"Processing range: {start_str} -> {end_str} ({start_seconds:.1f}s -> {end_seconds:.1f}s)")
            print("-" * 60)

            # Fatia o trecho correspondente
            start_ms = int(start_seconds * 1000)
            end_ms = int(end_seconds * 1000)
            sliced = audio[start_ms:end_ms]
            
            # Gera um nome temporário único para a fatia na pasta converted
            fix_wav_path = os.path.join(converted_dir, f"temp_slice_{start_str.replace(':', '_')}.wav")
            sliced.export(fix_wav_path, format="wav")

            print(f"Uploading slice '{os.path.basename(fix_wav_path)}' to Gemini API...")
            uploaded_file = client.files.upload(file=fix_wav_path)

            try:
                print("Waiting for backend processing...", end="", flush=True)
                while uploaded_file.state.name == "PROCESSING":
                    print(".", end="", flush=True)
                    time.sleep(2)
                    uploaded_file = client.files.get(name=uploaded_file.name)
                print(" [Done]")

                if uploaded_file.state.name == "FAILED":
                    raise RuntimeError("Gemini File API processing failed.")

                # Carrega o glossário local
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
                    except Exception:
                        pass

                offset_min = int(start_seconds // 60)
                offset_sec = int(start_seconds % 60)

                system_instruction = (
                    "Você é um transcritor industrial especialista. Seu trabalho é ouvir o arquivo de áudio e "
                    "transcrevê-lo com precisão em português (PT-BR), corrigindo erros de reconhecimento de fala "
                    "com base no contexto e no glossário técnico fornecido abaixo.\n\n"
                    f"Contexto e Glossário Técnico:\n{glossary}\n"
                    f"\nIMPORTANTE — OFFSET DE TIMESTAMP: Este clipe de áudio começa em {offset_min:02d}:{offset_sec:02d} da gravação original. "
                    f"TODOS os timestamps DEVEM iniciar em [{offset_min:02d}:{offset_sec:02d}] e contar a partir daí. NÃO reinicie do [00:00].\n\n"
                    "Instruções cruciais de formatação:\n"
                    "1. Identifique os falantes e separe-os obrigatoriamente como 'Participante 1', 'Participante 2', 'Participante 3', etc.\n"
                    "2. Adicione timestamps precisos no início de cada fala no formato [MM:SS - MM:SS] (indicando quando a fala começou e terminou).\n"
                    "3. A estrutura de cada linha deve ser exatamente: [MM:SS - MM:SS] Participante X - Texto da fala\n"
                    "   Exemplo:\n"
                    f"   [{offset_min:02d}:{offset_sec:02d} - {offset_min:02d}:{offset_sec:02d}] Participante 1 - Exemplo de fala\n"
                    "4. Corrija incompreensões fonéticas usando o contexto do glossário.\n"
                    "5. Retorne APENAS a transcrição estruturada e limpa. Não inclua notas ou comentários."
                )

                prompt = (
                    "Gere a transcrição completa do áudio enviado em português (PT-BR).\n"
                    "Separe as falas por participantes (Participante 1, Participante 2...) e formate cada linha "
                    "exatamente como: [MM:SS - MM:SS] Participante X - Texto da fala, baseando-se nas instruções do sistema."
                )

                spinner = TerminalSpinner(label="Requesting transcript from Gemini")
                spinner.start()
                try:
                    response = client.models.generate_content(
                        model=model_name,
                        contents=[uploaded_file, prompt],
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            temperature=0.2,
                            max_output_tokens=65536
                        )
                    )
                finally:
                    spinner.stop()

                new_transcript = response.text if response else ""
                if not new_transcript or not new_transcript.strip():
                    raise RuntimeError("Gemini returned an empty response.")

                # Grava no arquivo de correções teste_transcript_correcoes.txt
                with open(output_correcoes_path, "a", encoding="utf-8") as out_f:
                    out_f.write(f"=== TRECHO CORRIGIDO: {start_str} - {end_str} ===\n")
                    out_f.write(new_transcript.strip())
                    out_f.write("\n\n")

                print(f"✓ Trecho {start_str} - {end_str} re-transcrito com sucesso e salvo em '{os.path.basename(output_correcoes_path)}'!")

            finally:
                # Deleta o arquivo remoto
                try:
                    client.files.delete(name=uploaded_file.name)
                except Exception:
                    pass
                
                # Removido/comentado a delecao da fatia local — o usuario limpa depois
                # if os.path.exists(fix_wav_path):
                #     try:
                #         os.remove(fix_wav_path)
                #     except Exception:
                #         pass
        except Exception as chunk_err:
            print(f"Erro ao processar o intervalo {start_str} - {end_str}: {chunk_err}")

    print("\n" + "=" * 60)
    print(f"Processo concluído! Correções salvas em: {output_correcoes_path}")
    print("=" * 60)

if __name__ == "__main__":
    run_fix_by_time()
