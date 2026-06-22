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

from src.pipeline import run_pipeline

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

    try:
        run_pipeline(input_file, glossary_arg)
    except Exception as e:
        print(f"\nPipeline Execution Failed: {e}")
        sys.exit(1)
