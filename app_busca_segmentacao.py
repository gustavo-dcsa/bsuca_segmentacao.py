import streamlit as st
import pandas as pd
import google.generativeai as genai
import json
import os
import re
import asyncio
import time
from unidecode import unidecode
from dotenv import load_dotenv
from datetime import datetime

# --- CONFIGURAÇÃO INICIAL ---
load_dotenv()
st.set_page_config(page_title="Segmentação Médica IA", layout="wide", page_icon="🩺")

# Configurações Globais
CARREGAR_DADOS_AO_INICIAR = True
DIR_BASES = "bases"
FILE_PATH_MAIN = os.path.join(DIR_BASES, "classificacao_procedimentos.csv")
FILE_PATH_ERRORS = os.path.join(DIR_BASES, "inconsistencias.csv")
API_KEY = os.getenv("API_PROJETOS_UNI_GMINAI")
MAX_CONCURRENT_REQUESTS = 5

# Colunas Oficiais
COLS_FULL = [
    "CODIGO", "DESCRICAO", "ABREVIATURA", "ITEM", "SEGMENTACAO",
    "TERAPIA_ESPECIAL", "TIPO_MEDICAMENTO", "TIPO_CANCER",
    "CODIGO_SUGERIDO", "DESCRICAO_SUGERIDA", "NIVEL_CONFIANCA",
    "JUSTIFICATIVA", "DATA_MODIFICACAO"
]
# Verifica e cria diretório de bases se não existir
if not os.path.exists(DIR_BASES):
    os.makedirs(DIR_BASES)

if not API_KEY:
    st.error("⚠️ API Key não encontrada no arquivo .env")
    st.stop()

# Configuração da IA com JSON Mode e Safety Settings permissivos para termos médicos
genai.configure(api_key=API_KEY)
GENERATION_CONFIG = {
    "temperature": 0.2,
    "top_p": 0.95,
    "top_k": 40,
    "response_mime_type": "application/json",
}

SAFETY_SETTINGS = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]
# --- FUNÇÕES UTILITÁRIAS ---


def normalizar_texto(texto):
    """Remove acentos, espaços extras e converte para maiúsculo."""
    if not isinstance(texto, str):
        return ""
    return unidecode(texto).strip().upper()


def validar_codigo_tuss(codigo):
    """Valida se tem 8 dígitos numéricos."""
    if not codigo:
        return False
    clean = re.sub(r'\D', '', str(codigo))
    return bool(re.match(r'^\d{8}$', clean))


def carregar_dados():
    """Carrega as bases de dados ou cria vazias se não existirem."""
    if "main_df" not in st.session_state:
        if os.path.exists(FILE_PATH_MAIN):
            st.session_state.main_df = pd.read_csv(FILE_PATH_MAIN, sep=";", dtype=str, encoding='latin1')
        else:
            st.session_state.main_df = pd.DataFrame(columns=COLS_FULL)

    if "inconsistencias_df" not in st.session_state:
        if os.path.exists(FILE_PATH_ERRORS):
            st.session_state.inconsistencias_df = pd.read_csv(FILE_PATH_ERRORS, sep=";", dtype=str, encoding='latin1')
        else:
            st.session_state.inconsistencias_df = pd.DataFrame(columns=COLS_FULL)


def salvar_dados():
    """Persiste os dataframes em CSV."""
    st.session_state.main_df.to_csv(FILE_PATH_MAIN, sep=";", index=False, encoding='latin1')
    st.session_state.inconsistencias_df.to_csv(FILE_PATH_ERRORS, sep=";", index=False, encoding='latin1')


