"""
Script to audit transcript text files for common AI/API errors:
- Timestamp regressions (time going backwards).
- Timestamp jumps / anomalies (start > end, absurd durations).
- Synthesized fixed intervals (e.g. repetitive 3-second blocks).
- Endless loops (repeated words, repeated characters).
- Block text duplications across different timestamps.

Saves a full report to audit_report.txt and prints an executive summary.
"""

import os
import re
import sys
from pathlib import Path

# Expressao regular para capturar carimbos de tempo [MM:SS - MM:SS] ou [HH:MM:SS - HH:MM:SS]
TIMESTAMP_REGEX = re.compile(r"^\[(\d+:\d+(?::\d+)?)\s*-\s*(\d+:\d+(?::\d+)?)\]\s*(.*?)$")

def parse_time_to_seconds(time_str: str) -> int:
    """Converte formato MM:SS ou HH:MM:SS para segundos totais."""
    parts = [int(p) for p in time_str.split(":")]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    elif len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return 0

def format_seconds(seconds: int) -> str:
    """Converte segundos para MM:SS ou HH:MM:SS legivel."""
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

def audit_file(file_path: Path):
    """Analisa um arquivo de transcricao e retorna diagnostico detalhado."""
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    timestamp_regressions = []
    timestamp_anomalies = []
    repetition_errors = []
    duplicate_blocks = []
    fixed_step_blocks = []

    last_start = 0
    consecutive_3s = 0
    fixed_step_start_line = None

    seen_phrases = {}

    for idx, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("---"):
            continue

        match = TIMESTAMP_REGEX.match(line)
        if match:
            start_str, end_str, content = match.groups()
            start_sec = parse_time_to_seconds(start_str)
            end_sec = parse_time_to_seconds(end_str)
            duration = end_sec - start_sec

            # 1. Duracao negativa
            if end_sec < start_sec:
                timestamp_anomalies.append(
                    f"Linha {idx}: Duracao negativa [{start_str} - {end_str}]"
                )

            # 2. Regressao no tempo (> 10 segundos para tras)
            if start_sec < last_start - 10:
                timestamp_regressions.append(
                    (idx, last_start, start_sec, f"Linha {idx}: Voltou de {format_seconds(last_start)} para {start_str} (-{last_start - start_sec}s)")
                )

            # 3. Salto temporal gigante (> 10 minutos)
            if last_start > 0 and (start_sec - last_start) > 600:
                timestamp_anomalies.append(
                    f"Linha {idx}: Salto repentino de {format_seconds(last_start)} para {start_str} (+{(start_sec - last_start)//60} min)"
                )

            # 4. Falas consecutivas com exatamente 3s (sintetizacao em bloco)
            if duration == 3:
                consecutive_3s += 1
                if consecutive_3s == 1:
                    fixed_step_start_line = idx
            else:
                if consecutive_3s >= 6:
                    fixed_step_blocks.append(
                        f"Linhas {fixed_step_start_line} a {idx-1}: Sequencia de {consecutive_3s} falas de 3s exatos"
                    )
                consecutive_3s = 0

            # 5. Palavras repetidas em loop
            repeated_words = re.findall(r"\b(\w{3,})\b(?:\s+\1){3,}", content, flags=re.IGNORECASE)
            if repeated_words:
                repetition_errors.append(
                    f"Linha {idx} [{start_str}]: Palavra em loop '{repeated_words[0]}'"
                )

            # 6. Caracteres repetidos
            repeated_chars = re.findall(r"(.)\1{7,}", content)
            if repeated_chars:
                repetition_errors.append(
                    f"Linha {idx} [{start_str}]: Caracteres repetidos '{repeated_chars[0]}'"
                )

            # 7. Frases duplicadas em timestamps distantes (blocos substantivos > 65 caracteres)
            clean_text = re.sub(r"^[^-]+-\s*", "", content).strip().lower()
            if len(clean_text) > 65:
                if clean_text in seen_phrases:
                    prev_line, prev_ts = seen_phrases[clean_text]
                    if abs(start_sec - parse_time_to_seconds(prev_ts)) > 60:
                        duplicate_blocks.append(
                            f"Linha {idx} [{start_str}] duplica Linha {prev_line} [{prev_ts}]: \"{clean_text[:60]}...\""
                        )
                else:
                    seen_phrases[clean_text] = (idx, start_str)

            last_start = max(last_start, start_sec)

    return {
        "file_name": file_path.name,
        "total_lines": len(lines),
        "regressions": timestamp_regressions,
        "anomalies": timestamp_anomalies,
        "repetitive_blocks": fixed_step_blocks,
        "word_loops": repetition_errors,
        "duplicate_texts": duplicate_blocks
    }

def main():
    base_dir = Path("converted")
    if not base_dir.exists():
        base_dir = Path(".")

    transcript_files = sorted(base_dir.glob("*_transcript.txt"))
    report_lines = []

    print(f"\nAUDITORIA DE TRANSCRIÇÕES - SCRIBEPY\n{'='*70}")
    print(f"{'Arquivo':<45} | {'Regressões':<10} | {'Duplicatas':<10} | {'Status'}")
    print(f"{'-'*70}")

    for file_path in transcript_files:
        res = audit_file(file_path)
        
        has_critical = bool(res["regressions"] or res["duplicate_texts"] or res["anomalies"])
        has_issue = bool(has_critical or res["repetitive_blocks"] or res["word_loops"])
        status = "[CRÍTICO]" if (len(res["regressions"]) > 5 or len(res["duplicate_texts"]) > 3) else ("[ATENÇÃO]" if has_critical else "[OK]")
        
        print(f"{res['file_name'][:44]:<45} | {len(res['regressions']):<10} | {len(res['duplicate_texts']):<10} | {status}")

        # Monta relatorio detalhado para o arquivo
        report_lines.append(f"\n{'='*80}\nARQUIVO: {res['file_name']} ({res['total_lines']} linhas)\n{'='*80}")
        if res["regressions"]:
            report_lines.append(f"\n[!] REGRESSÕES TEMPORAIS ({len(res['regressions'])} ocorrências):")
            for item in res["regressions"][:15]:
                report_lines.append(f"  - {item[3]}")
            if len(res["regressions"]) > 15:
                report_lines.append(f"  ... e mais {len(res['regressions']) - 15} regressões.")

        if res["anomalies"]:
            report_lines.append(f"\n[!] ANOMALIAS DE TIMESTAMP ({len(res['anomalies'])}):")
            for a in res["anomalies"]:
                report_lines.append(f"  - {a}")

        if res["repetitive_blocks"]:
            report_lines.append(f"\n[!] BLOCOS ARTIFICIAIS COM INTERVALO FIXO ({len(res['repetitive_blocks'])}):")
            for b in res["repetitive_blocks"]:
                report_lines.append(f"  - {b}")

        if res["word_loops"]:
            report_lines.append(f"\n[!] LOOPS DE PALAVRA / CARACTERES ({len(res['word_loops'])}):")
            for wl in res["word_loops"]:
                report_lines.append(f"  - {wl}")

        if res["duplicate_texts"]:
            report_lines.append(f"\n[!] TRECHOS / DIÁLOGOS DUPLICADOS ({len(res['duplicate_texts'])}):")
            for d in res["duplicate_texts"]:
                report_lines.append(f"  - {d}")

        if not has_issue:
            report_lines.append("\n[OK] Nenhum problema detectado.")

    report_path = Path("audit_report.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

    print(f"{'-'*70}")
    print(f"Relatório detalhado salvo com sucesso em: {report_path.resolve()}\n")

if __name__ == "__main__":
    main()
