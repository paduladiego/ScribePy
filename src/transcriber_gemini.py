import os
import re
import sys
import time
import threading
from google import genai
from google.genai import types


from .spinner import TerminalSpinner


def _deduplicate_repetition_loops(text: str, max_repeats: int = 3) -> str:
    """
    Remove blocos de repeticao causados por alucinacao do Gemini.
    Quando a mesma fala aparece N+ vezes consecutivas, colpasa para apenas 1 linha
    mais um marcador [silencio / ruido de fundo], preservando o primeiro timestamp.
    """
    # Padrao para capturar uma linha completa de transcript (suporta minutos de 1 a 3 digitos e opcionalmente horas)
    # Aceita tanto formatos com identificacao de participante (Participante X - ou Participant X:) quanto sem.
    line_pattern = re.compile(
        r"(\[\d{1,3}:\d{2}(?::\d{2})? - \d{1,3}:\d{2}(?::\d{2})?\]\s*(?:(?:Participant|Participante)\s*\d+\s*[-:]\s*)?.+)"
    )
    lines = text.splitlines(keepends=True)
    result = []
    i = 0
    while i < len(lines):
        current_line = lines[i]
        # Extrai somente o texto falado (sem o timestamp) para comparacao
        match = line_pattern.match(current_line.strip())
        if match:
            # Isola o texto sem o timestamp para detectar repeticoes (suporta minutos de 1 a 3 digitos)
            spoken_text = re.sub(r"^\[\d{1,3}:\d{2}(?::\d{2})? - \d{1,3}:\d{2}(?::\d{2})?\]\s*", "", current_line.strip())
            # Conta quantas linhas consecutivas tem o mesmo texto falado
            repeat_count = 1
            j = i + 1
            while j < len(lines):
                next_spoken = re.sub(r"^\[\d{1,3}:\d{2}(?::\d{2})? - \d{1,3}:\d{2}(?::\d{2})?\]\s*", "", lines[j].strip())
                if next_spoken == spoken_text:
                    repeat_count += 1
                    j += 1
                else:
                    break
            if repeat_count >= max_repeats:
                # Extrai o timestamp final do bloco para registrar o intervalo coberto (suporta minutos de 1 a 3 digitos e opcionalmente horas)
                last_timestamp_match = re.match(r"\[(\d{1,3}:\d{2}(?::\d{2})?) - (\d{1,3}:\d{2}(?::\d{2})?)\]", lines[j - 1].strip())
                if last_timestamp_match:
                    start_time = last_timestamp_match.group(1)
                    end_time   = last_timestamp_match.group(2)
                    # Mantém a primeira linha do bloco
                    result.append(current_line)
                    # Adiciona marcador no formato [MM:SS - MM:SS] para que get_resume_offset
                    # consiga detectar o fim do bloco de silêncio como ponto válido de retomada
                    result.append(f"[{start_time} - {end_time}] [silencio / ruido de fundo — trecho suprimido ({repeat_count} repeticoes)]\n")
                    print(f"  [DEDUP] Collapsed {repeat_count} repetitions of: '{spoken_text[:40]}' -> silence marker at {end_time}")
                else:
                    # Sem timestamp detectavel — mantém apenas a primeira linha
                    result.append(current_line)
                    print(f"  [DEDUP] Collapsed {repeat_count} repetitions (no timestamp anchor found).")
                i = j
                continue
        result.append(current_line)
        i += 1
    return "".join(result)


