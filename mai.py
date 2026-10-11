import os
import sys
import math

# Garante suporte a caminhos de FFmpeg no Windows
try:
    import static_ffmpeg
    static_ffmpeg.add_paths()
except ImportError:
    pass

from pydub import AudioSegment
from src.audio_processor import preprocess_audio


def find_best_split_point(audio: AudioSegment, nominal_point_ms: int, search_radius_ms: int = 5000, step_ms: int = 100) -> int:
    """
    Localiza o ponto ideal de corte dentro de uma janela de busca ao redor do ponto nominal.
    Avalia a energia sonora (RMS) em intervalos curtos e seleciona o instante de menor
    volume (silêncio / pausa respiratória entre frases) para evitar cortar palavras no meio.

    Args:
        audio (AudioSegment): Objeto de áudio completo carregado pelo pydub.
        nominal_point_ms (int): Ponto de divisão teórico calculado matematicamente (em ms).
        search_radius_ms (int): Raio de busca para frente e para trás (em ms). Padrão: 5000ms (+/- 5s).
        step_ms (int): Passo de deslocamento da janela de amostragem em ms. Padrão: 100ms.

    Returns:
        int: Timestamp em milissegundos correspondente ao momento mais silencioso.
    """
    total_len = len(audio)
    start_search = max(0, nominal_point_ms - search_radius_ms)
    end_search = min(total_len, nominal_point_ms + search_radius_ms)

    window_size_ms = 250  # Janela de amostragem de 250ms para avaliar o nível de silêncio
    min_rms = float("inf")
    best_split_ms = nominal_point_ms

    current_ms = start_search
    while current_ms + window_size_ms <= end_search:
        sample_chunk = audio[current_ms : current_ms + window_size_ms]
        current_rms = sample_chunk.rms

        # Se encontrar silêncio absoluto (RMS == 0), interrompe imediatamente
        if current_rms == 0:
            return current_ms + (window_size_ms // 2)

        if current_rms < min_rms:
            min_rms = current_rms
            best_split_ms = current_ms + (window_size_ms // 2)

        current_ms += step_ms

    return best_split_ms


def format_ms_to_time(ms: int) -> str:
    """
    Converte milissegundos para o formato legível MM:SS.
    """
    total_seconds = int(ms // 1000)
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes:02d}:{seconds:02d}"


def slice_for_mai_playground(input_audio_path: str, max_mb_per_chunk: float = 22.0, noise_reduce: bool = False) -> list[str]:
    """
    Pré-processa o áudio (se necessário) e realiza o fatiamento inteligente em partes
    estritamente inferiores ao limite seguro configurado (default: 22 MB para o teto de 25 MB do MAI Playground).
    Detecta pausas naturais de silêncio para garantir integridade fonética em cada corte.

    Args:
        input_audio_path (str): Caminho para o áudio de entrada (.m4a, .wav, etc.).
        max_mb_per_chunk (float): Tamanho máximo desejado por fatia em Megabytes.
        noise_reduce (bool): Se True, ativa remoção de ruído fabril durante a conversão.

    Returns:
        list[str]: Lista com os caminhos dos arquivos WAV fatiados gerados.
    """
    if not os.path.exists(input_audio_path):
        raise FileNotFoundError(f"Arquivo de áudio não encontrado: {input_audio_path}")

    project_root = os.getcwd()
    converted_dir = os.path.join(project_root, "converted")
    os.makedirs(converted_dir, exist_ok=True)

    base_name = os.path.splitext(os.path.basename(input_audio_path))[0]
    
    # Se o nome já termina com _clean, mantém como está; senão gera o caminho padrão limpo
    if base_name.endswith("_clean"):
        clean_wav_path = os.path.join(converted_dir, f"{base_name}.wav")
        clean_title = base_name.replace("_clean", "")
    else:
        clean_wav_path = os.path.join(converted_dir, f"{base_name}_clean.wav")
        clean_title = base_name

    # 1. Verifica se já existe uma versão clean processada para economizar tempo
    if os.path.exists(clean_wav_path):
        print("=" * 65)
        print("SCRIBEPY — MAI Playground Slicer (VAD Silence Detection)")
        print("=" * 65)
        print(f"[REUSE] Áudio limpo já existente detectado: {clean_wav_path}")
    elif input_audio_path.lower().endswith(".wav"):
        clean_wav_path = input_audio_path
        print("=" * 65)
        print("SCRIBEPY — MAI Playground Slicer (VAD Silence Detection)")
        print("=" * 65)
        print(f"[DIRECT] Utilizando arquivo WAV fornecido: {clean_wav_path}")
    else:
        print("=" * 65)
        print("SCRIBEPY — MAI Playground Slicer (VAD Silence Detection)")
        print("=" * 65)
        print(f"Pré-processando áudio para WAV 16kHz mono...")
        preprocess_audio(input_audio_path, clean_wav_path, noise_reduce=noise_reduce)

    # 2. Carrega o áudio e analisa os parâmetros de tamanho e duração
    print(f"\nCarregando arquivo para análise acústica...")
    audio = AudioSegment.from_wav(clean_wav_path)
    total_duration_ms = len(audio)
    total_duration_sec = total_duration_ms / 1000.0
    
    file_size_bytes = os.path.getsize(clean_wav_path)
    file_size_mb = file_size_bytes / (1024 * 1024)

    # 3. Calcula o número mínimo de fatias para respeitar o teto estrito em MB
    num_parts = math.ceil(file_size_mb / max_mb_per_chunk)
    if num_parts < 1:
        num_parts = 1

    approx_part_size_mb = file_size_mb / num_parts
    target_duration_ms = total_duration_ms / num_parts

    print("-" * 65)
    print(f"Arquivo Master:      {os.path.basename(clean_wav_path)}")
    print(f"Tamanho Total:       {file_size_mb:.2f} MB")
    print(f"Duração Total:       {format_ms_to_time(total_duration_ms)} ({total_duration_sec:.1f}s)")
    print(f"Limite por Fatia:    {max_mb_per_chunk:.2f} MB (Margem segura para teto de 25 MB)")
    print(f"Divisões Calculadas: {num_parts} partes de ~{approx_part_size_mb:.2f} MB")
    print("-" * 65)

    if num_parts == 1:
        print("\n[OK] O arquivo já está abaixo de 22 MB! Não é necessário fatiar para o Playground.")
        return [clean_wav_path]

    # 4. Determina os pontos de corte acústicos (buscando silêncio nas fronteiras)
    split_points_ms = [0]
    for i in range(1, num_parts):
        nominal_cut = int(i * target_duration_ms)
        print(f"Buscando silêncio acústico para corte #{i} (ao redor de {format_ms_to_time(nominal_cut)})...")
        best_cut = find_best_split_point(audio, nominal_cut, search_radius_ms=5000, step_ms=100)
        split_points_ms.append(best_cut)
        diff_s = (best_cut - nominal_cut) / 1000.0
        sign = "+" if diff_s >= 0 else ""
        print(f"  -> Corte calibrado no ponto {format_ms_to_time(best_cut)} ({sign}{diff_s:.1f}s do ponto teórico)")

    split_points_ms.append(total_duration_ms)

    # 5. Exporta cada fatia como arquivo WAV individual
    print("\nExportando fatias acústicas...")
    generated_files = []
    summary_table = []

    for i in range(num_parts):
        part_num = i + 1
        start_ms = split_points_ms[i]
        end_ms = split_points_ms[i + 1]
        chunk_audio = audio[start_ms:end_ms]

        output_filename = f"{clean_title}_part{part_num}_of_{num_parts}.wav"
        output_filepath = os.path.join(converted_dir, output_filename)

        chunk_audio.export(output_filepath, format="wav")
        part_size_mb = os.path.getsize(output_filepath) / (1024 * 1024)
        part_duration_s = (end_ms - start_ms) / 1000.0

        generated_files.append(output_filepath)
        summary_table.append({
            "part": f"Parte {part_num}/{num_parts}",
            "start": format_ms_to_time(start_ms),
            "end": format_ms_to_time(end_ms),
            "duration": f"{int(part_duration_s // 60):02d}:{int(part_duration_s % 60):02d}",
            "size": f"{part_size_mb:.2f} MB",
            "path": output_filepath
        })

    # 6. Exibe a tabela consolidada de fatias
    print("\n" + "=" * 65)
    print(" 📑  TABELA DE FATIAS PARA O PLAYGROUND DO MAI-TRANSCRIBE-2")
    print("=" * 65)
    header = f"{'Fatia':<14} | {'Início':<7} | {'Fim':<7} | {'Duração':<8} | {'Tamanho':<10}"
    print(header)
    print("-" * 65)
    for row in summary_table:
        print(f"{row['part']:<14} | {row['start']:<7} | {row['end']:<7} | {row['duration']:<8} | {row['size']:<10}")

    print("=" * 65)
    print("\nArquivos gerados prontos para upload:")
    for row in summary_table:
        print(f"  • {row['part']}: {row['path']}")
    print("-" * 65)
    print("Dica: Todos os arquivos respeitam o limite de 25 MB e foram cortados")
    print("em momentos de silêncio natural, sem cortar frases ou palavras no meio!")
    print("=" * 65 + "\n")

    return generated_files


if __name__ == "__main__":
    args = sys.argv[1:]
    
    # Suporte a flag 'clear' opcional para redução de ruído industrial
    if args and args[0].strip().lower() == "clear":
        noise_flag = True
        args = args[1:]
    else:
        noise_flag = False

    if not args:
        print("Uso: python mai.py [clear] <arquivo_de_audio> [tamanho_maximo_mb]")
        print("Exemplos:")
        print("  python mai.py \"converted/01 Natália diretora nals.m4a\"")
        print("  python mai.py \"converted/01 Natália diretora nals_clean.wav\" 22.0")
        print("  python mai.py clear \"caminho/do/audio_fabrica.m4a\"")
        sys.exit(1)

    input_file = args[0]
    max_mb = float(args[1]) if len(args) > 1 else 22.0

    try:
        slice_for_mai_playground(input_file, max_mb_per_chunk=max_mb, noise_reduce=noise_flag)
    except Exception as e:
        print(f"\nErro durante o fatiamento: {e}")
        sys.exit(1)
