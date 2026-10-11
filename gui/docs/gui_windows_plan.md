# Cenário 1: Plano de Implantação da Interface Windows Desktop

Este plano detalha a primeira fase do desenvolvimento visual do ScribePy: a criação de um aplicativo desktop dedicado para o sistema operacional Windows com visual Fluent Design (estilo Windows 11).

---

## 🎨 Especificações Técnicas de UI/UX (Windows 11)

* **Framework Principal**: **PySide6** (Qt para Python) integrado à biblioteca **`qfluentwidgets`** para obter o design visual nativo do Windows 11.
* **Componentes Fluent**:
  * Janela principal com cantos arredondados e suporte ao efeito Mica/Acrylic (efeito de transparência característico do Windows 11).
  * Painel lateral de navegação com ícones modernos da Microsoft (`Segoe MDL2 Assets`).
  * Controles de formulário com estados visuais claros (Enabled, Disabled, Active, Hover).

---

## 🖥️ Layout e Protótipo de Tela

O aplicativo desktop do Windows será dividido em um fluxo simples de três etapas dispostas em guias (Tabs) ou painéis laterais:

```text
+--------------------------------------------------------------------------+
|  ScribePy - Transcrição Inteligente                       [-] [o] [x]   |
+--------------------------------------------------------------------------+
|  Painel de Controle           |  Visualizador de Transcrição            |
|                               |                                         |
|  [Selecionar Áudio...]        |  [00:10] Participante 1 - Bom dia...   |
|  meeting.m4a  (13:59)         |  [00:20] Participante 2 - Tudo bem?    |
|                               |                                         |
|  ┌──────────────────────────┐ |  Renomear: [ Participante 1 ]           |
|  │ 🎙️ Modo de Ambiente       │ |           → [ Luis Melo      ]  [✔]   |
|  │  ○ 🏢 Escritório (Clean)  │ |                                        |
|  │  ● 🏭 Fábrica   (Clear)   │ |  [ Excluir Linha Selecionada ]         |
|  └──────────────────────────┘ |  [ Salvar Edição ]                     |
|                               |                                         |
|  Provedor: [ GLADIA       ▾ ] |                                         |
|  Modelo:   [ solaria-1    ▾ ] |                                         |
|                               |                                         |
|  [ ▶  Iniciar Transcrição  ]  |                                         |
|  [ 🗑️  Limpar Temporários  ]  |                                         |
|                               |                                         |
|  Status: ✓ Concluído!         |                                         |
|  [████████████████] 100%      |                                         |
|  Custo: USD $0.142 / R$ 0.85 |                                         |
+--------------------------------------------------------------------------+
```

### 1. Painel de Controle de Execução (Lado Esquerdo)
* **Importação de Áudio**: Área interativa "Drag & Drop" (Arrastar e Soltar) que aceita arquivos `.m4a`, `.wav`, etc., ou botão de exploração tradicional que abre o `QFileDialog`.

* **🎙️ Seletor de Modo de Ambiente (Toggle CLEAR / CLEAN)**:
  Este é o controle visual que substitui a flag `clear` da linha de comando. Será implementado como um **grupo de opções com rádio-botões** (ou Toggle Switch do Fluent Design), com dois estados bem distintos:

  | Estado Visual | Modo | Comportamento no Backend | Quando Usar |
  |---|---|---|---|
  | 🏢 **Escritório (Clean)** | Padrão | `noise_reduce=False` — apenas converte e normaliza o volume | Salas de reunião, escritórios, ambiente silencioso |
  | 🏭 **Fábrica (Clear)** | Ativado | `noise_reduce=True` — aplica supressão de ruído industrial | Chão de fábrica, exaustores, tornos, motores |

  **Regras de UX**:
  * O estado padrão ao abrir o app é **Escritório (Clean)**, pois é a opção mais segura (não reduz volume de áudio limpos).
  * O toggle é **persistido no `.env`** como uma nova variável `AUDIO_MODE=CLEAR|CLEAN`, garantindo que o usuário não precise reconfigurar ao reabrir o app.
  * Quando o modo **Fábrica (Clear)** está ativo, o ícone da área de drop de arquivo muda para 🏭 e um badge laranja aparece no botão "Iniciar" com o texto `CLEAR ATIVO`, alertando visualmente que o processamento extra de ruído será aplicado.
  * Se o arquivo `_clean.wav` já existir na pasta `converted/` (gerado em execução anterior), um aviso amarelo é exibido: *"WAV cached detectado. Exclua-o para reaplicar o novo modo de ambiente."*