def _adjust_timestamps(text: str, offset_seconds: float) -> str:
    """
    Ajusta todos os timestamps no formato [MM:SS - MM:SS] ou [H:MM:SS - H:MM:SS]
    somando o offset_seconds a cada valor de tempo.
    """
    def replace_match(match):
        start_min = int(match.group(1))
        start_sec = int(match.group(2))
        end_min = int(match.group(3))
        end_sec = int(match.group(4))
        
        start_total = start_min * 60 + start_sec + offset_seconds
        end_total = end_min * 60 + end_sec + offset_seconds
        
        new_start_min = int(start_total // 60)
        new_start_sec = int(start_total % 60)
        new_end_min = int(end_total // 60)
        new_end_sec = int(end_total % 60)
        
        return f"[{new_start_min:02d}:{new_start_sec:02d} - {new_end_min:02d}:{new_end_sec:02d}]"

    # Regex para capturar [MM:SS - MM:SS] onde minutos podem ter de 1 a 3 digitos
    pattern = r"\[(\d{1,3}):(\d{2})\s*-\s*(\d{1,3}):(\d{2})\]"
    return re.sub(pattern, replace_match, text)


def clean_transcript_residue(transcript_path: str, lines_to_remove: int = 4) -> None:
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

    # Procura todos os timestamps no formato [MM:SS - MM:SS] (suporta ate 3 digitos de minutos)
    pattern = r"\[(\d{1,3}):(\d{2})\s*-\s*(\d{1,3}):(\d{2})\]"
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
    # Detecta se o nome do arquivo contém caracteres não-ASCII (ex: acentos portugueses)
    # A biblioteca google-genai tenta codificar o caminho como ASCII no Windows, causando falha
    safe_audio_path = audio_path
    temp_safe_path = None
    try:
        audio_path.encode("ascii")
    except UnicodeEncodeError:
        import shutil
        import tempfile
        # Cria um arquivo temporário com nome seguro (sem acentos) para o upload
        audio_dir = os.path.dirname(audio_path)
        ext = os.path.splitext(audio_path)[1]
        tmp = tempfile.NamedTemporaryFile(
            delete=False, suffix=ext, dir=audio_dir, prefix="scribepy_upload_"
        )
        tmp.close()
        shutil.copy2(audio_path, tmp.name)
        safe_audio_path = tmp.name
        temp_safe_path = tmp.name
        print(f"  [FIX] Non-ASCII filename detected. Using temp file for upload: {os.path.basename(safe_audio_path)}")

    try:
        # Faz upload do áudio para a Files API (gerencia arquivos grandes de forma eficiente)
        uploaded_file = client.files.upload(file=safe_audio_path)
    finally:
        # Remove o arquivo temporário de upload após o envio ser iniciado
        if temp_safe_path and os.path.exists(temp_safe_path):
            try:
                os.remove(temp_safe_path)
            except Exception:
                pass

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

    # Instrução de offset de timestamp removida do prompt para o Gemini.
    # O Gemini gera sempre a partir de 00:00 e o código Python ajusta os timestamps somando o offset.
    system_instruction = (
        "Você é um transcritor industrial especialista. Seu trabalho é ouvir o arquivo de áudio e "
        "transcrevê-lo com precisão em português (PT-BR), corrigindo erros de reconhecimento de fala "
        "com base no contexto e no glossário técnico fornecido abaixo.\n\n"
        f"Contexto e Glossário Técnico:\n{selected_glossary}\n\n"
        "Instruções cruciais de formatação:\n"
        "1. Identifique os falantes e separe-os obrigatoriamente como 'Participante 1', 'Participante 2', 'Participante 3', etc.\n"
        "2. Adicione timestamps precisos no início de cada fala no formato [MM:SS - MM:SS] (indicando quando a fala começou e terminou).\n"
        "3. A estrutura de cada linha deve ser exatamente: [MM:SS - MM:SS] Participante X - Texto da fala\n"
        "   Exemplo:\n"
        "   [00:00 - 00:05] Participante 1 - Olá, bom dia.\n"
        "   [00:05 - 00:12] Participante 2 - Bom dia, tudo bem?\n"
        "4. Corrija incompreensões fonéticas usando o contexto do glossário (por exemplo, se o áudio parecer "
        "'filme de cinema' ou 'insulfilme' mas estiver num contexto de sublimação, escreva "
        "'filme sublimático').\n"
        "5. Retorne APENAS a transcrição estruturada e limpa. Não inclua notas introdutórias, "
        "conversa fiada ou explicações de formatação."
    )

    prompt = (
        "Gere a transcrição completa do áudio enviado em português (PT-BR).\n"
        "Separe as falas por participantes (Participante 1, Participante 2...) e formate cada linha "
        "exatamente como: [MM:SS - MM:SS] Participante X - Texto da fala, começando do tempo [00:00] "
        "e seguindo rigorosamente as instruções do sistema."
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
                # Inicia o spinner animado e cronometro de tempo usando a classe unificada
                spinner = TerminalSpinner(label=f"Attempt {attempt}/{MAX_RETRIES} - Processando na API")
                spinner.start()
                try:
                    # Requisicao bloqueante ao modelo configurado no .env
                    response = client.models.generate_content(
                        model=model_name,
                        contents=[uploaded_file, prompt],
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            temperature=0.2,        # Temperatura baixa para transcricao mais factual
                            max_output_tokens=65536  # Limite maximo — evita truncamento em audios longos
                        )
                    )
                finally:
                    # Garante que o spinner pare independente de sucesso ou falha
                    spinner.stop()

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

        # Aplica filtro anti-loop: colapsa repeticoes causadas por alucinacao do Gemini
        transcript_text = _deduplicate_repetition_loops(transcript_text, max_repeats=3)

        # Se for resume, ajusta todos os timestamps somando o offset inicial do áudio enviado
        if is_resume:
            print(f"  [RESUME] Ajustando timestamps com offset de +{resume_from_seconds:.1f}s...")
            transcript_text = _adjust_timestamps(transcript_text, resume_from_seconds)

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