def get_few_shot_context():
    """Pega exemplos de alta confiança da base para treinar a IA (Few-Shot)."""
    if "main_df" not in st.session_state or st.session_state.main_df.empty:
        return ""

    exemplos = st.session_state.main_df[st.session_state.main_df["NIVEL_CONFIANCA"] == "ALTO"]
    if exemplos.empty:
        return ""

    sample = exemplos.sample(n=min(3, len(exemplos)))
    texto_exemplos = []
    for _, row in exemplos.iterrows():
        ex_json = {
            "entrada_descricao": row["DESCRICAO"],
            "saida_esperada": {
                "abreviatura": row["ABREVIATURA"],
                "tipo_medicamento": row["TIPO_MEDICAMENTO"],
                "tipo_cancer": row["TIPO_CANCER"],
                "nivel_confianca": row["NIVEL_CONFIANCA"],
                "justificativa": row["JUSTIFICATIVA"],
                "descricao_sugerida": row["DESCRICAO_SUGERIDA"],
                "codigo_sugerido": row["CODIGO_SUGERIDO"],
                "item": row["ITEM"],
                "segmentacao": row["SEGMENTACAO"],
                "terapia_especial": row["TERAPIA_ESPECIAL"],
                "codigo_sugerido": row["CODIGO_SUGERIDO"]
            }
        }
        texto_exemplos.append(json.dumps(ex_json, ensure_ascii=False))

    return "\n".join(texto_exemplos)


def get_prompt():
    try:
        with open("prompt_classificacao.md", "r", encoding="utf-8") as f:
            base = f.read()

        # Injeta few-shot se houver placeholder, senão concatena
        few_shot = get_few_shot_context()
        if "{{FEW_SHOT_EXAMPLES}}" in base:
            return base.replace("{{FEW_SHOT_EXAMPLES}}", few_shot)
        else:
            # Fallback se não tiver a tag
            return base + "\n\nEXEMPLOS:\n" + few_shot

    except Exception as e:
        st.error(f"Erro ao ler arquivo prompt_classificacao.md: {e}")
        return ""


def exibir_resultado(resultado_final, msg_base=""):
    """Exibe resultado estruturado de forma consistente."""
    st.markdown("### Resultado Encontrado")
    # Seção Principal: 3 Colunas Grandes
    col1, col2, col3 = st.columns(3)
    with col1:
        st.subheader("Descrição")
        st.write(resultado_final.get("DESCRICAO_SUGERIDA") or resultado_final.get("DESCRICAO", ""))
    with col2:
        st.subheader("Código")
        st.write(resultado_final.get("CODIGO_SUGERIDO") or resultado_final.get("CODIGO", ""))
    with col3:
        conf = resultado_final.get("NIVEL_CONFIANCA", "ALTO")
        cor_conf = "green" if conf == "ALTO" else "orange" if conf == "MEDIO" else "red"
        st.subheader("Nível de Confiança")
        st.markdown(f":{cor_conf}[**{conf}**]")
    # Seção Detalhes Específicos
    st.markdown("---")
    col_det1, col_det2 = st.columns(2)
    with col_det1:
        if resultado_final.get("ITEM"):
            st.write(f"**Item:** {resultado_final['ITEM']}")
        st.write(f"**Segmentação:** {resultado_final.get('SEGMENTACAO', '')}")
    with col_det2:
        seg = resultado_final.get("SEGMENTACAO", "")
        item = resultado_final.get("ITEM", "")
        if seg == "SAT":
            st.write(f"**Terapia Especial:** {resultado_final.get('TERAPIA_ESPECIAL', '')}")
        elif item == "MEDICAMENTOS":
            st.write(f"**Tipo Medicamento:** {resultado_final.get('TIPO_MEDICAMENTO', '')}")
            st.write(f"**Tipo Câncer:** {resultado_final.get('TIPO_CANCER', '')}")
    # Justificativa em texto menor
    st.markdown("---")
    st.caption(f"📝 **Justificativa:** {resultado_final.get('JUSTIFICATIVA', msg_base)}")


# --- ENGINE DE BUSCA E IA ---


async def consulta_gemini_1sync(model, prompt, semaphore):
    async with semaphore:
        try:
            # Executa em thread separada para não bloquear o loop de eventos
            response = await asyncio.to_thread(
                model.generate_content,
                prompt,
                generation_config=GENERATION_CONFIG,
                safety_settings=SAFETY_SETTINGS
            )

            # Como configuramos response_mime_type="application/json",
            # response.text já deve ser um JSON válido.
            try:
                return json.loads(response.text)
            except json.JSONDecodeError:
                # Fallback: Tenta limpar caso a API devolva markdown mesmo assim
                clean_text = response.text.replace("```json", "").replace("```", "").strip()
                return json.loads(clean_text)

        except Exception as e:
            return {"nivel_confianca": "ERRO", "justificativa": f"Erro API: {str(e)}"}


