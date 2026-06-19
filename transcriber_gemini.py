import os
import sys
import time
import threading
from google import genai
from google.genai import types

def _spin_while_generating(stop_event: threading.Event, attempt: int, max_retries: int) -> None:
    """Exibe um spinner animado com cronômetro enquanto a API Gemini está processando."""
    # Frames do spinner — ASCII puro para compatibilidade com Windows
    frames = ["|", "/", "-", "\\"]
    elapsed = 0
    idx     = 0
    label   = f"Attempt {attempt}/{max_retries}"
    while not stop_event.is_set():
        mins, secs = divmod(elapsed, 60)
        # Sobrescreve a linha atual com o spinner, label e tempo decorrido
        print(f"\r  [{label}] Processando na API... {frames[idx % 4]}  {mins:02d}:{secs:02d}", end="", flush=True)
        time.sleep(1)
        elapsed += 1
        idx     += 1
    # Limpa a linha do spinner quando terminar
    print("\r" + " " * 70 + "\r", end="", flush=True)

def transcribe_audio_with_gemini(audio_path: str, output_txt_path: str, glossary: str = None) -> dict:
    """
    Faz upload do áudio limpo para a Gemini File API, solicita a transcrição com
    diarização de locutores e timestamps, captura os tokens reais consumidos
    e calcula o custo estimado em USD e BRL.
    
    Args:
        audio_path (str): Caminho para o arquivo WAV local pré-processado.
        output_txt_path (str): Caminho para salvar o transcript final em texto.
        glossary (str, optional): Termos técnicos customizados para fornecer ao modelo.
        
    Returns:
        dict: Dicionário com o texto da transcrição e os dados de uso/custo.
    """
    # Verify API key is available
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
    
    # Inicializa o cliente da API Gemini
    client = genai.Client()
    
    print(f"Uploading audio to Gemini File API: {audio_path}")
    # Upload audio to Gemini Files API (handles large files efficiently)
    uploaded_file = client.files.upload(file=audio_path)
    print(f"Upload complete. File Reference URI: {uploaded_file.uri}")
    
    # Wait for the file to be processed by Gemini backend if necessary
    # (Usually fast, but recommended for larger audio/video files)
    print("Waiting for audio processing on Gemini backend...", end="", flush=True)
    while uploaded_file.state.name == "PROCESSING":
        print(".", end="", flush=True)
        time.sleep(2)
        uploaded_file = client.files.get(name=uploaded_file.name)
        
    print(" [Done]")
    if uploaded_file.state.name == "FAILED":
        raise RuntimeError("Gemini audio processing failed on backend.")
        
    print("Audio processing on backend complete. Generating transcript with context (this may take a few seconds)...")
    
    # Define industrial default context if none provided
    default_glossary = (
        "Aluminum sublimation factory, sublimated profiles, sublimation film (filme sublimático), "
        "heat presses, curing ovens, extrusion, anodizing, lacquer coating, metal profiles."
    )
    selected_glossary = glossary if glossary else default_glossary
    
    system_instruction = (
        "You are an expert industrial transcriber. Your job is to listen to the audio file and transcrib it accurately "
        "in Portuguese (PT-BR), correcting speech recognition mistakes based on the context and technical glossary provided below.\n\n"
        f"Context & Technical Glossary:\n{selected_glossary}\n\n"
        "Instructions:\n"
        "1. Identify the speakers and separate them as Participant 1, Participant 2, Participant 3, etc.\n"
        "2. Add precise timestamps format [MM:SS - MM:SS] at the beginning of each dialog turn indicating when the turn started and ended.\n"
        "3. Correct phonetic misunderstandings using the glossary context (e.g. if the audio sounds like 'filme de cinema' or 'insulfilme' "
        "but is in a context of sublimation, write 'filme sublimático').\n"
        "4. Output ONLY the clean structured transcript. Do not include introductory notes, chat filler, or formatting notes."
    )
    
    prompt = (
        "Generate a complete transcription of the uploaded audio in Portuguese (PT-BR). "
        "Separate dialogue turns by speakers (Participant 1, 2, 3...) and write their respective timestamps [MM:SS - MM:SS] "
        "based on the system instructions."
    )
    
    # Configuração do retry com backoff exponencial para erros transitórios da API
    MAX_RETRIES  = 3    # Número máximo de tentativas antes de desistir
    RETRY_CODES  = {"UNAVAILABLE", "RESOURCE_EXHAUSTED"}  # Códigos de erro que permitem retry
    BASE_WAIT_S  = 10   # Tempo de espera inicial em segundos (dobra a cada tentativa)

    try:
        response = None
        # Loop de tentativas com backoff exponencial
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                # Inicia o spinner animado em thread separada para feedback visual durante a espera
                stop_spinner = threading.Event()
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
                            temperature=0.2,       # Temperatura baixa para transcrição mais factual
                            max_output_tokens=65536 # Limite máximo do Gemini 2.5 Flash — evita truncamento em áudios longos
                        )
                    )
                finally:
                    # Garante que o spinner pare independente de sucesso ou falha
                    stop_spinner.set()
                    spinner_thread.join()

                # Sai do loop se a requisição for bem-sucedida
                print(f"  ✓ Transcrição concluída com sucesso!")
                break

            except Exception as api_err:
                err_str = str(api_err)
                # Verifica se o erro é transitório e pode ser recuperado com retry
                is_retryable = any(code in err_str for code in RETRY_CODES)

                if is_retryable and attempt < MAX_RETRIES:
                    # Calcula o tempo de espera com backoff exponencial (10s, 20s, 40s...)
                    wait_seconds = BASE_WAIT_S * (2 ** (attempt - 1))
                    print(f"  ⚠ API temporariamente indisponível (tentativa {attempt}/{MAX_RETRIES}).")
                    print(f"  Aguardando {wait_seconds}s antes de tentar novamente...")
                    time.sleep(wait_seconds)
                else:
                    # Erro não recuperável ou esgotadas as tentativas — propaga a exceção
                    raise

        transcript_text = response.text

        # Extrai os metadados de uso real retornados pela API (tokens efetivamente consumidos)
        usage = response.usage_metadata
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

        # Salva o transcript no arquivo de saída
        print(f"Saving transcript to: {output_txt_path}")
        with open(output_txt_path, "w", encoding="utf-8") as f:
            f.write(transcript_text)

        print("Transcription process finished successfully.")
        # Retorna o dicionário completo com texto e métricas de custo
        return usage_data
        
    finally:
        # Crucial clean-up step to delete the file from the cloud after processing
        print("Cleaning up remote file from Gemini File API storage...")
        client.files.delete(name=uploaded_file.name)
        print("Remote cleanup completed.")

if __name__ == "__main__":
    # Self-test block when running directly
    if len(sys.argv) > 2:
        transcribe_audio_with_gemini(sys.argv[1], sys.argv[2])
    else:
        print("Usage: python transcriber_gemini.py <wav_audio_file> <output_txt_file>")
