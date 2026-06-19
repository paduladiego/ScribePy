import os
import sys

# Carrega variáveis de ambiente do arquivo .env local
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Configura o caminho do FFmpeg automaticamente no Windows/Mac/Linux
try:
    import static_ffmpeg
    static_ffmpeg.add_paths()
except ImportError:
    pass

from audio_processor import preprocess_audio, get_wav_duration, slice_wav
from transcriber_gemini import transcribe_audio_with_gemini, get_resume_offset


def run_pipeline(input_audio_path: str, custom_glossary: str = None) -> None:
    """
    Orquestra o pipeline completo do ScribePy com suporte a checkpoint e resume:

    1. Verifica se o WAV já existe (pula Stage 1 se sim).
    2. Verifica o estado do transcript (completo, parcial ou inexistente).
    3. Em modo resume, fatia o áudio a partir do último timestamp com overlap de 10s.
    4. Transcreve e anexa ao transcript existente, ou transcreve do zero.
    5. Deleta o WAV SOMENTE após confirmação do marcador '--- FIM ---'.

    Args:
        input_audio_path (str): Caminho para o arquivo de áudio de entrada (ex: .m4a).
        custom_glossary (str, optional): Termos técnicos customizados para o Gemini.
    """
    if not os.path.exists(input_audio_path):
        print(f"Error: Input audio file '{input_audio_path}' does not exist.")
        sys.exit(1)

    base_name        = os.path.splitext(input_audio_path)[0]
    temp_wav_path    = f"{base_name}_clean.wav"
    resume_wav_path  = f"{base_name}_resume.wav"
    output_txt_path  = f"{base_name}_transcript.txt"

    # Sobreposição de 10s ao retomar — garante continuidade no meio de uma frase
    OVERLAP_SECONDS = 10
    # Taxa de câmbio USD -> BRL (atualize conforme necessário)
    USD_TO_BRL      = 6.00

    print("=" * 60)
    print("SCRIBEPY v3 — Smart Resume & Checkpoint Pipeline")
    print("=" * 60)
    print(f"Input File:        {input_audio_path}")
    print(f"Intermediate WAV:  {temp_wav_path}")
    print(f"Final Transcript:  {output_txt_path}")
    print("-" * 60)

    # -------------------------------------------------------------------------
    # CHECKPOINT: verifica o estado do transcript antes de qualquer processamento
    # -------------------------------------------------------------------------
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
    # Prepara o áudio para o Stage 2 (completo ou fatiado para resume)
    # -------------------------------------------------------------------------
    if resume_offset > 0.0:
        # Modo resume: recua OVERLAP_SECONDS para garantir contexto de continuidade
        slice_start_seconds = max(0.0, resume_offset - OVERLAP_SECONDS)
        print(f"\n[RESUME] Slicing audio from {slice_start_seconds:.0f}s "
              f"(offset {resume_offset:.0f}s - {OVERLAP_SECONDS}s overlap)")
        slice_wav(temp_wav_path, slice_start_seconds, resume_wav_path)
        # O áudio a ser enviado é o trecho fatiado, não o completo
        audio_to_upload        = resume_wav_path
        resume_for_transcriber = slice_start_seconds
    else:
        # Modo normal: envia o WAV completo
        audio_to_upload        = temp_wav_path
        resume_for_transcriber = 0.0

    # -------------------------------------------------------------------------
    # STAGE 2: transcrição e diarização via Gemini API
    # -------------------------------------------------------------------------
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

    except Exception as e:
        print(f"\nPipeline Error occurred: {e}")

    finally:
        # Remove o arquivo de resume temporário, se foi criado
        if os.path.exists(resume_wav_path):
            try:
                os.remove(resume_wav_path)
            except Exception:
                pass

    # -------------------------------------------------------------------------
    # STAGE 3: finalização e relatório de custo
    # -------------------------------------------------------------------------
    if not transcript_complete:
        # Falha no Stage 2 — preserva o WAV para permitir nova tentativa
        print("\n[CHECKPOINT] Stage 2 failed. WAV file preserved for next run:")
        print(f"  {temp_wav_path}")
        print("  Re-run the app to resume transcription automatically.")
        print("=" * 60)
        sys.exit(1)

    print("\n--- STAGE 3: Finalizing ---")
    print(f"Success! Your transcript is ready: {output_txt_path}")

    # Relatório de custo e tokens
    duration_min = int(audio_duration_seconds // 60)
    duration_sec = int(audio_duration_seconds % 60)
    total_cost_brl = usage_data["total_cost_usd"] * USD_TO_BRL

    print("\n" + "=" * 60)
    print(" \U0001f4b0  TOKEN & COST REPORT")
    print("=" * 60)
    print(f"  Audio Duration:    {duration_min:02d}:{duration_sec:02d} ({audio_duration_seconds:.0f}s)")
    print(f"  Input Tokens:      {usage_data['input_tokens']:>10,}")
    print(f"  Output Tokens:     {usage_data['output_tokens']:>10,}")
    print(f"  Total Tokens:      {usage_data['total_tokens']:>10,}")
    print("-" * 60)
    print(f"  Cost (Input):      USD ${usage_data['cost_input_usd']:.6f}")
    print(f"  Cost (Output):     USD ${usage_data['cost_output_usd']:.6f}")
    print(f"  Total Cost:        USD ${usage_data['total_cost_usd']:.6f}  |  R$ {total_cost_brl:.4f}")
    print(f"  Exchange Rate:     1 USD = R$ {USD_TO_BRL:.2f}")
    print("=" * 60)

    # Deleta o WAV somente após transcrição confirmada como completa (tem marcador FIM)
    # Dupla verificação no arquivo salvo para garantir integridade
    try:
        with open(output_txt_path, "r", encoding="utf-8") as f:
            saved_content = f.read()
        is_confirmed_complete = "--- FIM ---" in saved_content
    except Exception:
        is_confirmed_complete = False

    if is_confirmed_complete and os.path.exists(temp_wav_path):
        print(f"Cleaning up local intermediate file: {temp_wav_path}")
        try:
            os.remove(temp_wav_path)
        except Exception as e:
            print(f"Warning: Could not remove WAV file: {e}")
    elif os.path.exists(temp_wav_path):
        print(f"[CHECKPOINT] WAV preserved (transcript may be incomplete): {temp_wav_path}")

    print("=" * 60)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python main.py <input_audio_file> [custom_glossary]")
        print("Example: python main.py meeting.m4a")
        sys.exit(1)

    input_file   = sys.argv[1]
    glossary_arg = sys.argv[2] if len(sys.argv) > 2 else None

    # Carrega automaticamente o glossario.txt da raiz se nenhum glossário for passado
    if not glossary_arg:
        glossary_file_path = "glossario.txt"
        if os.path.exists(glossary_file_path):
            print(f"Detecting local glossary file: {glossary_file_path}")
            try:
                with open(glossary_file_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        print("Custom glossary successfully loaded.")
                        glossary_arg = content
            except Exception as e:
                print(f"Warning: Could not read glossary file: {e}")

    run_pipeline(input_file, glossary_arg)
