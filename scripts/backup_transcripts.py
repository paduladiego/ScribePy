"""
Script for Phase 1: Security and Backup of all transcript files.
Creates a timestamped snapshot of all *_transcript*.txt files inside converted/backups/
and validates copy integrity via MD5 checksums.
"""

import hashlib
import shutil
from datetime import datetime
from pathlib import Path

def calculate_checksum(file_path: Path) -> str:
    """Calcula o hash MD5 de um arquivo para validacao de integridade."""
    hasher = hashlib.md5()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()

def execute_backup():
    """Executa o backup de todos os arquivos de transcricao em converted/."""
    converted_dir = Path("converted")
    if not converted_dir.exists():
        print("[ERRO] Diretorio 'converted/' nao encontrado.")
        return

    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_base = converted_dir / "backups"
    snapshot_dir = backup_base / f"snapshot_{timestamp_str}"
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    # Tambem mantem uma copia de facil acesso diretamente em converted/backups/latest
    latest_dir = backup_base / "latest"
    latest_dir.mkdir(parents=True, exist_ok=True)

    transcript_files = sorted(converted_dir.glob("*_transcript*.txt"))

    if not transcript_files:
        print("[AVISO] Nenhum arquivo *_transcript*.txt encontrado para backup.")
        return

    print("=" * 75)
    print("FASE 1: SEGURANÇA E BACKUP DAS TRANSCRIÇÕES")
    print(f"Destino do Snapshot: {snapshot_dir.resolve()}")
    print("=" * 75)
    print(f"{'Arquivo':<48} | {'Tamanho':<10} | {'Integridade (MD5)'}")
    print("-" * 75)

    success_count = 0
    for src in transcript_files:
        dest_snapshot = snapshot_dir / src.name
        dest_latest = latest_dir / src.name

        shutil.copy2(src, dest_snapshot)
        shutil.copy2(src, dest_latest)

        src_hash = calculate_checksum(src)
        dest_hash = calculate_checksum(dest_snapshot)

        if src_hash == dest_hash:
            size_kb = f"{src.stat().st_size / 1024:.1f} KB"
            print(f"{src.name[:47]:<48} | {size_kb:<10} | OK ({src_hash[:8]}...)")
            success_count += 1
        else:
            print(f"[FALHA DE INTEGRIDADE] {src.name}")

    print("-" * 75)
    print(f"Backup concluído com sucesso: {success_count} arquivos protegidos.")
    print(f"Snapshots salvos em:\n  1. {snapshot_dir.resolve()}\n  2. {latest_dir.resolve()}\n")

if __name__ == "__main__":
    execute_backup()
