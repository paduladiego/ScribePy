# All logical architecture, variable names, function names, classes, and database schemas MUST be in US English.
# ALL comments inside the code (inline, block, or docstrings) MUST be written in Portuguese (PT-BR).

import sys
import time
import threading

class TerminalSpinner:
    """Classe utilitária para gerenciar animação de progresso e contador de tempo no terminal."""

    def __init__(self, label: str = "Processing"):
        self.label = label
        self.stop_event = threading.Event()
        self.thread = None

    def _spin(self) -> None:
        """Função interna executada em thread separada para exibir a animação."""
        # Frames do spinner - ASCII compatível com Windows
        frames = ["|", "/", "-", "\\"]
        elapsed = 0
        idx = 0
        while not self.stop_event.is_set():
            mins, secs = divmod(elapsed, 60)
            # Sobrescreve a linha atual com o label, animação e tempo decorrido
            print(
                f"\r  [{self.label}] ... {frames[idx % 4]}  {mins:02d}:{secs:02d}",
                end="",
                flush=True
            )
            time.sleep(1)
            elapsed += 1
            idx += 1
        # Limpa a linha do spinner quando terminar
        print("\r" + " " * 80 + "\r", end="", flush=True)

    def start(self) -> None:
        """Inicia a animação do spinner em uma thread secundária."""
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._spin, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        """Para a animação do spinner e aguarda a thread finalizar."""
        if self.thread:
            self.stop_event.set()
            self.thread.join()
            self.thread = None
