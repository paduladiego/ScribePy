import os
import re
import time
import requests
import wave
from .spinner import TerminalSpinner

def _get_wav_duration(audio_path: str) -> float:
    """
    Calcula de forma nativa a duração de um arquivo WAV em segundos.
    """
    with wave.open(audio_path, "rb") as wav_file:
        frames = wav_file.getnframes()
        rate = wav_file.getframerate()
        return frames / float(rate)

def _extract_vocabulary_terms(glossary: str) -> list[str]:
    """
    Extrai termos de vocabulário limpos a partir de uma string de glossário.
    Suporta tanto uma lista simples separada por vírgulas quanto o formato Markdown complexo do usuário.
    """
    if not glossary:
        return []
        
    terms = set()
    
    # Se não contiver formatação de Markdown, processa como lista separada por vírgulas
    if not any(marker in glossary for marker in ["#", "- **", "|", "```"]):
        for term in glossary.split(","):
            cleaned = term.strip()
            if cleaned:
                terms.add(cleaned)
        return sorted(list(terms))
        
    # Processa o formato Markdown complexo do usuário
    for line in glossary.splitlines():
        line = line.strip()
        if not line:
            continue
            
        # 1. Se for uma linha de tabela Markdown (contém |):
        if line.startswith("|") and line.count("|") >= 2:
            # Captura termos entre aspas duplas (ex: "Pebolim")
            quoted = re.findall(r'"([^"]+)"', line)
            for q in quoted:
                cleaned = q.strip()
                if cleaned:
                    terms.add(cleaned)
            # Captura termos entre negritos
            bolded = re.findall(r'\*\*([^*]+)\*\*', line)
            for b in bolded:
                # Remove explicações entre parênteses
                val = re.sub(r'\s*\([^)]*\)', '', b).strip()
                if val:
                    terms.add(val)
            continue
            
        # 2. Se for uma linha de lista Markdown com termos em negrito
        list_match = re.match(r'^[-*]\s+\*\*([^*:]+):?\*\*', line)
        if list_match:
            term_val = list_match.group(1).strip()
            for part in term_val.split("/"):
                cleaned = part.strip()
                if cleaned:
                    terms.add(cleaned)
            continue
            
        # 3. Captura geral de termos curtos em negrito
        bolded_general = re.findall(r'\*\*([^*:]+)\*\*', line)
        for bg in bolded_general:
            cleaned = bg.strip()
            if cleaned and len(cleaned) < 50:
                terms.add(cleaned)
                
    # Lista de títulos e textos gerais a ignorar
    blacklisted = {
        "GLOSSÁRIO DE CONTEXTO E CORREÇÃO FONÉTICA - PROJETO AS IS",
        "DIRETRIZ MACRO DE TRANSCRIÇÃO",
        "ENTIDADES, NOMES PRÓPRIOS E COORDENADORES",
        "ACRÔNIMOS TÉCNICOS E ENGENHARIA DE PROCESSOS",
        "MAQUINAÁRIOS, LINHAS DE PRODUÇÃO E JARGÕES",
        "DICIONÁRIO DE CORREÇÃO FONÉTICA",
        "Objetivo do Projeto",
        "Proibição de Termos",
        "Ambiente de Gravação"
    }
    
    filtered_terms = []
    for t in terms:
        if t not in blacklisted and len(t) > 1:
            filtered_terms.append(t)
            
    return sorted(filtered_terms)