def buscar_na_base_local(codigo=None, descricao=None):
    """
    Busca hierárquica na base local.
    Retorna (Encontrado: bool, Dados: dict/row)
    """
    df = st.session_state.main_df
    if df.empty:
        return False, None, "Base vazia"

    # 1. Busca por Código Exato
    if codigo:
        cod_norm = str(codigo).strip()
        res_cod = df[df["CODIGO"] == cod_norm]
        if not res_cod.empty:
            return True, res_cod.iloc[0].to_dict(), "Código encontrado na base."

    # 2. Busca por Descrição Exata (Normalizada)
    if descricao:
        desc_norm = normalizar_texto(descricao)
        # Cria coluna temporária para busca (não salva)
        temp_desc = df["DESCRICAO"].apply(normalizar_texto)
        idx_match = temp_desc[temp_desc == desc_norm].index

        if not idx_match.empty:
            return True, df.loc[idx_match[0]].to_dict(), "Descrição exata encontrada na base."

    return False, None, "Não encontrado."


def processar_resultado_ia(dados_ia, codigo_input, descricao_input):
    confianca = dados_ia.get("nivel_confianca", "BAIXO")
    cod_sugerido = dados_ia.get("codigo_sugerido", "")
    justificativa = dados_ia.get("justificativa", "")

    # Validação Cruzada de Código TUSS
    if cod_sugerido and not validar_codigo_tuss(cod_sugerido):
        confianca = "BAIXO"
        justificativa += " [ALERTA: Código sugerido inválido]"

    return {
        "CODIGO": codigo_input if codigo_input else "",
        "DESCRICAO": descricao_input,
        "ABREVIATURA": dados_ia.get("abreviatura", ""),
        "ITEM": dados_ia.get("item", ""),
        "SEGMENTACAO": dados_ia.get("segmentacao", ""),
        "TERAPIA_ESPECIAL": dados_ia.get("terapia_especial", "NÃO"),
        "TIPO_MEDICAMENTO": dados_ia.get("tipo_medicamento", ""),
        "TIPO_CANCER": dados_ia.get("tipo_cancer", ""),
        "CODIGO_SUGERIDO": cod_sugerido,
        "DESCRICAO_SUGERIDA": dados_ia.get("descricao_sugerida", ""),
        "NIVEL_CONFIANCA": confianca,
        "JUSTIFICATIVA": justificativa,
        "DATA_MODIFICACAO": datetime.now().strftime("%d/%m/%Y")
    }


async def processar_lote_async(df_batch):
    """Processa DataFrame em lote."""
    model = genai.GenerativeModel('gemini-2.5-flash')
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    prompt_base = get_prompt()
    if not prompt_base:
        return []

    tasks = []

    for idx, row in df_batch.iterrows():
        cod = str(row.get("CODIGO", "")).replace("nan", "")
        desc = str(row.get("DESCRICAO_BUSCA", ""))

        # 1. Verifica Base Local Antes
        found, data_local, _ = buscar_na_base_local(cod, desc)

        if found:
            # Se achou, já retorna formatado como task concluída (fake async)
            future = asyncio.Future()
            future.set_result({**data_local, "NIVEL_CONFIANCA": "ALTO", "JUSTIFICATIVA": "Encontrado na Base Local"})
            tasks.append(future)
        else:
            # Se não, prepara chamada IA
            user_msg = prompt_base.replace("{{CODIGO_USUARIO}}", cod).replace("{{DESCRICAO_USUARIO}}", desc)
            tasks.append(consulta_gemini_1sync(model, user_msg, semaphore))

    results_raw = await asyncio.gather(*tasks)

    final_results = []
    for i, res in enumerate(results_raw):
        # Se for resultado da IA, precisa formatar. Se veio do banco, já é dict
        if "segmentacao" in res:  # Veio da IA (formato JSON chaves minusculas)
            row_orig = df_batch.iloc[i]
            formatted = processar_resultado_ia(res, row_orig.get("CODIGO", ""), row_orig.get("DESCRICAO_BUSCA", ""))
            final_results.append(formatted)
        else:  # Veio do banco (formato chaves maiusculas)
            res["DATA_MODIFICACAO"] = datetime.now().strftime("%d/%m/%y")
            final_results.append(res)

    return final_results


