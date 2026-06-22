import os
import sys

from .audio_processor import preprocess_audio, get_wav_duration, slice_wav
from .transcriber_gemini import transcribe_audio_with_gemini, get_resume_offset, clean_transcript_residue

def run_pipeline(input_audio_path: str, custom_glossary: str = None) -> None:
    """
    Orquestra o pipeline completo do ScribePy com suporte a checkpoint e resume.
    Desacoplado de argumentos de CLI (sys.argv) e sys.exit() para suportar futuros front-ends.

    Args:
        input_audio_path (str): Caminho para o arquivo de áudio de entrada (ex: .m4a).
        custom_glossary (str, optional): Termos técnicos customizados para o Gemini.
    """
    if not os.path.exists(input_audio_path):
        raise FileNotFoundError(f"Input audio file '{input_audio_path}' does not exist.")

    project_root     = os.getcwd()
    converted_dir    = os.path.join(project_root, "converted")
    os.makedirs(converted_dir, exist_ok=True)

    file_title       = os.path.splitext(os.path.basename(input_audio_path))[0]
    temp_wav_path    = os.path.join(converted_dir, f"{file_title}_clean.wav")
    resume_wav_path  = os.path.join(converted_dir, f"{file_title}_resume.wav")
    output_txt_path  = os.path.join(converted_dir, f"{file_title}_transcript.txt")

    # Sobreposição de 10s ao retomar — garante continuidade no meio de uma frase
    OVERLAP_SECONDS = 10
    # Taxa de câmbio USD -> BRL (atualize conforme necessário)
    USD_TO_BRL      = 6.00

    print("=" * 60)
    print("SCRIBEPY — Smart Resume & Checkpoint Pipeline")
    print("=" * 60)
    print(f"Input File:        {input_audio_path}")
    print(f"Intermediate WAV:  {temp_wav_path}")
    print(f"Final Transcript:  {output_txt_path}")
    print("-" * 60)

    # -------------------------------------------------------------------------
    # CHECKPOINT: limpa residuos de travamento anterior e verifica o estado do transcript
    # -------------------------------------------------------------------------
    clean_transcript_residue(output_txt_path)
    resume_offset = get_resume_offset(output_txt_path)

    if resume_offset == -1.0:
        # Transcript já está completo — encerra sem custo algum
        print("\n[CHECKPOINT] Transcript already complete! ('--- FIM ---' found)")
        print(f"[CHECKPOINT] Nothing to do. File: {output_txt_path}")
        print("=" * 60)
        return

    if resume_offset > 0.0:
        offset_min = int(resume_offset // 60)
        offset_sec = int(resume_offset % 60)
        print(f"\n[CHECKPOINT] Incomplete transcript detected.")
        print(f"[CHECKPOINT] Last timestamp: {offset_min:02d}:{offset_sec:02d} — resuming from there.")
    else:
        print("\n[CHECKPOINT] No transcript found — starting fresh.")

    # -------------------------------------------------------------------------
    # STAGE 1: pré-processamento de áudio (pula se o WAV já existir)
    # -------------------------------------------------------------------------
    print("\n--- STAGE 1: Audio Processing ---")

    if os.path.exists(temp_wav_path):
        # WAV existente reutilizado — Stage 1 pulado para economizar tempo
        audio_duration_seconds = get_wav_duration(temp_wav_path)
        duration_min = int(audio_duration_seconds // 60)
        duration_sec = int(audio_duration_seconds % 60)
        print(f"[SKIP] WAV file already exists: {temp_wav_path}")
        print(f"[SKIP] Reusing existing processed audio. Duration: {duration_min:02d}:{duration_sec:02d}")
    else:
        # WAV não encontrado — executa o pré-processamento completo
        _, audio_duration_seconds = preprocess_audio(input_audio_path, temp_wav_path)

    # -------------------------------------------------------------------------
    # Loop de transcrição adaptativo para cobrir 100% do arquivo
    # -------------------------------------------------------------------------
    previous_offset = -1.0
    accumulated_usage = {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "cost_input_usd": 0.0,
        "cost_output_usd": 0.0,
        "total_cost_usd": 0.0,
    }
    chunk_count = 0

    while True:
        # 1. Verifica offset atual no arquivo
        resume_offset = get_resume_offset(output_txt_path)

        if resume_offset == -1.0:
            print("\n[CHECKPOINT] Transcript already complete! ('--- FIM ---' found)")
            break

        # 2. Verifica proximidade com o fim do áudio (limiar de 15 segundos para cobrir 100% dos minutos)
        if resume_offset > 0.0 and (audio_duration_seconds - resume_offset) < 15.0:
            print(f"\n[COMPLETE] Last timestamp ({resume_offset:.1f}s) is close to total audio duration ({audio_duration_seconds:.1f}s).")
            print("Marking transcript as complete.")
            with open(output_txt_path, "a", encoding="utf-8") as f:
                f.write("\n\n--- FIM ---\n")
            break

        # 3. Evita loop infinito se não houver progresso na transcrição
        if previous_offset != -1.0 and resume_offset <= previous_offset:
            raise RuntimeError(f"No progress made in transcription (stuck at {resume_offset:.1f}s). Aborting to prevent loop.")

        previous_offset = resume_offset
        chunk_count += 1
        print("-" * 60)
        print(f"TRANSCRIPTION CHUNK #{chunk_count}")
        print("-" * 60)

        # 4. Prepara o áudio slice (completo ou fatiado)
        if resume_offset > 0.0:
            slice_start_seconds = max(0.0, resume_offset - OVERLAP_SECONDS)
            print(f"[RESUME] Slicing audio from {slice_start_seconds:.0f}s "
                  f"(offset {resume_offset:.0f}s - {OVERLAP_SECONDS}s overlap)")
            slice_wav(temp_wav_path, slice_start_seconds, resume_wav_path)
            audio_to_upload        = resume_wav_path
            resume_for_transcriber = slice_start_seconds
        else:
            audio_to_upload        = temp_wav_path
            resume_for_transcriber = 0.0

        # 5. Executa a transcrição do bloco
        print("\n--- STAGE 2: Contextual Transcription via Gemini API ---")
        transcript_complete = False
        try:
            usage_data = transcribe_audio_with_gemini(
                audio_path=audio_to_upload,
                output_txt_path=output_txt_path,
                glossary=custom_glossary,
                resume_from_seconds=resume_for_transcriber
            )
            transcript_complete = True

            # Acumula metadados de tokens e custo
            accumulated_usage["input_tokens"] += usage_data["input_tokens"]
            accumulated_usage["output_tokens"] += usage_data["output_tokens"]
            accumulated_usage["total_tokens"] += usage_data["total_tokens"]
            accumulated_usage["cost_input_usd"] += usage_data["cost_input_usd"]
            accumulated_usage["cost_output_usd"] += usage_data["cost_output_usd"]
            accumulated_usage["total_cost_usd"] += usage_data["total_cost_usd"]

        except Exception as e:
            print(f"\nPipeline Error occurred during chunk transcription: {e}")
            break
        finally:
            # Removido/comentado a delecao do arquivo de slice temporario — o usuario limpa depois
            # from .cleaner import AudioCleaner
            # if os.path.exists(resume_wav_path):
            #     AudioCleaner.delete_file(resume_wav_path)
            pass

        if not transcript_complete:
            raise RuntimeError("Stage 2 chunk failed. WAV file preserved for next run.")

    # -------------------------------------------------------------------------
    # STAGE 3: finalização e relatório de custo acumulado
    # -------------------------------------------------------------------------
    # Verifica se de fato está completo no arquivo final
    try:
        with open(output_txt_path, "r", encoding="utf-8") as f:
            saved_content = f.read()
        is_confirmed_complete = "--- FIM ---" in saved_content
    except Exception:
        is_confirmed_complete = False

    if not is_confirmed_complete:
        raise RuntimeError("Pipeline execution finished but '--- FIM ---' was not written/confirmed.")

    print("\n--- STAGE 3: Finalizing ---")
    print(f"Success! Your transcript is ready: {output_txt_path}")

    # Relatório de custo consolidado (todos os blocos executados nessa sessão)
    duration_min = int(audio_duration_seconds // 60)
    duration_sec = int(audio_duration_seconds % 60)
    total_cost_brl = accumulated_usage["total_cost_usd"] * USD_TO_BRL

    print("\n" + "=" * 60)
    print(" 💰  TOTAL TOKEN & COST REPORT (All chunks)")
    print("=" * 60)
    print(f"  Audio Duration:    {duration_min:02d}:{duration_sec:02d} ({audio_duration_seconds:.0f}s)")
    print(f"  Input Tokens:      {accumulated_usage['input_tokens']:>10,}")
    print(f"  Output Tokens:     {accumulated_usage['output_tokens']:>10,}")
    print(f"  Total Tokens:      {accumulated_usage['total_tokens']:>10,}")
    print("-" * 60)
    print(f"  Cost (Input):      USD ${accumulated_usage['cost_input_usd']:.6f}")
    print(f"  Cost (Output):     USD ${accumulated_usage['cost_output_usd']:.6f}")
    print(f"  Total Cost:        USD ${accumulated_usage['total_cost_usd']:.6f}  |  R$ {total_cost_brl:.4f}")
    print(f"  Exchange Rate:     1 USD = R$ {USD_TO_BRL:.2f}")
    print("=" * 60)

    # Removido/comentado a delecao do WAV completo — o usuario limpa depois usando o script de limpeza
    # from .cleaner import AudioCleaner
    # if os.path.exists(temp_wav_path):
    #     print(f"Cleaning up local intermediate file: {temp_wav_path}")
    #     AudioCleaner.delete_file(temp_wav_path)

    print("=" * 60)
