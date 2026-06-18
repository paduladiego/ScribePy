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
    
    # Load audio using pydub
    audio_format = os.path.splitext(input_path)[1].replace(".", "").lower()
    audio = AudioSegment.from_file(input_path, format=audio_format)
    
    # Convert to 16kHz, mono
    print("Converting audio to 16kHz, mono...")
    audio = audio.set_frame_rate(16000).set_channels(1)
    
    # Normalize gain to maximize voice signal before processing
    print("Normalizing audio volume...")
    audio = audio.normalize()
    
    # Convert pydub AudioSegment to numpy array for noisereduce
    samples = np.array(audio.get_array_of_samples())
    
    # Handle sample width conversion (convert to float32 between -1.0 and 1.0)
    if audio.sample_width == 2:
        samples = samples.astype(np.float32) / 32768.0
    elif audio.sample_width == 4:
        samples = samples.astype(np.float32) / 2147483648.0
    else:
        samples = samples.astype(np.float32) / 128.0  # 8-bit audio fallback
        
    sample_rate = audio.frame_rate
    
    print("Applying noise reduction...")
    # Reduce noise using non-stationary noise reduction algorithm
    # stationary=False is ideal for complex environments like factories
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

if __name__ == "__main__":
    # Self-test block when running directly
    import sys
    if len(sys.argv) > 2:
        preprocess_audio(sys.argv[1], sys.argv[2])
    else:
        print("Usage: python audio_processor.py <input_file> <output_wav_file>")
