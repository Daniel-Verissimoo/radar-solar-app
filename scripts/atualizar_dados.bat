@echo off
title Radar Solar - Atualizacao de Dados
echo ============================================
echo   Radar Solar - Atualizacao de Dados
echo ============================================
echo.
echo Verificando ambiente Python...

if exist ..\.venv\Scripts\activate.bat (
    call ..\.venv\Scripts\activate.bat
    echo Ambiente virtual ativado.
) else (
    echo AVISO: Ambiente virtual nao encontrado.
    echo Usando Python padrao do sistema.
)

echo.
echo [1/5] Baixando e processando dados ANEEL...
python scripts\update_aneel_data.py --force
if %errorlevel% neq 0 (
    echo ERRO: Falha ao atualizar dados ANEEL.
    pause
    exit /b 1
)

echo.
echo [2/5] Extraindo CSVs com CNPJs...
python scripts\extract_aneel_rmr_csv.py --force
if %errorlevel% neq 0 (
    echo ERRO: Falha ao extrair CSVs.
    pause
    exit /b 1
)

echo.
echo [3/5] Enriquecendo CNPJs (telefone/email)...
echo ATENCAO: Esta etapa consulta a API CNPJa para cada empresa nova.
echo Cada consulta leva ~13s. Pode demorar na primeira vez.
echo Para processar apenas alguns CNPJs de teste, use Ctrl+C e rode:
echo   python scripts\update_cnpj_enderecos.py --limit=10
echo.
python scripts\update_cnpj_enderecos.py
if %errorlevel% neq 0 (
    echo ERRO: Falha ao enriquecer CNPJs.
    pause
    exit /b 1
)

echo.
echo [4/5] Gerando GeoJSON do mapa...
python scripts\gerar_mapa_geojson.py
if %errorlevel% neq 0 (
    echo ERRO: Falha ao gerar GeoJSON.
    pause
    exit /b 1
)

echo.
echo [5/5] Geocodificando CEPs...
python scripts\geocodificar_ceps.py
if %errorlevel% neq 0 (
    echo AVISO: Falha ao geocodificar CEPs (nao critico).
)

echo.
echo ============================================
echo   Dados atualizados com sucesso!
echo ============================================
echo.
echo Proximos passos:
echo 1. Abra o GitHub Desktop ou terminal
echo 2. Commit as alteracoes em data/data/
echo 3. De push para o GitHub
echo 4. O Render fara deploy automatico
echo.
pause
