import streamlit as st
import os
import re
import pickle
import PyPDF2  # Usando PyPDF2 conforme solicitado
import requests  # Necessário para requisições (se houver necessidade em outras partes)
from dotenv import load_dotenv
from googlesearch import search  # Certifique-se de instalar com "pip install googlesearch-python"

# LangChain/IA
from langchain_community.document_loaders import CSVLoader
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import OpenAIEmbeddings
from langchain_community.chat_models import ChatOpenAI
from langchain.schema import HumanMessage

# ------------------------ CONFIGURAÇÕES INICIAIS ------------------------
load_dotenv()  # Carrega as variáveis definidas no .env
st.set_page_config(
    page_title="Assistente Virtual NavSupply",
    layout="wide"
)

# ------------------------ CSS PERSONALIZADO ------------------------
css = """
<style>
/* Fundo geral (Navy) e texto em branco */
body, [data-testid="stAppViewContainer"], [data-testid="stHeader"], [data-testid="stToolbar"] {
    background-color: #1F3C73 !important;
    color: #FFFFFF !important;
}

/* Título centralizado */
h1 {
    text-align: center;
}

/* Contêiner principal para centralizar o chat */
.chat-container {
    max-width: 800px;
    margin: 0 auto;
    margin-top: 30px;
}

/* Mensagens do usuário (Gold) e do assistente (também Gold, para uniformidade) */
[data-testid="stChatMessage-user"],
[data-testid="stChatMessage-assistant"] {
    background-color: #C9A15D !important;
    color: #000000 !important;
    margin-bottom: 10px;
    border-radius: 8px;
    padding: 10px;
    width: 100%;
    box-shadow: 0 2px 4px rgba(0,0,0,0.3);
}

/* Ajusta fonte geral */
html, body, [class*="css"] {
    font-family: "Arial", sans-serif;
}
</style>
"""
st.markdown(css, unsafe_allow_html=True)

# ------------------------ FUNÇÃO DE BUSCA NO GOOGLE ------------------------
def google_search(query):
    """
    Realiza uma busca no Google e retorna os 3 primeiros resultados (URLs).
    """
    results = []
    try:
        for url in search(query, tld="com", num=3, stop=3, pause=2):
            results.append(url)
    except Exception as e:
        st.error(f"Erro ao buscar na web: {e}")
    return results

# ------------------------ FUNÇÕES COM CACHE ------------------------
@st.cache_data
def load_documents():
    """Carrega os documentos do CSV uma única vez."""
    loader = CSVLoader(file_path="merged_data.csv", encoding="utf-8")
    documents = list(loader.lazy_load())
    return documents

@st.cache_resource
def get_vectorstore():
    """
    Cria e retorna o índice vetorial utilizando embeddings.
    Se já existir um índice pré-computado em 'faiss_index.pkl', ele é carregado.
    Caso contrário, é gerado e salvo para futuras execuções.
    """
    index_file = "faiss_index.pkl"
    # Verifica se o índice já foi salvo localmente
    if os.path.exists(index_file):
        try:
            with open(index_file, "rb") as f:
                vectorstore = pickle.load(f)
            st.info("Índice vetorial carregado a partir do arquivo pré-computado.")
            return vectorstore
        except Exception as e:
            st.error(f"Erro ao carregar o índice salvo: {e}")
    
    # Se não existir, cria o índice e o salva
    documents = load_documents()  # Obtém os documentos internamente
    embeddings = OpenAIEmbeddings()
    vectorstore = FAISS.from_documents(documents, embeddings)
    
    try:
        with open(index_file, "wb") as f:
            pickle.dump(vectorstore, f)
        st.info("Índice vetorial criado e salvo com sucesso.")
    except Exception as e:
        st.error(f"Erro ao salvar o índice: {e}")
    return vectorstore

# Carregar o índice vetorial (aproveitando o cache)
db = get_vectorstore()

