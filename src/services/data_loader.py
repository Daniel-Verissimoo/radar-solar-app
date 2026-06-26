import pandas as pd
import logging

def carregar_dados_aneel(caminho_arquivo: str) -> pd.DataFrame:
    """
    Lê arquivos .parquet pesados. 
    Esta função rodará em um processo isolado (CPU Bound).
    """
    try:
        # PyArrow como engine é o mais performático para Parquet
        df = pd.read_parquet(caminho_arquivo, engine='pyarrow')
        
        # Você pode fazer filtragens ou agregações pesadas aqui dentro também
        # para retornar ao processo principal apenas o payload necessário para o mapa.
        return df
    except Exception as e:
        logging.error(f"Erro ao ler Parquet {caminho_arquivo}: {e}")
        raise