def classificar_dados():
    """
    Classifica campos em branco/nulos da base usando IA de forma eficiente.
    """
    # carregar_dados() -> Assumindo que carrega no st.session_state.main_df
    # Para o exemplo, vamos garantir que carrega aqui ou já foi carregado
    if 'main_df' not in st.session_state or st.session_state.main_df.empty:
        # carregar_dados() # Descomente se sua função de carregar for necessária aqui
        return

    prompt_base = get_prompt()

    # Identifica linhas que precisam processamento
    df = st.session_state.main_df.copy()

    # --- (SEUS FILTROS ORIGINAIS MANTIDOS) ---
    # Filtro 1: ITEM vazio/nulo
    mask_item_vazio = (df['ITEM'].isna()) | (df['ITEM'] == '')
    indices_item = df[mask_item_vazio & (df['DESCRICAO'] != '')].index.tolist()

    # Filtro 2: ITEM = "SERVIÇO" ou "MEDICAMENTOS" com SEGMENTACAO vazio/nulo
    mask_item_servico_med = df['ITEM'].isin(['SERVIÇO', 'MEDICAMENTOS'])
    mask_segmentacao_vazio = (df['SEGMENTACAO'].isna()) | (df['SEGMENTACAO'] == '')
    indices_segmentacao = df[mask_item_servico_med & mask_segmentacao_vazio & (df['DESCRICAO'] != '')].index.tolist()

    # Filtro 3: SEGMENTACAO = "SAT" com TERAPIA_ESPECIAL vazio/nulo
    mask_sat = df['SEGMENTACAO'] == 'SAT'
    mask_terapia_vazio = (df['TERAPIA_ESPECIAL'].isna()) | (df['TERAPIA_ESPECIAL'] == '')
    indices_terapia = df[mask_sat & mask_terapia_vazio & (df['DESCRICAO'] != '')].index.tolist()

    # Filtro 4: SEGMENTACAO = "SAT" com ABREVIATURA vazio/nulo
    mask_sat = df['SEGMENTACAO'] == 'SAT'
    mask_abreviatura_vazio = (df['ABREVIATURA'].isna()) | (df['ABREVIATURA'] == '')
    indices_abreviatura = df[mask_sat & mask_abreviatura_vazio & (df['DESCRICAO'] != '')].index.tolist()

    # Filtro 5: ITEM = "MEDICAMENTOS" com TIPO_MEDICAMENTO ou TIPO_CANCER vazios/nulos
    mask_medicamento = df['ITEM'] == 'MEDICAMENTOS'
    mask_tipo_med_vazio = (df['TIPO_MEDICAMENTO'].isna()) | (df['TIPO_MEDICAMENTO'] == '')
    mask_tipo_cancer_vazio = (df['TIPO_CANCER'].isna()) | (df['TIPO_CANCER'] == '')
    indices_medicamento = df[mask_medicamento & (mask_tipo_med_vazio | mask_tipo_cancer_vazio) & (df['DESCRICAO'] != '')].index.tolist()
    # -----------------------------------------

    # Combina todos os índices únicos
    indices_processar = sorted(set(indices_item + indices_segmentacao + indices_terapia + indices_medicamento + indices_abreviatura))

    if not indices_processar:
        st.success("A base já está enriquecida! Nenhuma atualização necessária.")
        time.sleep(1)  # Pequena pausa para o usuário ler
        return

    # ### UI UPDATE: Inicializa elementos visuais ###
    st.info(f"Iniciando enriquecimento da base. Total de registros a processar: {len(indices_processar)}")
    barra_progresso = st.progress(0)
    status_text = st.empty()  # Placeholder para o texto mudando

    # Processa apenas as linhas que precisam
    model = genai.GenerativeModel('gemini-2.5-flash')

    total_items = len(indices_processar)

    for i, idx in enumerate(indices_processar):
        row = df.loc[idx]
        codigo = str(row.get('CODIGO', '')).strip()
        descricao = str(row.get('DESCRICAO', '')).strip()

        # ### UI UPDATE: Atualiza a interface a cada iteração ###
        # Calcula porcentagem (0.0 a 1.0)
        progresso = (i + 1) / total_items
        barra_progresso.progress(progresso)

        # Mostra spinner e texto
        status_text.markdown(f"""
        Running... Processando item {i+1}/{total_items}:
        \n**Código:** `{codigo}`
        \n**Descrição:** *{descricao}*
        """)

        # Pula linhas sem descrição válida
        if not descricao or descricao == '':
            continue

        try:
            # Consulta IA com a descrição
            user_msg = prompt_base.replace("{{CODIGO_USUARIO}}", codigo).replace("{{DESCRICAO_USUARIO}}", descricao)
            response = model.generate_content(user_msg)

            # Limpeza básica do json markdown
            raw_text = response.text.replace("```json", "").replace("```", "").strip()
            res_json = json.loads(raw_text)

            resultado_final = processar_resultado_ia(res_json, codigo, descricao)
            resultado_final["DATA_MODIFICACAO"] = datetime.now().strftime("%d/%m/%y")

            # --- Lógica de atualização do DataFrame (Mantida igual) ---
            mask_match = (st.session_state.main_df['CODIGO'] == codigo) & (st.session_state.main_df['DESCRICAO'] == descricao)
            matching_indices = st.session_state.main_df[mask_match].index.tolist()

            if not matching_indices:
                continue

            linha_idx = matching_indices[0]

            for col in COLS_FULL:
                if col not in ['DESCRICAO_SUGERIDA', 'NIVEL_CONFIANCA', 'JUSTIFICATIVA', 'DATA_MODIFICACAO']:
                    valor_atual = st.session_state.main_df.at[linha_idx, col]
                    if pd.isna(valor_atual) or valor_atual == '':
                        if col in resultado_final and resultado_final[col]:
                            st.session_state.main_df.at[linha_idx, col] = resultado_final[col]

            st.session_state.main_df.at[linha_idx, 'DESCRICAO_SUGERIDA'] = resultado_final.get('DESCRICAO_SUGERIDA', '')
            st.session_state.main_df.at[linha_idx, 'NIVEL_CONFIANCA'] = resultado_final.get('NIVEL_CONFIANCA', 'BAIXO')
            st.session_state.main_df.at[linha_idx, 'JUSTIFICATIVA'] = resultado_final.get('JUSTIFICATIVA', '')
            st.session_state.main_df.at[linha_idx, 'DATA_MODIFICACAO'] = resultado_final['DATA_MODIFICACAO']

            # Verifica confiança e move para inconsistências
            confianca = resultado_final.get('NIVEL_CONFIANCA', 'BAIXO')
            if confianca in ['BAIXO', 'MEDIO']:
                linha_para_mover = st.session_state.main_df.loc[linha_idx].to_dict()
                st.session_state.main_df.drop(linha_idx, inplace=True)
                st.session_state.inconsistencias_df = pd.concat(
                    [st.session_state.inconsistencias_df, pd.DataFrame([linha_para_mover])],
                    ignore_index=True
                )

            # Salva após cada busca
            salvar_dados()

        except Exception as e:
            # Opcional: Mostrar erro na tela
            # st.error(f"Erro ao processar {descricao}: {e}")
            continue

    # Finalização da função
    st.session_state.main_df.drop_duplicates(subset=['CODIGO', 'DESCRICAO'], keep='first', inplace=True)

    # Ordenação
    st.session_state.main_df['DATA_MODIFICACAO'] = pd.to_datetime(
        st.session_state.main_df['DATA_MODIFICACAO'],
        format='%d/%m/%y',
        errors='coerce'
    )
    st.session_state.main_df.sort_values(by='DATA_MODIFICACAO', ascending=False, inplace=True)
    st.session_state.main_df['DATA_MODIFICACAO'] = st.session_state.main_df['DATA_MODIFICACAO'].dt.strftime('%d/%m/%y')
    st.session_state.main_df.reset_index(drop=True, inplace=True)

    salvar_dados()

    # ### UI UPDATE: Mensagem final ###
    status_text.text("Processo finalizado com sucesso!")
    barra_progresso.progress(100)
    time.sleep(1.5)  # Pausa para ver o 100%


