# ScribePy

O **ScribePy** é uma ferramenta em Python desenvolvida para resolver transcrições de áudios em ambientes altamente ruidosos (como fábricas e plantas industriais) e com a necessidade de identificação de termos e jargões muito técnicos (como sublimação de alumínio, perfis extrudados e filmes sublimáticos).

O aplicativo realiza o tratamento de ruído local e despacha o áudio processado de forma inteligente para múltiplos provedores (APIs na nuvem ou processamento 100% Local offline). A transcrição final gera um arquivo de texto estruturado com marcação de tempo e diarização de locutores, projetado especificamente para ser integrado e analisado no **NotebookLM** para a geração automática de atas de reunião, relatórios Lean e planos de ação.

---

## 🚀 Novidades da Versão v8

* **Suporte Multi-Provedor (Dispatcher Central)**: Chaveamento dinâmico via arquivo `.env` para escolher onde rodar a transcrição.
* **Integração com Gladia API v2**: Processamento ultra-rápido (ex: 8 minutos de áudio processados em 14 segundos) com **diarização de falantes integrada** e de excelente qualidade para Português (PT-BR).
* **Parser de Glossário Inteligente**: Se você utilizar um glossário complexo em Markdown (com tabelas e explicações), o ScribePy limpa a formatação e extrai cirurgicamente apenas as palavras técnicas para injetar no vocabulário da API (evitando alucinações de jargões fabris).
* **Transcrição Local Offline**: Execução local sem dependência de internet utilizando a biblioteca `faster-whisper` em CPU com modelos otimizados (como o `large-v3-turbo`).
* **Roadmap de GUI**: Estrutura física e planejamento definidos para a futura interface gráfica com visual nativo do Windows 11 (Fluent Design).

---

## 🛠️ Funcionalidades

1. **Fase 1: Pré-processamento e Limpeza de Áudio (Local)**:
   * Conversão automática de áudio `.m4a` (gravados em celulares) para `.wav` de 16kHz Mono (padrão ouro para processamento de voz) usando `static-ffmpeg`.
   * Normalização de volume para amplificar vozes baixas.
   * Redução inteligente de ruído estacionário de chão de fábrica (exaustores, motores, empilhadeiras) com a biblioteca `noisereduce` e barra de progresso visual.

2. **Fase 2: Transcrição Roteada Inteligente (Dispatcher)**:
   * **API Gemini**: Utiliza o modelo `gemini-3.1-flash-lite` para transcrição de baixo custo e altíssima precisão com contexto longo.
   * **API Gladia v2**: Focada em velocidade extrema com diarização nativa (`Participante 1`, `Participante 2`...).
   * **API OpenAI (Whisper-1)**: Transcrição clássica baseada na nuvem da OpenAI.
   * **Whisper Local**: Transcrição offline rodando no processador (CPU) da sua máquina usando chaves e modelos customizáveis (`base`, `large-v3-turbo`).

3. **Correção Cirúrgica e Conciliação com IA (Smart Merge)**:
   * Script nativo (`fix_by_time.py`) para recortar e transcrever apenas trechos problemáticos (ruídos, falhas de API) definidos em um arquivo de texto.
   * Conciliação automática (`smart_merge.py`) baseada em IA que costura a transcrição corrigida de volta no arquivo original, resolvendo furos, removendo duplicatas e interpolando falhas de "time drift" matematicamente para um texto perfeitamente fluido.

4. **Checkpoints e Smart Resume**:
   * O pipeline monitora o arquivo de saída. Se o processo for interrompido por queda de internet ou cota de API, o ScribePy calcula o timestamp de parada, fatia o áudio restante com overlap de segurança de 10s e **continua exatamente de onde parou**, evitando custos de reprocessamento e tokens duplicados.

4. **Pronto para o NotebookLM**:
   * O output final é salvo em um arquivo de texto limpo (`_transcript.txt`) projetado para ser arrastado e solto como fonte no NotebookLM para gerar resumos de reuniões e atas.

---

## ⚙️ Configuração e Instalação

### 1. Criar o Ambiente Virtual e Instalar Dependências
No PowerShell do Windows, execute:
```powershell
# Criar ambiente virtual
python -m venv .venv

# Ativar ambiente virtual
.\.venv\Scripts\Activate.ps1

# Instalar dependências atualizadas
pip install -r requirements.txt
```

### 2. Configurar o arquivo `.env`
Crie um arquivo chamado `.env` na raiz do projeto (ou edite o existente) e configure as credenciais dos provedores que deseja utilizar:

```env
# --- Configurações de Roteamento de Transcrição ---
# Rota de transcrição: API ou LOCAL
TRANSCRIPTION_MODE=API

# Provedor se TRANSCRIPTION_MODE=API (GEMINI, OPENAI ou GLADIA)
API_PROVIDER=GLADIA

# --- Modelos de Transcrição ---
GEMINI_MODEL=gemini-3.1-flash-lite
GLADIA_MODEL=solaria-1
OPENAI_MODEL=whisper-1
LOCAL_WHISPER_MODEL=large-v3-turbo

# --- Credenciais de API ---
GEMINI_API_KEY=sua_chave_gemini_aqui
GLADIA_API_KEY=sua_chave_gladia_aqui
OPENAI_API_KEY=sua_chave_openai_aqui
```

### 3. Configurar seu Glossário Técnico (`glossario.txt`)
Crie um arquivo chamado `glossario.txt` na raiz do projeto. Você pode escrever uma lista simples separada por vírgulas ou colar um documento Markdown completo com tabelas explicando os jargões. O ScribePy interpretará e enviará as informações limpas para cada provedor.

Exemplo de lista simples:
```text
filme sublimático, sublimação de perfis, gancheiras, passivação, extrusão de alumínio, OEE, MEK.
```

---

## 📖 Como Usar

Com o ambiente virtual ativo, execute o script principal passando o caminho do arquivo de áudio:

```powershell
.\.venv\Scripts\python.exe main.py "caminho/do/seu_audio.m4a"
.\.venv\Scripts\python.exe main.py clear "caminho/do/seu_audio.m4a"

```

O programa realizará automaticamente:
1. Limpeza e conversão do áudio exibindo progresso no console.
2. Roteamento do upload para o provedor selecionado no `.env`.
3. Transcrição com diarização (exibindo um spinner de progresso).
4. Gravação do arquivo final e consolidação de custos estimados no terminal.