def transcribe_audio_with_gladia(
    audio_path: str,
    output_txt_path: str,
    glossary: str = None,
    resume_from_seconds: float = 0.0
) -> dict:
    """
    Envia o arquivo de áudio para a API do Gladia v2, realiza o polling do status
    da transcrição com spinner ativo, formata os timestamps com suporte a diarização,
    e calcula os custos estimados em dólares baseados no tempo de áudio.

    Args:
        audio_path (str): Caminho local para o arquivo de áudio WAV de entrada.
        output_txt_path (str): Caminho do arquivo texto onde será salva a transcrição.
        glossary (str, opcional): Termos do glossário técnico passados ao modelo.
        resume_from_seconds (float): Offset de segundos caso seja retomada.

    Returns:
        dict: Estatísticas de uso de tokens e custo total em dólares (USD).
    """
    # 1. Recupera as chaves e modelos do ambiente
    api_key = os.environ.get("GLADIA_API_KEY")
    if not api_key:
        raise ValueError(
            "A variável de ambiente GLADIA_API_KEY não foi configurada no arquivo .env."
        )

    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Arquivo de áudio não encontrado: {audio_path}")

    model_name = os.environ.get("GLADIA_MODEL", "solaria-1")
    print(f"Model: {model_name}")

    is_resume = resume_from_seconds > 0.0
    if is_resume:
        offset_min = int(resume_from_seconds // 60)
        offset_sec = int(resume_from_seconds % 60)
        print(f"Mode: RESUME from {offset_min:02d}:{offset_sec:02d} ({resume_from_seconds:.0f}s)")
    else:
        print("Mode: NEW transcription")

    headers = {
        "x-gladia-key": api_key
    }

    # 2. Faz o upload do arquivo de áudio para a API do Gladia
    print(f"Uploading audio to Gladia API: {audio_path}")
    
    # Tratamento básico de caracteres não-ASCII no nome do arquivo para upload
    safe_filename = os.path.basename(audio_path)
    try:
        safe_filename.encode("ascii")
    except UnicodeEncodeError:
        safe_filename = "scribepy_upload_temp.wav"

    with open(audio_path, "rb") as f:
        files = {
            "audio": (safe_filename, f, "audio/wav")
        }
        upload_response = requests.post(
            "https://api.gladia.io/v2/upload",
            headers=headers,
            files=files
        )
        upload_response.raise_for_status()

    upload_data = upload_response.json()
    audio_url = upload_data["audio_url"]
    print(f"Upload complete. Audio URL: {audio_url}")

    # 3. Dispara a transcrição assíncrona com diarização ativa e glossário
    print("Initiating transcription job on Gladia backend...")
    payload = {
        "audio_url": audio_url,
        "diarization": True,
        "diarization_config": {
            "min_speakers": 1,
            "max_speakers": 5
        },
        "language_config": {
            "languages": ["pt"]
        },
        "model": model_name
    }

    # Adiciona o vocabulário customizado extraindo os termos do glossário Markdown ou lista
    if glossary:
        terms = _extract_vocabulary_terms(glossary)
        if terms:
            print(f"Glossary parsed successfully! Sent {len(terms)} technical terms to Gladia Custom Vocabulary.")
            payload["custom_vocabulary"] = True
            payload["custom_vocabulary_config"] = {
                "vocabulary": terms,
                "default_intensity": 0.5
            }

    transcription_response = requests.post(
        "https://api.gladia.io/v2/pre-recorded",
        headers={**headers, "Content-Type": "application/json"},
        json=payload
    )
    transcription_response.raise_for_status()
    job_data = transcription_response.json()
    result_url = job_data["result_url"]
    job_id = job_data["id"]
    print(f"Transcription job started. Job ID: {job_id}")

    # 4. Faz polling do status até a finalização do processamento
    spinner = TerminalSpinner(label="Processando transcrição no Gladia v2")
    spinner.start()

    try:
        while True:
            result_response = requests.get(result_url, headers=headers)
            result_response.raise_for_status()
            result_data = result_response.json()

            status = result_data.get("status")
            if status == "done":
                break
            elif status == "error":
                error_msg = result_data.get("error", "Erro interno da API do Gladia.")
                raise RuntimeError(f"Gladia transcription failed: {error_msg}")

            time.sleep(5)
    finally:
        spinner.stop()

    print(" \u2713 Transcrição no Gladia concluída com sucesso!")

    # 5. Processa as falas/segmentos (utterances) formatando os timestamps
    result_detail = result_data.get("result", {})
    transcription_detail = result_detail.get("transcription", {})
    utterances = transcription_detail.get("utterances", [])

    formatted_lines = []
    for utterance in utterances:
        text = utterance.get("text", "").strip()
        if not text:
            continue

        start = utterance.get("start", 0.0)
        end = utterance.get("end", 0.0)
        speaker = utterance.get("speaker", 0)

        # Ajusta os timestamps aplicando o offset de retomada do checkpoint
        start_adjusted = start + resume_from_seconds
        end_adjusted = end + resume_from_seconds

        start_min = int(start_adjusted // 60)
        start_sec = int(start_adjusted % 60)
        end_min = int(end_adjusted // 60)
        end_sec = int(end_adjusted % 60)

        # Converte o speaker de índice 0 para Participante 1, index 1 para Participante 2, etc.
        speaker_name = f"Participante {speaker + 1}"
        formatted_lines.append(
            f"[{start_min:02d}:{start_sec:02d} - {end_min:02d}:{end_sec:02d}] {speaker_name} - {text}"
        )

    transcript_text = "\n".join(formatted_lines)

    # 6. Calcula os custos do Gladia (taxa fixa de USD $0.61 por hora de áudio processada)
    audio_duration = _get_wav_duration(audio_path)
    cost_per_second = 0.61 / 3600.0
    total_cost_usd = audio_duration * cost_per_second

    usage_data = {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "cost_input_usd": 0.0,
        "cost_output_usd": 0.0,
        "total_cost_usd": total_cost_usd,
        "transcript": transcript_text,
    }

    # 7. Salva a transcrição no arquivo texto
    write_mode = "a" if is_resume else "w"
    print(f"Saving transcript to: {output_txt_path} (mode={write_mode})")
    with open(output_txt_path, write_mode, encoding="utf-8") as f:
        if is_resume:
            f.write("\n")
        f.write(transcript_text)

    print("Transcription process finished successfully.")
    return usage_data
