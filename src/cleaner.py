# All logical architecture, variable names, function names, classes, and database schemas MUST be in US English.
# ALL comments inside the code (inline, block, or docstrings) MUST be written in Portuguese (PT-BR).

import os

class AudioCleaner:
    """Classe utilitária para gerenciar a remoção de arquivos de áudio temporários."""

    @staticmethod
    def delete_file(file_path: str) -> bool:
        """
        Remove um arquivo do sistema de arquivos se ele existir.
        Retorna True se foi removido com sucesso, False caso contrário.
        """
        if not file_path:
            return False
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                return True
        except Exception as e:
            # Mensagem em caso de erro na exclusão do arquivo
            print(f"[CLEANER] Erro ao deletar arquivo {file_path}: {e}")
        return False