# --- LÓGICA DE INICIALIZAÇÃO DO APP ---

# Verificamos se já rodou. Se NÃO rodou, criamos um placeholder que ocupa a tela.
if "dados_classificados" not in st.session_state:

    # Criamos um container vazio para segurar a tela de "Loading"
    loading_placeholder = st.empty()

    with loading_placeholder.container():
        st.header("🚀 Iniciando Aplicação")
        st.write("Aguarde enquanto enriquecemos a base de dados com IA...")

        # Chama a função que agora tem os prints visuais dentro dela
        # Usamos um spinner geral, mas a barra de progresso interna da função fará o detalhamento
        with st.spinner('Preparando o ambiente...'):
            classificar_dados()

    # Quando a função retorna, limpamos o container de loading
    loading_placeholder.empty()

    # Marcamos como feito
    st.session_state.dados_classificados = True

    # Opcional: Rerun para garantir que a tela limpa renderize o main limpo imediatamente
    st.rerun()

carregar_dados()

# BARRA LATERAL (NAVEGAÇÃO E DOWNLOADS)
st.sidebar.image("C:/Users/gustavo.santos/Documents/Imagens e Icones/Icones/hospital (1).png", width=60)
st.sidebar.title("Classificador de Procedimentos")
page = st.sidebar.radio("Navegação", ["🔍 Busca Individual", "🚀 Busca em Lote", "🛠️ Corrigir e Treinar"])

