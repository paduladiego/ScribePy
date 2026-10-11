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
    # Detecta se a flag 'clear' foi passada como primeiro argumento da CLI
    # Uso: python main.py clear "audio.m4a"  -> ativa redução de ruído industrial
    # Uso: python main.py "audio.m4a"        -> apenas converte (ideal para escritório)
    args = sys.argv[1:]
    
    # Verifica se o primeiro argumento é a flag de modo 'clear'
    if args and args[0].strip().lower() == "clear":
        noise_reduce_flag = True
        args = args[1:]  # Remove a flag da lista, o restante são arquivo e glossário
    else:
        noise_reduce_flag = False

    if not args:
        print("Usage: python main.py [clear] <input_audio_file>")
        print("  clear       -> Ativa redução de ruído industrial (chao de fab rica/fábrica)")
        print("  (sem flag)  -> Apenas converte e normaliza (escritorio/ambiente silencioso)")
        print("")
        print("Exemplos:")
        print("  python main.py meeting.m4a")
        print("  python main.py clear factory_audio.m4a")
        sys.exit(1)

    input_file   = args[0]
    glossary_arg = args[1] if len(args) > 1 else None

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
        run_pipeline(input_file, glossary_arg, noise_reduce=noise_reduce_flag)
    except Exception as e:
        print(f"\nPipeline Execution Failed: {e}")
        sys.exit(1)
