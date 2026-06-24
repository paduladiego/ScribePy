import os

def transcribe_audio(
    audio_path: str,
    output_txt_path: str,
    glossary: str = None,
    resume_from_seconds: float = 0.0
) -> dict:
    """
    Função de fachada (Facade/Dispatcher) que decide a rota de transcrição com base
    nas variáveis de ambiente configuradas no arquivo .env (TRANSCRIPTION_MODE e API_PROVIDER).

    Args:
        audio_path (str): Caminho local para o arquivo de áudio.
        output_txt_path (str): Caminho do arquivo para salvar a transcrição.
        glossary (str, opcional): Termos do glossário.
        resume_from_seconds (float): Offset de tempo caso seja retomada.

    Returns:
        dict: Metadados padronizados contendo estatísticas de uso e custo.
    """
    # 1. Lê a rota e o provedor do arquivo .env
    transcription_mode = os.environ.get("TRANSCRIPTION_MODE", "API").strip().upper()
    api_provider       = os.environ.get("API_PROVIDER", "GEMINI").strip().upper()

    print("-" * 60)
    print(f"TRANSCRIPTION ROUTER: Mode={transcription_mode} | Provider={api_provider if transcription_mode == 'API' else 'N/A'}")
    print("-" * 60)

    # 2. Roteia para o arquivo .py correspondente usando importações sob demanda (lazy imports)
    if transcription_mode == "LOCAL":
        from .transcriber_local import transcribe_audio_local
        return transcribe_audio_local(
            audio_path=audio_path,
            output_txt_path=output_txt_path,
            glossary=glossary,
            resume_from_seconds=resume_from_seconds
        )
    elif transcription_mode == "API":
        if api_provider == "GEMINI":
            from .transcriber_gemini import transcribe_audio_with_gemini
            return transcribe_audio_with_gemini(
                audio_path=audio_path,
                output_txt_path=output_txt_path,
                glossary=glossary,
                resume_from_seconds=resume_from_seconds
            )
        elif api_provider == "OPENAI":
            from .transcriber_openai import transcribe_audio_with_openai
            return transcribe_audio_with_openai(
                audio_path=audio_path,
                output_txt_path=output_txt_path,
                glossary=glossary,
                resume_from_seconds=resume_from_seconds
            )

        else:
            raise ValueError(
                f"Provedor de API inválido: '{api_provider}'. "
                "Opções aceitas no .env: GEMINI ou OPENAI."
            )
    else:
        raise ValueError(
            f"Modo de transcrição inválido: '{transcription_mode}'. "
            "Opções aceitas no .env: API ou LOCAL."
        )
