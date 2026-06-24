import os
import wave
import time
from openai import OpenAI
from .spinner import TerminalSpinner

def _get_wav_duration(audio_path: str) -> float:
    """
    Calcula de forma nativa a duração de um arquivo WAV em segundos.
    """
    with wave.open(audio_path, "rb") as wav_file:
        frames = wav_file.getnframes()
        rate = wav_file.getframerate()
        return frames / float(rate)

def transcribe_audio_with_openai(
    audio_path: str,
    output_txt_path: str,
    glossary: str = None,
    resume_from_seconds: float = 0.0
) -> dict:
    """
    Envia o arquivo de áudio para a API do OpenAI Whisper-1, gera a transcrição
    com marcação de timestamps ajustados pelo offset, e calcula o custo estimado.

    Args:
        audio_path (str): Caminho local para o arquivo de áudio.
        output_txt_path (str): Caminho do arquivo para salvar a transcrição.
        glossary (str, opcional): Termos do glossário passados no prompt.
        resume_from_seconds (float): Offset de tempo caso seja uma retomada.

    Returns:
        dict: Metadados contendo estatísticas de uso e custo.
    """
    # 1. Recupera a chave da OpenAI do ambiente
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "A variável de ambiente OPENAI_API_KEY não foi configurada no arquivo .env."
        )

    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Arquivo de áudio não encontrado: {audio_path}")

    # 2. Inicializa configurações
    model_name = os.environ.get("OPENAI_MODEL", "whisper-1")
    print(f"Model: {model_name}")

    is_resume = resume_from_seconds > 0.0
    if is_resume:
        offset_min = int(resume_from_seconds // 60)
        offset_sec = int(resume_from_seconds % 60)
        print(f"Mode: RESUME from {offset_min:02d}:{offset_sec:02d} ({resume_from_seconds:.0f}s)")
    else:
        print("Mode: NEW transcription")

    # 3. Calcula duração para cobrança
    audio_duration = _get_wav_duration(audio_path)
    
    # 4. Inicializa o cliente OpenAI
    client = OpenAI(api_key=api_key)

    # 5. Prepara o prompt do glossário (ajuda a evitar alucinações de jargões técnicos)
    default_prompt = (
        "Transcrição industrial precisa. Termos: filme sublimático, extrusão de alumínio, lacagem."
    )
    selected_prompt = glossary if glossary else default_prompt

    print(f"Sending audio to OpenAI Whisper API...")
    
    # Inicializa o indicador visual na tela
    spinner = TerminalSpinner(label="Processando transcrição na OpenAI")
    spinner.start()

    try:
        with open(audio_path, "rb") as audio_file:
            # Requisita a transcrição com formato detalhado verbose_json
            response = client.audio.transcriptions.create(
                model=model_name,
                file=audio_file,
                response_format="verbose_json",
                prompt=selected_prompt,
                language="pt"  # Força a transcrição para Português
            )
    finally:
        spinner.stop()

    print(" \u2713 Transcrição na OpenAI concluída com sucesso!")

    # 6. Processa a resposta estruturando os timestamps por segmento
    formatted_lines = []
    # response no formato verbose_json traz a lista de segmentos sob o atributo 'segments'
    segments = getattr(response, "segments", [])

    for segment in segments:
        start = segment.get("start", 0.0)
        end = segment.get("end", 0.0)
        text = segment.get("text", "").strip()

        # Ajusta os timestamps baseando-se no offset do checkpoint
        start_adjusted = start + resume_from_seconds
        end_adjusted = end + resume_from_seconds

        start_min = int(start_adjusted // 60)
        start_sec = int(start_adjusted % 60)
        end_min = int(end_adjusted // 60)
        end_sec = int(end_adjusted % 60)

        # Whisper não possui diarização nativa, apenas adiciona o timestamp e a fala
        formatted_lines.append(
            f"[{start_min:02d}:{start_sec:02d} - {end_min:02d}:{end_sec:02d}] {text}"
        )

    transcript_text = "\n".join(formatted_lines)

    # 7. Cálculo de custo (US$ 0.006 por minuto de áudio)
    # A cobrança é feita por segundo proporcional
    cost_per_second = 0.006 / 60.0
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

    # 8. Salva o texto no arquivo final
    write_mode = "a" if is_resume else "w"
    print(f"Saving transcript to: {output_txt_path} (mode={write_mode})")
    with open(output_txt_path, write_mode, encoding="utf-8") as f:
        if is_resume:
            f.write("\n")
        f.write(transcript_text)

    print("Transcription process finished successfully.")
    return usage_data
