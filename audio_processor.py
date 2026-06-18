import os
import numpy as np
from pydub import AudioSegment
import noisereduce as nr
import soundfile as sf

def preprocess_audio(input_path: str, output_path: str) -> str:
    """
    Converts input audio (e.g. .m4a) to WAV 16kHz mono, applies noise reduction
    to suppress industrial background noise, and normalizes the voice signal.
    
    Args:
        input_path (str): Path to the input audio file.
        output_path (str): Path where the processed WAV file will be saved.
        
    Returns:
        str: Path to the processed audio file.
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
    
    # Save the processed numpy array as a standard 16kHz wav file
    print(f"Saving processed clean audio to: {output_path}")
    sf.write(output_path, reduced_noise, sample_rate, subtype='PCM_16')
    
    print("Audio processing completed successfully.")
    return output_path

if __name__ == "__main__":
    # Self-test block when running directly
    import sys
    if len(sys.argv) > 2:
        preprocess_audio(sys.argv[1], sys.argv[2])
    else:
        print("Usage: python audio_processor.py <input_file> <output_wav_file>")
