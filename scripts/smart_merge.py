import os
import sys
from google import genai
from google.genai import types

# Adiciona o diretório raiz para imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

def run_smart_merge():
    print("=" * 60)
    print("SCRIBEPY - SMART MERGE (CONCILIAÇÃO COM IA)")
    print("=" * 60)

    if len(sys.argv) < 2:
        print("Usage: python scripts/smart_merge.py <base_name>")
        print("Example: python scripts/smart_merge.py \"Nals 27 Reinaldo Ruys Qualidade\"")
        return

    base_name = sys.argv[1].replace(".m4a", "").replace(".wav", "").replace("_transcript", "")
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(script_dir, ".."))
    converted_dir = os.path.join(project_root, "converted")

    original_path = os.path.join(converted_dir, f"{base_name}_transcript.txt")
    corrections_path = os.path.join(converted_dir, f"{base_name}_transcript_correcoes.txt")

    if not os.path.exists(original_path) or not os.path.exists(corrections_path):
        print(f"Erro: Arquivos não encontrados para {base_name}.")
        return

    glossary_path = os.path.join(project_root, "glossario.txt")
    glossary_text = ""
    if os.path.exists(glossary_path):
        try:
            with open(glossary_path, "r", encoding="utf-8") as gf:
                glossary_text = gf.read().strip()
        except Exception:
            pass

    # Lê os conteúdos
    with open(original_path, "r", encoding="utf-8") as f:
        original_text = f.read()

    with open(corrections_path, "r", encoding="utf-8") as f:
        corrections_text = f.read()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Erro: GEMINI_API_KEY não configurada no .env")
        sys.exit(1)

    print("Iniciando conciliação via IA (Gemini)... isso pode levar 1-2 minutos.")
    
    client = genai.Client()
    model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

    system_instruction = (
        "Você é um engenheiro de dados especialista em processamento de linguagem natural e alinhamento de transcrições de áudio.\n"
        "O usuário tentou fazer um 'patch' (correção de um trecho) em uma transcrição longa, mas o trecho gerado "
        "possui timestamps alucinados (time drift) e perdeu os nomes originais dos participantes (usando Participante 1, etc.).\n\n"
        "Sua tarefa é CONCILIAR (fazer o merge perfeito) dos dois textos:\n"
        "1. Identifique no TEXTO ORIGINAL onde o TEXTO CORRIGIDO deve entrar (substituindo o trecho corrompido/alucinado).\n"
        "2. Identifique pelo contexto quem são os participantes reais (ex: Padula, Reynaldo) e substitua os nomes genéricos no texto corrigido.\n"
        "3. Remova sobreposições (duplicatas) nas costuras (início e fim do trecho inserido).\n"
        "4. Interpole/Ajuste os timestamps do trecho corrigido de forma matemática/lógica para que fluam suavemente "
        "desde o timestamp da linha anterior até o timestamp da linha posterior, sem saltos bizarros (como pular pra 2 horas num áudio de 60 min).\n\n"
        "RETORNE APENAS O TEXTO COMPLETO E FINAL DA TRANSCRIÇÃO JÁ CONCILIADA. Não adicione comentários, saudações ou formatação markdown (```)."
    )

    prompt = f"""
    === TEXTO ORIGINAL (Com trecho corrompido no meio) ===
    {original_text}

    === TEXTO CORRIGIDO (Para ser inserido no lugar do corrompido) ===
    {corrections_text}
    """
    
    if glossary_text:
        prompt += f"\n\n=== CONTEXTO ADICIONAL (GLOSSÁRIO DA EMPRESA) ===\n{glossary_text}\n"

    prompt += """
    Por favor, devolva o texto original com o bloco corrigido perfeitamente inserido, 
    nomes resolvidos, costuras limpas e timestamps matematicamente coerentes.
    """

    try:
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.1,
                max_output_tokens=65536
            )
        )
        
        final_text = response.text.strip()
        
        # Limpa blocos de markdown se a IA colocar sem querer
        if final_text.startswith("```"):
            final_text = "\n".join(final_text.split("\n")[1:])
        if final_text.endswith("```"):
            final_text = "\n".join(final_text.split("\n")[:-1])

        merged_path = os.path.join(converted_dir, f"{base_name}_transcript_merged.txt")
        with open(merged_path, "w", encoding="utf-8") as f:
            f.write(final_text)

        print(f"\nConciliação concluída com sucesso!")
        print(f"O arquivo final unificado foi salvo em: {merged_path}")

    except Exception as e:
        print(f"Erro durante a comunicação com a API: {e}")

if __name__ == "__main__":
    run_smart_merge()
