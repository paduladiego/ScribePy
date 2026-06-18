import os
import sys

# Load environment variables from local .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Automatically configure FFmpeg path on Windows/Mac/Linux
try:
    import static_ffmpeg
    static_ffmpeg.add_paths()
except ImportError:
    pass

from audio_processor import preprocess_audio
from transcriber_gemini import transcribe_audio_with_gemini

def run_pipeline(input_audio_path: str, custom_glossary: str = None) -> None:
    """
    Orchestrates the entire ScribePy pipeline:
    1. Validates input files.
    2. Runs audio preprocessing (noise reduction, conversion to WAV 16kHz mono).
    3. Uploads the processed audio to Gemini, transcribes it with diarization and context.
    4. Cleans up intermediate WAV files.
    
    Args:
        input_audio_path (str): Path to the source audio file (e.g. .m4a from S24 Ultra).
        custom_glossary (str, optional): Custom technical terms/context for Gemini.
    """
    if not os.path.exists(input_audio_path):
        print(f"Error: Input audio file '{input_audio_path}' does not exist.")
        sys.exit(1)
        
    base_name = os.path.splitext(input_audio_path)[0]
    temp_wav_path = f"{base_name}_clean.wav"
    output_txt_path = f"{base_name}_transcript.txt"
    
    print("=" * 60)
    print("SCRIBEPY PIPELINE: Audio Preprocessing & Intelligent Transcription")
    print("=" * 60)
    print(f"Input File:        {input_audio_path}")
    print(f"Intermediate WAV:  {temp_wav_path}")
    print(f"Final Transcript:  {output_txt_path}")
    print("-" * 60)
    
    try:
        # Step 1: Preprocess Audio (Convert, Normalize, Noise reduction)
        print("\n--- STAGE 1: Audio Processing ---")
        preprocess_audio(input_audio_path, temp_wav_path)
        
        # Step 2: Transcribe and Diarize with Gemini 1.5
        print("\n--- STAGE 2: Contextual Transcription via Gemini API ---")
        transcribe_audio_with_gemini(
            audio_path=temp_wav_path,
            output_txt_path=output_txt_path,
            glossary=custom_glossary
        )
        
        print("\n--- STAGE 3: Finalizing ---")
        print(f"Success! Your transcript is ready: {output_txt_path}")
        
    except Exception as e:
        print(f"\nPipeline Error occurred: {e}")
        sys.exit(1)
        
    finally:
        # Step 4: Cleanup local intermediate WAV file to save disk space
        if os.path.exists(temp_wav_path):
            print(f"Cleaning up local intermediate file: {temp_wav_path}")
            try:
                os.remove(temp_wav_path)
            except Exception as e:
                print(f"Warning: Could not remove temporary WAV file: {e}")
                
    print("=" * 60)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python main.py <input_audio_file> [custom_glossary]")
        print("Example: python main.py meeting.m4a")
        sys.exit(1)
        
    input_file = sys.argv[1]
    glossary_arg = sys.argv[2] if len(sys.argv) > 2 else None
    
    # Automatically load glossary.txt from root if no command line glossary is provided
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
