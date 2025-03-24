import streamlit as st
import pandas as pd
import time
import traceback
from io import BytesIO
import os

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    ElementClickInterceptedException,
    NoSuchElementException
)
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities

def encontrar_campo_busca(driver, tempo_espera=10):
    try:
        return WebDriverWait(driver, tempo_espera).until(
            EC.presence_of_element_located((By.XPATH, '//*[@id="P_ENTREE_HOME"]'))
        )
    except TimeoutException:
        return WebDriverWait(driver, tempo_espera).until(
            EC.presence_of_element_located((By.XPATH, '//*[@id="P_ENTREE_ENTETE"]'))
        )

def iniciar_driver():
    """
    Tenta iniciar o driver local usando caminhos alternativos para o binário.
    Se falhar, tenta utilizar um WebDriver remoto, se configurado via variável de ambiente.
    """
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")  
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    
    # Tente diferentes caminhos para o binário do Chromium
    for binary_path in ["/usr/bin/chromium-browser", "/usr/bin/chromium"]:
        if os.path.exists(binary_path):
            options.binary_location = binary_path
            break
    else:
        st.error("Nenhum binário do Chromium encontrado no caminho padrão.")
        return None

    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        return driver
    except Exception as e:
        st.error("Erro ao iniciar o Chrome WebDriver local: " + str(e))
        # Tente usar WebDriver remoto, se configurado
        remote_url = os.environ.get("REMOTE_WEBDRIVER_URL")
        if remote_url:
            st.info("Tentando usar WebDriver remoto em: " + remote_url)
            try:
                caps = DesiredCapabilities.CHROME.copy()
                driver = webdriver.Remote(
                    command_executor=remote_url,
                    desired_capabilities=caps,
                    options=options
                )
                return driver
            except Exception as ex:
                st.error("Erro ao iniciar o WebDriver remoto: " + str(ex))
        return None

