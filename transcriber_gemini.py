import os
import re
import sys
import time
import threading
from google import genai
from google.genai import types


def _spin_while_generating(
    stop_event: threading.Event, attempt: int, max_retries: int
) -> None:
    """Exibe um spinner animado com cronômetro enquanto a API Gemini está processando."""
    # Frames do spinner — ASCII puro para compatibilidade com Windows
    frames  = ["|", "/", "-", "\\"]
    elapsed = 0
    idx     = 0
    label   = f"Attempt {attempt}/{max_retries}"
    while not stop_event.is_set():
        mins, secs = divmod(elapsed, 60)
        # Sobrescreve a linha atual com o spinner, label e tempo decorrido
        print(
            f"\r  [{label}] Processando na API... {frames[idx % 4]}  {mins:02d}:{secs:02d}",
            end="", flush=True
        )
        time.sleep(1)
        elapsed += 1
        idx     += 1
    # Limpa a linha do spinner quando terminar
    print("\r" + " " * 70 + "\r", end="", flush=True)


def clean_transcript_residue(transcript_path: str, lines_to_remove: int = 3) -> None:
    """
    Remove as ultimas N linhas de um arquivo de transcricao incompleto
    para eliminar residuos ou dialogos truncados causados por travamentos anteriores.
    """
    if not os.path.exists(transcript_path):
        return

    with open(transcript_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Se ja esta finalizado com o marcador de fim, nao mexemos
    if "--- FIM ---" in content:
        return

    lines = content.splitlines()
    if len(lines) <= lines_to_remove:
        print(f"[CLEANUP] Transcript file '{os.path.basename(transcript_path)}' has very few lines. Clearing to start fresh.")
        with open(transcript_path, "w", encoding="utf-8") as f:
            f.write("")
    else:
        print(f"[CLEANUP] Removing last {lines_to_remove} lines from '{os.path.basename(transcript_path)}' to clean residues.")
        trimmed_lines = lines[:-lines_to_remove]
        with open(transcript_path, "w", encoding="utf-8") as f:
            f.write("\n".join(trimmed_lines) + "\n")


def get_resume_offset(transcript_path: str) -> float:
    """
    Analisa o arquivo de transcript para determinar o ponto de retomada.
    Procura pelo padrão de timestamp [MM:SS - MM:SS] e retorna o último offset de fim.

    Args:
        transcript_path (str): Caminho para o arquivo de transcript.

    Returns:
        -1.0  -> transcript completo (contém '--- FIM ---')
         0.0  -> sem transcript ou sem timestamps (começar do zero)
        float -> segundos do último timestamp de fim (ponto para retomada)
    """
    if not os.path.exists(transcript_path):
        return 0.0

    with open(transcript_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Verifica se o transcript já está marcado como completo
    if "--- FIM ---" in content:
        return -1.0

    # Procura todos os timestamps no formato [MM:SS - MM:SS]
    pattern = r"\[(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})\]"
    matches = re.findall(pattern, content)

    if not matches:
        return 0.0

    # Extrai os minutos e segundos do último timestamp de FIM
    last          = matches[-1]
    end_minutes   = int(last[2])
    end_seconds   = int(last[3])
    return float(end_minutes * 60 + end_seconds)


def transcribe_audio_with_gemini(
    audio_path: str,
    output_txt_path: str,
    glossary: str = None,
    resume_from_seconds: float = 0.0
) -> dict:
    """
    Faz upload do áudio limpo para a Gemini File API, solicita a transcrição com
    diarização de locutores e timestamps, captura os tokens reais consumidos
    e calcula o custo estimado em USD e BRL.

    Suporta modo resume: se resume_from_seconds > 0, os timestamps do prompt são
    ajustados para o offset correto e o resultado é anexado ao arquivo existente.
    Ao final de uma transcrição bem-sucedida, adiciona o marcador '--- FIM ---'.

    Args:
        audio_path (str): Caminho para o arquivo WAV local pré-processado (ou fatiado).
        output_txt_path (str): Caminho para salvar o transcript final em texto.
        glossary (str, optional): Termos técnicos customizados para fornecer ao modelo.
        resume_from_seconds (float): Offset em segundos para modo resume. 0.0 = início.

    Returns:
        dict: Dicionário com o texto da transcrição e os dados de uso/custo.
    """
    # Verifica se a chave de API está disponível
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY environment variable is not set.\n"
            "Please set it using: $env:GEMINI_API_KEY='your_api_key_here' in PowerShell."
        )

    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    # Lê o modelo configurado no .env (fallback para gemini-2.5-flash se não definido)
    model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    print(f"Model: {model_name}")

    # Modo de operação: nova transcrição ou retomada de ponto anterior
    is_resume = resume_from_seconds > 0.0
    if is_resume:
        offset_min = int(resume_from_seconds // 60)
        offset_sec = int(resume_from_seconds % 60)
        print(f"Mode: RESUME from {offset_min:02d}:{offset_sec:02d} ({resume_from_seconds:.0f}s)")
    else:
        print("Mode: NEW transcription")

    # Inicializa o cliente da API Gemini
    client = genai.Client()

    print(f"Uploading audio to Gemini File API: {audio_path}")
    # Faz upload do áudio para a Files API (gerencia arquivos grandes de forma eficiente)
    uploaded_file = client.files.upload(file=audio_path)
    print(f"Upload complete. File Reference URI: {uploaded_file.uri}")

    # Aguarda o processamento do backend da Gemini se necessário
    print("Waiting for audio processing on Gemini backend...", end="", flush=True)
    while uploaded_file.state.name == "PROCESSING":
        print(".", end="", flush=True)
        time.sleep(2)
        uploaded_file = client.files.get(name=uploaded_file.name)

    print(" [Done]")
    if uploaded_file.state.name == "FAILED":
        raise RuntimeError("Gemini audio processing failed on backend.")

    print("Audio processing on backend complete. Generating transcript with context (this may take a few seconds)...")

    # Define o glossário industrial padrão se nenhum for fornecido
    default_glossary = (
        "Aluminum sublimation factory, sublimated profiles, sublimation film (filme sublimático), "
        "heat presses, curing ovens, extrusion, anodizing, lacquer coating, metal profiles."
    )
    selected_glossary = glossary if glossary else default_glossary

    # Instrução de offset de timestamp — informa ao modelo a partir de qual segundo o áudio começa
    offset_instruction = ""
    if is_resume:
        offset_instruction = (
            f"\nIMPORTANT — TIMESTAMP OFFSET: This audio clip starts at "
            f"{offset_min:02d}:{offset_sec:02d} of the original recording. "
            f"ALL timestamps MUST begin at [{offset_min:02d}:{offset_sec:02d}] "
            f"and count forward from there. Do NOT restart from [00:00].\n"
        )

    system_instruction = (
        "You are an expert industrial transcriber. Your job is to listen to the audio file and "
        "transcribe it accurately in Portuguese (PT-BR), correcting speech recognition mistakes "
        "based on the context and technical glossary provided below.\n\n"
        f"Context & Technical Glossary:\n{selected_glossary}\n"
        f"{offset_instruction}\n"
        "Instructions:\n"
        "1. Identify the speakers and separate them as Participant 1, Participant 2, Participant 3, etc.\n"
        "2. Add precise timestamps format [MM:SS - MM:SS] at the beginning of each dialog turn "
        "indicating when the turn started and ended.\n"
        "3. Correct phonetic misunderstandings using the glossary context (e.g. if the audio sounds "
        "like 'filme de cinema' or 'insulfilme' but is in a context of sublimation, write "
        "'filme sublimático').\n"
        "4. Output ONLY the clean structured transcript. Do not include introductory notes, "
        "chat filler, or formatting notes."
    )

    prompt = (
        "Generate a complete transcription of the uploaded audio in Portuguese (PT-BR). "
        "Separate dialogue turns by speakers (Participant 1, 2, 3...) and write their "
        "respective timestamps [MM:SS - MM:SS] based on the system instructions."
    )

    # Configuração do retry com backoff exponencial para erros transitórios da API
    MAX_RETRIES = 3    # Número máximo de tentativas antes de desistir
    RETRY_CODES = {"UNAVAILABLE", "RESOURCE_EXHAUSTED"}  # Erros recuperáveis
    BASE_WAIT_S = 10   # Tempo de espera inicial em segundos (dobra a cada tentativa)

    try:
        response = None
        # Loop de tentativas com backoff exponencial
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                # Inicia o spinner animado em thread separada para feedback visual
                stop_spinner   = threading.Event()
                spinner_thread = threading.Thread(
                    target=_spin_while_generating,
                    args=(stop_spinner, attempt, MAX_RETRIES),
                    daemon=True
                )
                spinner_thread.start()

                try:
                    # Requisição bloqueante ao modelo configurado no .env
                    response = client.models.generate_content(
                        model=model_name,
                        contents=[uploaded_file, prompt],
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            temperature=0.2,        # Temperatura baixa para transcrição mais factual
                            max_output_tokens=65536  # Limite máximo — evita truncamento em áudios longos
                        )
                    )
                finally:
                    # Garante que o spinner pare independente de sucesso ou falha
                    stop_spinner.set()
                    spinner_thread.join()

                # --- Validação: detecta resposta vazia (ex: modelo não suporta áudio via Files API) ---
                transcript_text = response.text if response else ""
                if not transcript_text or not transcript_text.strip():
                    raise RuntimeError(
                        f"Model '{model_name}' returned an empty transcript. "
                        "This model may not support audio via the Files API. "
                        "Try setting GEMINI_MODEL=gemini-2.5-flash in your .env file."
                    )

                # Sai do loop se a requisição foi bem-sucedida
                print(f"  \u2713 Transcricao concluida com sucesso!")
                break

            except Exception as api_err:
                err_str = str(api_err)
                # Verifica se o erro é transitório e pode ser recuperado com retry
                is_retryable = any(code in err_str for code in RETRY_CODES)

                if is_retryable and attempt < MAX_RETRIES:
                    # Calcula o tempo de espera com backoff exponencial (10s, 20s, 40s...)
                    wait_seconds = BASE_WAIT_S * (2 ** (attempt - 1))
                    print(f"  ! API temporariamente indisponivel (tentativa {attempt}/{MAX_RETRIES}).")
                    print(f"  Aguardando {wait_seconds}s antes de tentar novamente...")
                    time.sleep(wait_seconds)
                else:
                    # Erro não recuperável ou esgotadas as tentativas — propaga a exceção
                    raise

        # Extrai os metadados de uso real retornados pela API (tokens efetivamente consumidos)
        usage         = response.usage_metadata
        input_tokens  = usage.prompt_token_count     if usage else 0
        output_tokens = usage.candidates_token_count if usage else 0

        # --- Tabela de preços do Gemini 2.5 Flash (por 1 milhão de tokens) ---
        # Fonte: https://ai.google.dev/pricing
        PRICE_INPUT_PER_MILLION  = 0.30   # USD por 1M tokens de input
        PRICE_OUTPUT_PER_MILLION = 2.50   # USD por 1M tokens de output

        # Custo calculado em USD com base nos tokens reais da resposta
        cost_input_usd  = (input_tokens  / 1_000_000) * PRICE_INPUT_PER_MILLION
        cost_output_usd = (output_tokens / 1_000_000) * PRICE_OUTPUT_PER_MILLION
        total_cost_usd  = cost_input_usd + cost_output_usd

        # Agrupa todos os dados de uso para retornar ao pipeline principal
        usage_data = {
            "input_tokens":    input_tokens,
            "output_tokens":   output_tokens,
            "total_tokens":    input_tokens + output_tokens,
            "cost_input_usd":  cost_input_usd,
            "cost_output_usd": cost_output_usd,
            "total_cost_usd":  total_cost_usd,
            "transcript":      transcript_text,
        }

        # Salva o transcript: modo append em resume, sobrescreve em nova transcrição
        write_mode = "a" if is_resume else "w"
        print(f"Saving transcript to: {output_txt_path} (mode={write_mode})")
        with open(output_txt_path, write_mode, encoding="utf-8") as f:
            if is_resume:
                # Adiciona separação visual antes do trecho retomado
                f.write("\n")
            f.write(transcript_text)

        print("Transcription process finished successfully.")
        # Retorna o dicionário completo com texto e métricas de custo
        return usage_data

    finally:
        # Limpeza obrigatória: remove o arquivo do armazenamento da Gemini File API
        print("Cleaning up remote file from Gemini File API storage...")
        client.files.delete(name=uploaded_file.name)
        print("Remote cleanup completed.")


if __name__ == "__main__":
    # Bloco de autoteste ao executar diretamente
    if len(sys.argv) > 2:
        transcribe_audio_with_gemini(sys.argv[1], sys.argv[2])
    else:
        print("Usage: python transcriber_gemini.py <wav_audio_file> <output_txt_file>")
