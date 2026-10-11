# ScribePy — Guia Rápido de Uso e Comandos (DevInfo)

Este documento centraliza as instruções práticas de uso do ScribePy, comandos rápidos de execução, fluxos de correção cirúrgica e configurações essenciais.

---

## 1. Pré-requisitos & Ambiente

Certifique-se de ativar o ambiente virtual antes de executar qualquer comando:

```powershell
.venv\Scripts\Activate.ps1
```

---

## 2. Comandos Principais de Transcrição

O ponto de entrada principal do projeto é o `main.py`.

### 2.1 Modo Padrão (Ambiente silencioso / Reuniões normais)
Converte o áudio para WAV 16kHz mono, normaliza o volume e envia para o provedor configurado no `.env`:
```powershell
.venv\Scripts\python main.py "seu_audio.m4a"
```

### 2.2 Modo com Redução de Ruído Industrial (`clear`)
Recomendado para áudios gravados em chão de fábrica ou com ruído constante de máquinas:
```powershell
.venv\Scripts\python main.py clear "seu_audio.m4a"
```

### 2.3 Usando Glossário Específico
Por padrão, o arquivo `glossario.txt` da raiz é carregado automaticamente. Caso deseje passar outro glossário:
```powershell
.venv\Scripts\python main.py "seu_audio.m4a" "glossario_Yuji.txt"
```

---

## 3. Correção e Transcrição Cirúrgica por Trecho

Quando um trecho específico falha (ex.: erro de API entre `17:23` e `40:12`) ou precisa ser refeito sem reprocessar o áudio inteiro:

### Passo a Passo:
1. Abra o arquivo `scripts/fix_ranges.txt`.
2. Insira os intervalos que deseja transcrever (um por linha) no formato `MM:SS - MM:SS` (ou use `fim` para ir até o término do áudio):
   ```text
   17:23 - 40:12
   ```
3. Execute o script cirúrgico:
   ```powershell
   .venv\Scripts\python scripts/fix_by_time.py "seu_audio.m4a"
   ```
4. O resultado do trecho fatiado será gerado com os timestamps corretos em:
5. (Opcional) Para colar o trecho corrigido perfeitamente de volta no arquivo original, sem duplicações, com ajuste de nomes e correção de contagem de tempo, execute a Conciliação via IA:
   ```powershell
   .venv\Scripts\python scripts/smart_merge.py "seu_audio"
   ```
   - O resultado unificado e limpo será gerado em: `converted/{nome_do_audio}_transcript_merged.txt`

---

## 4. Retomada Automática (Smart Resume)

Se uma transcrição falhou no meio do processo ou foi interrompida:
- O arquivo de saída parcial `converted/{audio}_transcript.txt` é verificado automaticamente pelo `src/pipeline.py`.
- Se ele contiver timestamps válidos e não tiver a tag `--- FIM ---`, basta rodar o comando normal novamente:
  ```powershell
  .venv\Scripts\python main.py "seu_audio.m4a"
  ```
- O sistema retoma a partir do último timestamp gravado (com 10 segundos de sobreposição para não perder contexto).

---

## 5. Limpeza de Arquivos Intermediários

Para limpar os arquivos temporários gerados (`_clean.wav`, `_resume.wav`, fatias temporárias) mantendo as transcrições finais:

```powershell
.venv\Scripts\python scripts/cleanup.py
```

---

## 6. Auditoria e Correção em Lote de Transcrições

Quando há suspeita de alucinações de timestamp, repetição de palavras ou blocos de diálogo duplicados por falhas da API:

### 6.1 Auditoria Completa
Para verificar todos os arquivos `*_transcript.txt` de uma vez e gerar o relatório:
```powershell
.venv\Scripts\python scripts/audit_transcripts.py
```

### 6.2 Correção Cirúrgica com Backup
Para aplicar a desduplicação e normalização automática com backup para `converted/backups/`:
```powershell
.venv\Scripts\python scripts/fix_transcripts.py
```

*Consulte o plano completo em: `00_DevInfo/PLANO_CORRECAO_TRANSCRICOES.md`.*

---

## 7. Provedores Suportados (.env)

No arquivo `.env`, altere o provedor através da variável `API_PROVIDER`:

| Provedor | Variável | Configuração |
| :--- | :--- | :--- |
| **Google Gemini** | `API_PROVIDER=GEMINI` | Modelo rápido e econômico (`gemini-2.5-flash` ou `gemini-3.1-flash-lite`) |
| **OpenAI Whisper** | `API_PROVIDER=OPENAI` | API oficial Whisper-1 da OpenAI |
| **Gladia API** | `API_PROVIDER=GLADIA` | Modelo Solaria-1 com diarização nativa de falantes |
| **Local Whisper** | `TRANSCRIPTION_MODE=LOCAL` | Execução offline via CPU/GPU usando `faster-whisper` |

---

## 8. Estrutura de Diretórios Importantes

```text
ScribePy/
├── 00_DevInfo/
│   ├── GUIA_RAPIDO.md              # Este guia rápido de comandos e uso
│   └── PLANO_CORRECAO_TRANSCRICOES.md # Plano de correção de alucinações e duplicatas
├── converted/                      # Saídas e arquivos gerados (WAVs e TXTs)
│   └── backups/                    # Backups automáticos antes de correções cirúrgicas
├── scripts/
│   ├── audit_transcripts.py        # Auditor de regressões e duplicatas
│   ├── fix_transcripts.py          # Corretor cirúrgico automatizado
│   ├── fix_by_time.py             # Script de corte e transcrição cirúrgica
│   ├── smart_merge.py             # Conciliação via IA de transcrições corrigidas
│   ├── fix_ranges.txt             # Arquivo com as marcações de tempo a corrigir
│   └── cleanup.py                 # Limpeza de WAVs intermediários
├── glossario.txt                  # Termos técnicos e jargões da fábrica
├── main.py                        # Ponto de entrada CLI
└── .env                           # Chaves de API e configurações
```