st.sidebar.markdown("---")
st.sidebar.header("📩 Downloads")
st.sidebar.download_button(
    "Baixar Base Oficial (.csv)",
    st.session_state.main_df.to_csv(sep=";", index=False, encoding='utf-8').encode("utf-8"),
    "classificacao_procedimentos.csv"
)
st.sidebar.download_button(
    "Baixar Inconsistências (.csv)",
    st.session_state.inconsistencias_df.to_csv(sep=";", index=False, encoding='utf-8').encode("utf-8"),
    "inconsistencias.csv"
)

# PÁGINA 1: BUSCA INDIVIDUAL
if page == "🔍 Busca Individual":
    st.header("Busca e Classificação Individual")

    c1, c2 = st.columns([1, 3])
    input_cod = c1.text_input("Código (Opcional)", placeholder="Ex: 50000160")
    input_desc = c2.text_input("Descrição do Procedimento", placeholder="Ex: SESSÃO DE PSICOMOTRICIDADE")

    if st.button("Pesquisar / Classificar", type="primary"):
        if not input_cod and not input_desc:
            st.warning("❗Por favor, insira pelo menos um campo: Código ou Descrição.")
            st.stop()
        # LÓGICA DE BUSCA SOLICITADA
        # Caso 1: Só Código (Sem descrição)
        if input_cod and not input_desc:
            found, data, msg = buscar_na_base_local(codigo=input_cod)
            if found:
                st.success(msg)
                exibir_resultado(data, msg)
                # Tabela de Resultados
                st.markdown("---")
                st.dataframe(pd.DataFrame([data]))
            else:
                st.error("❌ Código não localizado na base local.")
                st.warning("Por favor, insira uma DESCRIÇÃO para permitir a busca aprofundada via IA.")

        # Caso 2 e 3: Tem Descrição (Com ou Sem Código)
        elif input_desc:
            # Passo A: Busca Local
            found, data, msg = buscar_na_base_local(codigo=input_cod, descricao=input_desc)

            if found:
                st.success(msg)
                exibir_resultado(data, msg)
                # Tabela de Resultados
                st.markdown("---")
                st.dataframe(pd.DataFrame([data]))

            else:
                # Passo B: Busca IA
                st.info("🔎 Não encontrado localmente. Consultando Agente IA (TUSS/CBHPM/ANS)...")

                with st.spinner("Analisando regras de negócio e similaridade..."):
                    model = genai.GenerativeModel('gemini-2.5-flash')
                    prompt = st.session_state.get('prompt_base', get_prompt())
                    user_msg = prompt.replace("{{CODIGO_USUARIO}}", input_cod).replace("{{DESCRICAO_USUARIO}}", input_desc)

                    try:
                        response = model.generate_content(user_msg)
                        res_json = json.loads(response.text.replace("```json", "").replace("```", "").strip())

                        resultado_final = processar_resultado_ia(res_json, input_cod, input_desc)
                        resultado_final["DATA_MODIFICACAO"] = datetime.now().strftime("%d/%m/%y")

                        st.markdown("### Resultado da IA")

                        # Exibição Visual - Resultado Estruturado
                        resultado_final = processar_resultado_ia(res_json, input_cod, input_desc)

                        # Seção Principal: 3 Colunas Grandes
                        col1, col2, col3 = st.columns(3)

                        with col1:
                            st.subheader("Descrição Sugerida")
                            st.write(resultado_final["DESCRICAO_SUGERIDA"] or resultado_final["DESCRICAO"])

                        with col2:
                            st.subheader("Código Sugerido")
                            st.write(resultado_final["CODIGO_SUGERIDO"] or resultado_final["CODIGO"])

                        with col3:
                            conf = resultado_final["NIVEL_CONFIANCA"]
                            cor_conf = "green" if conf == "ALTO" else "orange" if conf == "MEDIO" else "red"
                            st.subheader("Nível de Confiança")
                            st.markdown(f":{cor_conf}[**{conf}**]")

                        # Seção Detalhes Específicos
                        st.markdown("---")
                        col_det1, col_det2 = st.columns(2)

                        with col_det1:
                            if resultado_final["ITEM"]:
                                st.write(f"**Item:** {resultado_final['ITEM']}")
                            st.write(f"**Segmentação:** {resultado_final['SEGMENTACAO']}")

                        with col_det2:
                            if resultado_final["SEGMENTACAO"] == "SAT":
                                st.write(f"**TERAPIA_ESPECIAL:** {resultado_final['TERAPIA_ESPECIAL']}")
                            elif resultado_final["ITEM"] == "MEDICAMENTOS":
                                st.write(f"**Tipo Medicamento:** {resultado_final['TIPO_MEDICAMENTO']}")
                                st.write(f"**Tipo Câncer:** {resultado_final['TIPO_CANCER']}")

                        # Justificativa em texto menor
                        st.markdown("---")
                        st.caption(f"📝 **Justificativa:** {resultado_final['JUSTIFICATIVA']}")
                        st.caption(f"📅 **Data de Classificação:** {resultado_final['DATA_MODIFICACAO']}")

                        # JSON Completo
                        with st.expander("Ver Dados Completos (JSON)"):
                            st.json(resultado_final)

                        # Persistência Automática
                        if conf == "ALTO":
                            st.session_state.main_df = pd.concat([st.session_state.main_df, pd.DataFrame([resultado_final])], ignore_index=True)
                            st.toast("Salvo na Base Oficial (Confiança Alta)", icon="✅")
                        else:
                            st.session_state.inconsistencias_df = pd.concat([st.session_state.inconsistencias_df, pd.DataFrame([resultado_final])], ignore_index=True)
                            st.toast("Enviado para Inconsistências (Revisão Necessária)", icon="⚠️")

                        salvar_dados()

                    except Exception as e:
                        st.error(f"Erro na comunicação com a IA: {e}")
        else:
            st.warning("Preencha pelo menos um campo.")