def retrieve_info(query):
    similar_response = db.similarity_search(query, k=3)
    return [doc.page_content for doc in similar_response]

# ------------------------ FUNÇÕES PARA PROCESSAR PDF ------------------------
def process_pdf(file) -> list:
    """
    Lê um arquivo PDF, extrai o texto e procura por códigos IMPA (6 dígitos).
    Para cada código encontrado, tenta capturar a linha onde ele aparece (como contexto).
    Retorna uma lista de tuplas: (codigo, contexto).
    """
    try:
        pdf_reader = PyPDF2.PdfReader(file)
    except Exception as e:
        st.error(f"Erro ao ler o PDF {file.name}: {e}")
        return []
    
    full_text = ""
    for page in pdf_reader.pages:
        text = page.extract_text()
        if text:
            full_text += text + "\n"
    
    pattern = re.compile(r'(\d{6})')  # Busca sequências de 6 dígitos
    matches = pattern.findall(full_text)
    unique_codes = list(set(matches))
    
    results = []
    lines = full_text.splitlines()
    for code in unique_codes:
        for line in lines:
            if code in line:
                results.append((code, line.strip()))
                break
    return results

def is_valid_product_context(context: str) -> bool:
    """
    Utiliza o modelo para verificar se o trecho extraído descreve um produto real.
    Responde 'sim' ou 'não'. Se a resposta for 'sim', consideramos o contexto válido.
    """
    prompt = (
        f"Você é um especialista em análise de textos de produtos marítimos. Dado o seguinte trecho:\n\n"
        f"\"{context}\"\n\n"
        f"Esse trecho descreve um produto real (com informações sobre características, aplicações ou especificações) e não apenas dados irrelevantes? Responda apenas 'sim' ou 'não'."
    )
    message = HumanMessage(content=prompt)
    response = lm([message])
    answer = response.content.strip().lower()
    return answer.startswith("sim")

def lookup_product(code: str, context: str) -> str:
    """
    Tenta identificar o produto usando o código IMPA e o contexto extraído.
    Se a consulta com o código retornar uma descrição válida (mínimo 20 caracteres),
    gera uma breve explicação que inclui o código. Caso contrário, tenta com o contexto
    sozinho e informa que o código não foi localizado.
    Se não houver informação válida, retorna string vazia.
    """
    if not is_valid_product_context(context):
        return ""
    
    query_with_code = f"IMPA {code} {context}"
    info_with_code = retrieve_info(query_with_code)
    if info_with_code and len(info_with_code[0].strip()) >= 20:
        prompt = (
            f"Você é uma vendedora de materiais marítimos. Com base na seguinte descrição de um produto:\n\n"
            f"{info_with_code[0]}\n\n"
            f"Forneça uma explicação breve e clara sobre esse produto, destacando suas principais características e aplicações."
        )
        sales_message = HumanMessage(content=prompt)
        sales_response = lm([sales_message])
        return sales_response.content.strip() + f"\n(Código IMPA: {code})"
    else:
        info_without_code = retrieve_info(context)
        if info_without_code and len(info_without_code[0].strip()) >= 20:
            prompt = (
                f"Você é uma vendedora de materiais marítimos. Com base na seguinte descrição de um produto:\n\n"
                f"{info_without_code[0]}\n\n"
                f"Forneça uma explicação breve e clara sobre esse produto, destacando suas principais características e aplicações.\n"
                f"(Observação: o código IMPA não foi localizado no arquivo.)"
            )
            sales_message = HumanMessage(content=prompt)
            sales_response = lm([sales_message])
            return sales_response.content.strip()
        else:
            return ""

# ------------------------ INICIALIZA O MODELO DE CHAT ------------------------
lm = ChatOpenAI(temperature=0, model="gpt-4o-mini")

