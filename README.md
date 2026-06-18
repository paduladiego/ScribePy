# ScribePy

O **ScribePy** é uma ferramenta em Python desenvolvida para resolver transcrições de áudios em ambientes altamente ruidosos (como fábricas e plantas industriais) e com a necessidade de identificação de termos e jargões muito técnicos (como sublimação de alumínio, perfis extrudados e filmes sublimáticos).

O aplicativo realiza o tratamento de ruído local e envia o áudio processado para a API do **Gemini 2.5 Flash** para fazer a transcrição inteligente em português (PT-BR) com identificação de locutores (diarização) e timestamps, gerando um arquivo de texto perfeitamente estruturado para ser integrado e analisado no **NotebookLM**.

---

## 🚀 Funcionalidades

1. **Pré-processamento e Limpeza (Fase 1)**:
   * Conversão automática de áudio `.m4a` (do Galaxy S24 Ultra, por exemplo) para `.wav` de 16kHz Mono (padrão ouro de áudio para IA) usando `static-ffmpeg`.
   * Normalização automática de ganho para amplificar a voz.
   * Redução inteligente de ruído estacionário de fábrica (motores, exaustores, fornos) com a biblioteca `noisereduce` e barra de progresso visual.

2. **Transcrição Inteligente Contextualizada (Fase 2)**:
   * Integração com o modelo **Gemini 2.5 Flash** (rápido e de altíssima precisão).
   * **Diarização**: Identificação automática de quem fala, separando as falas por `Participant 1`, `Participant 2`, etc.
   * **Timestamps**: Adiciona o tempo de início e fim de cada diálogo no formato `[MM:SS - MM:SS]`.
   * **Glossário Técnico Automático**: Se você criar um arquivo `glossario.txt` na raiz do projeto e escrever termos de fábrica nele, o ScribePy lerá o arquivo e ensinará o Gemini a transcrever corretamente termos difíceis (ex: "filme sublimático" em vez de "filme de cinema").

3. **Pronto para o NotebookLM**:
   * O output final é salvo em um arquivo de texto limpo (`_transcript.txt`) projetado para ser arrastado e solto como fonte no NotebookLM para gerar resumos de reuniões e atas.

---

## 🛠️ Requisitos e Configuração

### 1. Criar o Ambiente Virtual e Instalar Dependências
No PowerShell do Windows, execute:
```powershell
# Criar ambiente virtual
python -m venv .venv

# Ativar ambiente virtual
.\.venv\Scripts\Activate.ps1

# Instalar dependências
pip install -r requirements.txt
```

### 2. Configurar a Chave da API do Gemini
Crie um arquivo chamado `.env` na raiz do projeto (este arquivo é ignorado pelo Git para sua segurança) e insira a sua chave obtida no [Google AI Studio](https://aistudio.google.com/):
```env
GEMINI_API_KEY=SUA_CHAVE_AQUI
```

### 3. Configurar seu Glossário Técnico (Opcional, mas Recomendado)
Crie um arquivo chamado `glossario.txt` na raiz do projeto e escreva os termos da sua empresa separados por vírgula. Exemplo:
```text
filme sublimático, sublimação de perfis, prensa térmica, forno de cura, extrusão de alumínio, lacagem.
```

---

## 📖 Como Usar

Com o ambiente virtual ativo, basta executar o script principal passando o caminho do seu arquivo de áudio:

```powershell
.\.venv\Scripts\python.exe main.py caminho/do/seu_audio.m4a
```

O programa fará:
1. A limpeza e conversão do áudio (exibindo a porcentagem na tela).
2. O upload e a geração do texto na nuvem (exibindo pontos de progresso).
3. A limpeza do arquivo temporário local `.wav` e da nuvem, gerando o arquivo final de transcrição (ex: `seu_audio_transcript.txt`).