# PÁGINA 2: LOTE
elif page == "🚀 Busca em Lote":
    st.header("Processamento em Lote (IA)")
    st.markdown("Faça upload de um CSV contendo a coluna ```DESCRICAO_BUSCA```.")

    uploaded = st.file_uploader("Arquivo CSV", type=["csv"])

    if uploaded:
        df_up = pd.read_csv(uploaded, sep=";", dtype=str, encoding='utf-8')
        if "DESCRICAO_BUSCA" not in df_up.columns:
            df_up = pd.read_csv(uploaded, sep=",", dtype=str, encoding='utf-8')  # Tenta vírgula

        if "DESCRICAO_BUSCA" in df_up.columns:
            st.info(f"{len(df_up)} registros carregados.")

            if st.button("Iniciar Processamento"):
                progress_bar = st.progress(0, "Iniciando...")

                # Loop Assíncrono
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                resultados = loop.run_until_complete(processar_lote_async(df_up))

                progress_bar.progress(100, "Concluído!")

                # Separação e Salvamento
                novos_altos = [r for r in resultados if r["NIVEL_CONFIANCA"] == "ALTO"]
                novos_baixos = [r for r in resultados if r["NIVEL_CONFIANCA"] != "ALTO"]

                if novos_altos:
                    st.session_state.main_df = pd.concat([st.session_state.main_df, pd.DataFrame(novos_altos)], ignore_index=True)
                if novos_baixos:
                    st.session_state.inconsistencias_df = pd.concat([st.session_state.inconsistencias_df, pd.DataFrame(novos_baixos)], ignore_index=True)

                salvar_dados()

                # Resumo
                c1, c2 = st.columns(2)
                c1.success(f"✅ {len(novos_altos)} salvos na Base Oficial")
                c2.warning(f"⚠️ {len(novos_baixos)} enviados para Inconsistências")

                # Download do Lote Processado (Independente do destino)
                df_resultado_lote = pd.DataFrame(resultados)
                st.download_button(
                    "📥 Baixar Resultado Deste Lote Completo",
                    df_resultado_lote.to_csv(sep=";", index=False, encoding='utf-8').encode("utf-8"),
                    "resultado_lote.csv",
                    "text/csv"
                )

