# All logical architecture, variable names, function names, classes, and database schemas MUST be in US English.
# ALL comments inside the code (inline, block, or docstrings) MUST be written in Portuguese (PT-BR).

import os
import sys

# Adiciona o diretório raiz do projeto ao sys.path para permitir importações de módulos locais
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.cleaner import AudioCleaner

def run_cleanup():
    """Varre a pasta converted e remove arquivos .wav, .m4a e .txt."""
    print("=" * 60)
    print("SCRIBEPY CLEANUP — LIMPEZA MANUAL DE ARQUIVOS")
    print("=" * 60)
    
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    target_dir = os.path.join(project_root, "converted")
    files_to_delete = []
    
    if not os.path.exists(target_dir):
        print("A pasta 'converted' não existe. Nada a limpar.")
        print("=" * 60)
        return

    try:
        # Varre apenas os arquivos da pasta converted (sem busca recursiva)
        for filename in os.listdir(target_dir):
            file_path = os.path.join(target_dir, filename)
            
            # Garante que seja um arquivo físico na pasta
            if os.path.isfile(file_path):
                ext = os.path.splitext(filename)[1].lower()
                
                # Seleciona arquivos .wav, .m4a e .txt
                if ext in {".wav", ".m4a", ".txt"}:
                    files_to_delete.append((filename, file_path))
                        
    except Exception as e:
        print(f"Erro ao listar arquivos para limpeza: {e}")
        return

    if not files_to_delete:
        print("Nenhum arquivo temporário (.wav, .m4a, .txt) encontrado para remover na pasta 'converted'.")
        print("=" * 60)
        return

    print("Os seguintes arquivos foram encontrados na pasta 'converted':")
    for filename, _ in files_to_delete:
        print(f"  - {filename}")
    print("-" * 60)
    
    # Solicita confirmação manual do usuário no terminal
    confirm = input("Deseja realmente deletar estes arquivos da pasta 'converted'? (S/N): ").strip().upper()
    if confirm != "S":
        print("Operação cancelada pelo usuário.")
        print("=" * 60)
        return

    print("-" * 60)
    deleted_count = 0
    for filename, file_path in files_to_delete:
        print(f"Deletando: {filename} ... ", end="", flush=True)
        if AudioCleaner.delete_file(file_path):
            print("[OK]")
            deleted_count += 1
        else:
            print("[FALHA]")
                      
    print("-" * 60)
    print(f"Limpeza concluída. Total de arquivos removidos: {deleted_count}")
    print("=" * 60)

if __name__ == "__main__":
    run_cleanup()