* **Configuração do Provedor de Transcrição**:
  * Seleção de Provedores (`Gemini`, `Gladia`, `OpenAI` ou `Whisper Local`) e Modelos por menus dropdown.
  * Inputs mascarados para chaves de API, com persistência automática de estado no arquivo local `.env`.

* **Controles Operacionais**:
  * Botões de "Iniciar", "Pausar" e "Retomar do Checkpoint".
  * Botão de limpeza de temporários (chama a rotina de exclusão de WAVs residuais).

### 2. Painel de Edição de Texto e Revisão (Lado Direito)
* **Visualizador em Tempo Real**: Carrega dinamicamente o arquivo `{audio}_transcript.txt`.
* **Substituição de Participantes**:
  * Caixa dedicada onde o usuário pode selecionar um participante detectado (ex: `Participante 1`) e definir o nome definitivo (ex: `Luís Melo`), disparando uma atualização rápida no arquivo físico de transcrição.
* **Refinamento de Linhas**:
  * Possibilidade de selecionar uma linha incorreta no editor e clicar em "Excluir Linha" ou fazer correções ortográficas livremente.
  * Editor de texto livre integrado para correções ortográficas antes de exportar ao NotebookLM.

### 3. Painel de Correções Cirúrgicas e Glossário (Configurações Avançadas)
* **Lista de Correções Temporais**: O usuário digita os tempos problemáticos (ex: `31:18 - 39:40`) em uma lista e clica em "Corrigir Trecho", automatizando a execução do script `fix_by_time.py`.
* **Editor do Glossário**: Uma tabela de chave-valor para cadastrar jargões novos e sincronizá-los diretamente com o [glossario.txt](file:///c:/00_Projects/ScribePy/glossario.txt).

### 4. Barra de Status e Relatório de Custos (Painel Inferior)
* **Indicador de Modo Ativo**: Exibe no rodapé da janela o modo atual selecionado (`🏭 CLEAR` ou `🏢 CLEAN`) junto ao nome do provedor ativo (`GLADIA | solaria-1`) para referência rápida sem abrir o painel de controle.
* **Progresso de Estágios**: Barra de progresso em 4 segmentos visuais distintos com label dinâmico:
  * Estágio 1: `Convertendo áudio...` (FFmpeg)
  * Estágio 2: `Reduzindo ruído...` (noisereduce, apenas no modo CLEAR)
  * Estágio 3: `Enviando para API...` (upload)
  * Estágio 4: `Transcrevendo...` (polling + resposta)
* **Painel de Custo**: Após a conclusão, exibe o resumo de tokens e custo em USD e BRL, tal qual o relatório atual do terminal.

---

## 🛠️ Arquitetura do Processo de Transcrição (QThread)

Para manter a janela responsiva (sem congelar ou travar o Windows):
1. **Thread Principal (GUI)**: Roda o loop de eventos do PySide6 e gerencia todos os cliques e atualizações de estado visual.
2. **Thread de Execução (QThread)**: Executa o loop do [pipeline.py](file:///c:/00_Projects/ScribePy/src/pipeline.py) em paralelo, recebendo como parâmetros:
   * `input_audio_path` — arquivo de áudio selecionado.
   * `noise_reduce` — derivado do toggle 🏭/🏢 selecionado na interface.
   * `custom_glossary` — conteúdo atual do `glossario.txt`.
3. **Comunicação por Sinais (Signals)**:
   * `stage_changed(str)` — atualiza o label da barra de progresso conforme o estágio muda (ex: `"Reduzindo ruído..."`), emitido apenas se `noise_reduce=True`.
   * `progress_updated(int)` — atualiza a barra de progresso percentual.
   * `cost_report_ready(dict)` — sinal final com os dados de custo que popula o painel de relatório.

---

## 📦 Compilação e Distribuição (.exe e Microsoft Store)

Para distribuir o software comercialmente para usuários finais de Windows:
1. **Compilação**: Utilização do **`PyInstaller`** ou **`auto-py-to-exe`** para empacotar o código Python e todas as suas dependências (incluindo binários do FFmpeg) em um arquivo executável único de clique duplo (`ScribePy.exe`).
2. **Empacotamento MSIX**: Conversão do instalador para o formato `.msix` exigido pela Microsoft Store.
3. **Distribuição**: Publicação do pacote na **Microsoft Partner Center** para disponibilizá-lo na **Windows Store**, permitindo atualizações automáticas gerenciadas pelo próprio sistema do Windows.
