import os
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

def transcribe_audio_local(
    audio_path: str,
    output_txt_path: str,
    glossary: str = None,
    resume_from_seconds: float = 0.0
) -> dict:
    """
    Carrega o modelo Whisper local usando a biblioteca faster-whisper, executa a
    transcrição em CPU com otimização int8, ajusta os timestamps e salva o output.

    Args:
        audio_path (str): Caminho local para o arquivo de áudio.
        output_txt_path (str): Caminho do arquivo para salvar a transcrição.
        glossary (str, opcional): Termos de vocabulário passados no prompt.
        resume_from_seconds (float): Offset de tempo para retomar a transcrição.

    Returns:
        dict: Metadados contendo estatísticas de custo (zeradas) e uso.
    """
    # 1. Importação tardia da biblioteca para evitar lentidão ao iniciar o script principal
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise ImportError(
            "A biblioteca 'faster-whisper' não está instalada. "
            "Por favor, execute: pip install faster-whisper"
        )

    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Arquivo de áudio não encontrado: {audio_path}")

    # 2. Inicializa configurações de modelo do .env
    model_size = os.environ.get("LOCAL_WHISPER_MODEL", "base")
    print(f"Local Model Size: {model_size}")

    is_resume = resume_from_seconds > 0.0
    if is_resume:
        offset_min = int(resume_from_seconds // 60)
        offset_sec = int(resume_from_seconds % 60)
        print(f"Mode: LOCAL RESUME from {offset_min:02d}:{offset_sec:02d} ({resume_from_seconds:.0f}s)")
    else:
        print("Mode: LOCAL NEW transcription")

    audio_duration = _get_wav_duration(audio_path)

    # 3. Carrega o modelo Whisper em CPU
    print(f"Loading local Whisper model '{model_size}' onto CPU (this may take a moment)...")
    spinner_model = TerminalSpinner(label=f"Carregando Whisper Model ({model_size})")
    spinner_model.start()
    try:
        # device="cpu" e compute_type="float32" oferecem maior precisão matemática em CPU, prevenindo loops de alucinação
        model = WhisperModel(
            model_size,
            device="cpu",
            compute_type="float32",
            download_root=os.path.join(os.getcwd(), "models")  # Salva os modelos na pasta models/ do projeto
        )
    finally:
        spinner_model.stop()

    print(" \u2713 Modelo carregado com sucesso.")

    # 4. Configura glossário/prompts
    default_prompt = (
        "Transcrição industrial precisa. Termos: filme sublimático, extrusão de alumínio, lacagem."
    )
    selected_prompt = glossary if glossary else default_prompt

    print("Transcribing audio locally...")
    spinner_transcribe = TerminalSpinner(label="Processando áudio localmente no processador")
    spinner_transcribe.start()

    try:
        # model.transcribe retorna um gerador preguiçoso (lazy generator) de segmentos
        # Usamos vad_filter=True para remover silêncio/ruídos e impedir alucinações repetitivas.
        # temperature=0.0 força respostas factuais e previne alucinações criativas.
        segments, info = model.transcribe(
            audio_path,
            beam_size=5,
            language="pt",
            initial_prompt=selected_prompt,
            temperature=0.0,
            vad_filter=True
        )

        # Consumimos o gerador ativamente dentro do bloco try/finally para que o spinner funcione durante a CPU pesada
        segments_list = []
        for segment in segments:
            segments_list.append(segment)
    finally:
        spinner_transcribe.stop()

    print(" \u2713 Transcrição concluída localmente!")

    # 5. Formata os segmentos com os timestamps ajustados pelo resume
    formatted_lines = []
    for segment in segments_list:
        start = segment.start
        end = segment.end
        text = segment.text.strip()

        # Ajusta os timestamps baseando-se no offset do checkpoint
        start_adjusted = start + resume_from_seconds
        end_adjusted = end + resume_from_seconds

        start_min = int(start_adjusted // 60)
        start_sec = int(start_adjusted % 60)
        end_min = int(end_adjusted // 60)
        end_sec = int(end_adjusted % 60)

        # Sem diarização nativa
        formatted_lines.append(
            f"[{start_min:02d}:{start_sec:02d} - {end_min:02d}:{end_sec:02d}] {text}"
        )

    transcript_text = "\n".join(formatted_lines)

    # 6. Metadados de retorno (custo local é zero)
    usage_data = {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "cost_input_usd": 0.0,
        "cost_output_usd": 0.0,
        "total_cost_usd": 0.0,
        "transcript": transcript_text,
    }

    # 7. Salva a transcrição no arquivo final
    write_mode = "a" if is_resume else "w"
    print(f"Saving transcript to: {output_txt_path} (mode={write_mode})")
    with open(output_txt_path, write_mode, encoding="utf-8") as f:
        if is_resume:
            f.write("\n")
        f.write(transcript_text)

    print("Local transcription process finished successfully.")
    return usage_data
