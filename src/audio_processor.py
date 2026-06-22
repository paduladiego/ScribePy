import os
import numpy as np
from pydub import AudioSegment
import noisereduce as nr
import soundfile as sf


def preprocess_audio(input_path: str, output_path: str) -> tuple[str, float]:
    """
    Converte o áudio de entrada (ex: .m4a) para WAV 16kHz mono, aplica redução de ruído
    para suprimir o ruído industrial de fundo e normaliza o sinal de voz.

    Args:
        input_path (str): Caminho para o arquivo de áudio de entrada.
        output_path (str): Caminho onde o arquivo WAV processado será salvo.

    Returns:
        tuple[str, float]: Caminho do arquivo processado e duração em segundos.
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input audio file not found: {input_path}")

    print(f"Loading audio file: {input_path}")

    # Carrega o áudio usando pydub
    audio_format = os.path.splitext(input_path)[1].replace(".", "").lower()
    audio = AudioSegment.from_file(input_path, format=audio_format)

    # Converte para 16kHz, mono
    print("Converting audio to 16kHz, mono...")
    audio = audio.set_frame_rate(16000).set_channels(1)

    # Normaliza o ganho para maximizar o sinal de voz antes do processamento
    print("Normalizing audio volume...")
    audio = audio.normalize()

    # Converte o AudioSegment do pydub para array numpy para o noisereduce
    samples = np.array(audio.get_array_of_samples())

    # Converte a largura de amostra para float32 entre -1.0 e 1.0
    if audio.sample_width == 2:
        samples = samples.astype(np.float32) / 32768.0
    elif audio.sample_width == 4:
        samples = samples.astype(np.float32) / 2147483648.0
    else:
        samples = samples.astype(np.float32) / 128.0  # fallback para áudio 8-bit

    sample_rate = audio.frame_rate

    print("Applying noise reduction...")
    # Redução de ruído não-estacionário — ideal para ambientes industriais complexos
    reduced_noise = nr.reduce_noise(
        y=samples,
        sr=sample_rate,
        stationary=False,
        prop_decrease=0.85,
        use_tqdm=True
    )

    # Calcula a duração do áudio em segundos antes de salvar
    audio_duration_seconds = len(reduced_noise) / sample_rate

    # Salva o array numpy processado como um arquivo WAV padrão de 16kHz
    print(f"Saving processed clean audio to: {output_path}")
    sf.write(output_path, reduced_noise, sample_rate, subtype='PCM_16')

    print(f"Audio processing completed successfully. Duration: {audio_duration_seconds:.1f}s")
    # Retorna o caminho do arquivo e a duração para o cálculo de custo
    return output_path, audio_duration_seconds


def get_wav_duration(wav_path: str) -> float:
    """
    Retorna a duração de um arquivo WAV existente em segundos,
    sem precisar reprocessar o áudio. Usado no modo de checkpoint/resume.

    Args:
        wav_path (str): Caminho para o arquivo WAV.

    Returns:
        float: Duração em segundos.
    """
    # soundfile.info lê apenas o cabeçalho do arquivo — operação muito rápida
    info = sf.info(wav_path)
    return float(info.duration)


def slice_wav(wav_path: str, start_seconds: float, output_path: str) -> str:
    """
    Extrai um trecho do arquivo WAV a partir de start_seconds até o final.
    Usado no modo resume para evitar retranscrição do áudio já processado.

    Args:
        wav_path (str): Caminho para o arquivo WAV completo.
        start_seconds (float): Segundo a partir do qual cortar o áudio.
        output_path (str): Caminho onde o trecho fatiado será salvo.

    Returns:
        str: Caminho do arquivo fatiado.
    """
    # Carrega o WAV completo e fatia a partir do offset em milissegundos
    audio    = AudioSegment.from_wav(wav_path)
    start_ms = int(start_seconds * 1000)
    sliced   = audio[start_ms:]
    # Exporta o trecho como WAV mantendo as mesmas configurações do original
    sliced.export(output_path, format="wav")
    print(f"Audio sliced: starting from {start_seconds:.0f}s -> saved to {output_path}")
    return output_path


if __name__ == "__main__":
    # Bloco de autoteste ao executar diretamente
    import sys
    if len(sys.argv) > 2:
        preprocess_audio(sys.argv[1], sys.argv[2])
    else:
        print("Usage: python audio_processor.py <input_file> <output_wav_file>")