# PÁGINA 3: CORREÇÃO
elif page == "🛠️ Corrigir e Treinar":
    st.header("Correção de Inconsistências")
    st.markdown("Itens com confiança MÉDIA ou BAIXA aguardam sua validação. Ao salvar, eles enriquecem a base e treinam a IA.")

    if not st.session_state.inconsistencias_df.empty:
        # Adiciona coluna visual de status
        df_edit = st.session_state.inconsistencias_df.copy()

        # Mapa de cores visual usando Pandas Styler (apenas para visualização se fosse st.dataframe, mas para editor usaremos uma coluna de status)
        df_edit.insert(0, "STATUS", df_edit["NIVEL_CONFIANCA"].apply(lambda x: "🔴" if x == "BAIXO" else "🟡"))

        # Contadores de inconsistências
        total_linhas = len(df_edit)
        confianca_media = len(df_edit[df_edit["NIVEL_CONFIANCA"] == "MEDIO"])
        confianca_baixa = len(df_edit[df_edit["NIVEL_CONFIANCA"] == "BAIXO"])

        st.markdown("**Legenda:** 🟡 Média Confiança | 🔴 Baixa Confiança")
        st.info(f"📊 **Total:** {total_linhas} linhas | 🟡 **Média Confiança:** {confianca_media} | 🔴 **Baixa Confiança:** {confianca_baixa}")

        edited_df = st.data_editor(
            df_edit,
            use_container_width=True,
            num_rows="fixed",
            key="editor_fix",
            column_config={
                "STATUS": st.column_config.TextColumn("Status", disabled=True, width="small"),
                "JUSTIFICATIVA": st.column_config.TextColumn("Justificativa IA", disabled=True)
            },
            hide_index=True,
        )

        if st.button("💾 Validar e Mover para Base Oficial"):
            # Remove a coluna visual STATUS antes de salvar
            if "STATUS" in edited_df.columns:
                edited_df = edited_df.drop(columns=["STATUS"])

            # Atualiza confiança para ALTO pois foi validado por humano
            edited_df["NIVEL_CONFIANCA"] = "ALTO"
            edited_df["JUSTIFICATIVA"] = "Validado Manualmente"

            # Move para Main
            st.session_state.main_df = pd.concat([st.session_state.main_df, edited_df], ignore_index=True)
            # Limpa Inconsistências
            st.session_state.inconsistencias_df = pd.DataFrame(columns=COLS_FULL)

            salvar_dados()
            st.success("Base atualizada com sucesso! A IA aprenderá com estas correções.")
            st.rerun()

    else:
        st.success("🎉 Nenhuma inconsistência pendente! Tudo limpo.")