def processar_imos(df_imos):
    driver = iniciar_driver()
    if driver is None:
        st.error("Não foi possível iniciar o WebDriver.")
        return None

    todos_os_dados = []
    try:
        # --- LOGIN ---
        driver.get("http://www.equasis.org/")
        time.sleep(3)
        email_field = driver.find_element(By.XPATH, '//*[@id="home-login"]')
        password_field = driver.find_element(By.XPATH, '//*[@id="home-password"]')
        email_field.send_keys("mkt@navsupply.com.br")
        password_field.send_keys("mKT@2025")
        password_field.send_keys(Keys.RETURN)
        time.sleep(5)

        # --- LOOP para cada IMO ---
        for imo in df_imos["IMO"]:
            imo_str = str(imo).strip()
            st.write(f"Processando IMO: {imo_str}")
            try:
                campo_busca = encontrar_campo_busca(driver, tempo_espera=10)
                campo_busca.clear()
                campo_busca.send_keys(imo_str)
                campo_busca.send_keys(Keys.RETURN)
                time.sleep(5)

                try:
                    nome_navio_element = driver.find_element(By.XPATH, '//*[@id="ShipResultId"]/table/tbody/tr[1]/td[1]')
                    nome_navio = nome_navio_element.text.strip()
                    st.write(f"Nome do Navio capturado: {nome_navio}")
                except NoSuchElementException:
                    st.write("Nome do navio não encontrado. Tentando fechar alerta...")
                    try:
                        close_button = WebDriverWait(driver, 10).until(
                            EC.element_to_be_clickable((By.XPATH, '//*[@id="warning"]/div/div/div[3]/button'))
                        )
                        close_button.click()
                        st.write("Alerta fechado. Pulando este IMO...")
                    except Exception as e:
                        st.write("Erro ao fechar alerta:", e)
                    continue

                xpath_imo_link = f"//a[contains(text(),'{imo_str}')]"
                imo_link = WebDriverWait(driver, 15).until(
                    EC.element_to_be_clickable((By.XPATH, xpath_imo_link))
                )
                driver.execute_script("arguments[0].scrollIntoView(true);", imo_link)
                time.sleep(1)
                imo_link.click()
                st.write(f"Link contendo '{imo_str}' clicado com sucesso!")

                try:
                    segundo_elemento = WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH, '//*[@id="body"]/div[6]/div/div/div/div/div/div/div[2]/a/div/div/div[1]/div/div/div/div/div/div/h3'))
                    )
                    driver.execute_script("arguments[0].scrollIntoView(true);", segundo_elemento)
                    time.sleep(1)
                    try:
                        segundo_elemento.click()
                    except ElementClickInterceptedException:
                        driver.execute_script("arguments[0].click();", segundo_elemento)
                    st.write("Segundo elemento clicado com sucesso!")
                except TimeoutException:
                    st.write("Segundo elemento não encontrado/clicável. Pulando este IMO.")
                    continue

                time.sleep(5)  # Aguarda a página detalhada

                try:
                    tabela_xpath = '//*[@id="collapse3"]/div/div/div/div/div/div[1]/div[1]/div[3]/div/div/form/table/tbody'
                    tabela_body = WebDriverWait(driver, 20).until(
                        EC.presence_of_element_located((By.XPATH, tabela_xpath))
                    )
                    linhas = tabela_body.find_elements(By.TAG_NAME, "tr")
                    for linha in linhas:
                        try:
                            celulas = linha.find_elements(By.TAG_NAME, "td")
                            if len(celulas) >= 3:
                                texto_manager_owner = celulas[1].text.strip()
                                texto_compania = celulas[2].text.strip()
                                lista_manager = []
                                lista_owner = []
                                partes = texto_manager_owner.split("\n")
                                for parte in partes:
                                    subpartes = parte.split("/") if "/" in parte else [parte]
                                    for sub in subpartes:
                                        sub = sub.strip()
                                        if "manager" in sub.lower():
                                            lista_manager.append(sub)
                                        if "owner" in sub.lower():
                                            lista_owner.append(sub)
                                manager = " / ".join(lista_manager)
                                owner = " / ".join(lista_owner)
                                if not manager and not owner and partes:
                                    manager = partes[0].strip()
                                todos_os_dados.append({
                                    "IMO": imo_str,
                                    "Nome do Navio": nome_navio,
                                    "Compania": texto_compania,
                                    "Manager": manager,
                                    "Owner": owner
                                })
                        except Exception as e:
                            st.write("Erro ao processar uma linha da tabela:", e)
                except TimeoutException:
                    st.write(f"Não foi possível localizar a tabela para o IMO {imo_str}.")
            except Exception as e:
                st.write(f"[ERRO] Problema ao processar o IMO {imo_str}: {e}")
                traceback.print_exc()
                continue

        df_resultado = pd.DataFrame(todos_os_dados)
        return df_resultado
    except Exception as e:
        st.write("Erro crítico:", e)
    finally:
        driver.quit()
        st.write("Navegador fechado.")

# --- Interface do Streamlit ---
st.title("Scraping de Dados - Equasis")

uploaded_file = st.file_uploader("Selecione o arquivo Excel com a lista de IMOs", type=["xlsx", "xls"])
if uploaded_file is not None:
    try:
        df_imos = pd.read_excel(BytesIO(uploaded_file.read()))
        st.write("Arquivo carregado com sucesso!")
        st.write(df_imos.head())
    except Exception as e:
        st.error("Erro ao ler o arquivo: " + str(e))

if st.button("Iniciar Extração"):
    if uploaded_file is None:
        st.error("Por favor, faça o upload do arquivo Excel primeiro.")
    else:
        with st.spinner("Processando..."):
            df_resultado = processar_imos(df_imos)
            if df_resultado is not None and not df_resultado.empty:
                st.success("Processo concluído!")
                st.dataframe(df_resultado)
                @st.cache_data
                def convert_df(df):
                    return df.to_excel(index=False).encode('utf-8')
                resultado_excel = convert_df(df_resultado)
                st.download_button(
                    label="Baixar resultado em Excel",
                    data=resultado_excel,
                    file_name="resultado.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.warning("Nenhum dado foi extraído.")