# ------------------------ TEMPLATE DA ASSISTENTE ------------------------
template = """Você é uma assistente virtual altamente especializada que trabalha para a NavSupply, uma empresa de vendas marítimas. Seu papel é apoiar os compradores de materiais da empresa, respondendo a dúvidas e fornecendo informações precisas sobre temas relacionados ao setor marítimo. Para desempenhar essa função, você deve possuir amplo conhecimento em diversas áreas, incluindo:

Navegação: Entendimento dos conceitos básicos e avançados de navegação, regulamentações marítimas, rotas e procedimentos de segurança.
Comércio Exterior: Conhecimento sobre importação, exportação, regulamentações alfandegárias e processos de logística internacional.
Navios e Transporte Marítimo: Informações detalhadas sobre diferentes tipos de navios, suas funções, especificações técnicas e operações.
Tripulação e Operações: Conhecimento sobre as funções e responsabilidades da tripulação, gestão de pessoal a bordo e procedimentos de emergência.
Componentes e Equipamentos de Navios: Familiaridade com os diversos objetos e materiais utilizados em navios, desde equipamentos de navegação até itens de manutenção.
Materiais de Salvamento: Conhecimento dos dispositivos e materiais essenciais para a segurança e salvamento no mar.
Códigos e Normas IMPA: Entendimento das diretrizes e códigos IMPA (International Marine Purchasing Association) que regulam processos e práticas de compras e manutenção no setor marítimo.
Sua comunicação deve ser clara, objetiva e precisa, de modo a fornecer respostas que auxiliem os compradores na tomada de decisões informadas sobre a aquisição de materiais e na resolução de dúvidas técnicas e operacionais.
Além disso, se a consulta estiver relacionada a algum material específico, forneça uma descrição detalhada sobre sua aplicação e para que ele é utilizado, de modo a ajudar o comprador que não conhece o material."""
 
# ------------------------ INTERFACE DE CHAT ------------------------
st.title("Assistente Virtual NavSupply")
st.markdown('<div class="chat-container">', unsafe_allow_html=True)

# Histórico de conversa (armazenado na sessão)
if "conversation" not in st.session_state:
    st.session_state.conversation = []

for message in st.session_state.conversation:
    if message["role"] == "user":
        st.chat_message("user").write(message["content"])
    else:
        st.chat_message("assistant").write(message["content"])

user_input = st.chat_input("Digite sua pergunta:")

if user_input:
    st.session_state.conversation.append({"role": "user", "content": user_input})
    st.chat_message("user").write(user_input)
    
    context_info = retrieve_info(user_input)
    if not context_info or all(not item.strip() for item in context_info):
        web_results = google_search(user_input)
        web_context = "\n".join(web_results)
        final_context = f"Resultados da Web:\n{web_context}"
    else:
        final_context = "Contexto do CSV:\n" + "\n".join(context_info)
    
    full_prompt = f"{template}\n\n{final_context}\n\nPergunta: {user_input}"
    messages = [HumanMessage(content=full_prompt)]
    response = lm(messages)
    answer = response.content
    
    st.session_state.conversation.append({"role": "assistant", "content": answer})
    st.chat_message("assistant").write(answer)

st.markdown('</div>', unsafe_allow_html=True)

# ------------------------ UPLOAD E PROCESSAMENTO DE PDF ------------------------
st.header("Anexar PDFs para identificar itens")
uploaded_files = st.file_uploader("Selecione um ou mais arquivos PDF", type=["pdf"], accept_multiple_files=True)

if uploaded_files:
    for uploaded_file in uploaded_files:
        st.subheader(f"Processando arquivo: {uploaded_file.name}")
        pdf_results = process_pdf(uploaded_file)
        if pdf_results:
            for code, context in pdf_results:
                if is_valid_product_context(context):
                    st.write(f"**Código IMPA encontrado:** {code}")
                    st.write(f"**Contexto extraído:** {context}")
                    product_info = lookup_product(code, context)
                    if product_info:
                        st.write("**Produto Identificado:**")
                        st.write(product_info)
                        st.markdown("---")
        else:
            st.write("Nenhum código IMPA encontrado neste arquivo.")
