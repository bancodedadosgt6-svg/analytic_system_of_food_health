# Painel de Análise de Dados em Saúde Alimentar

## Estrutura

- `app.py`: orquestra o painel Streamlit.
- `settings.py`: sincroniza dados do Google Drive, salva em `data/`, lê datasets e detecta bases geoespaciais.
- `sidebar.py`: centraliza sidebar, filtros globais e catálogo local.
- `table.py`: renderiza tabela dinâmica e agregações rápidas.
- `graphic.py`: renderiza gráficos de barras, linha, tendência e comparativos.
- `map.py`: renderiza mapa para datasets com latitude e longitude.
- `data/`: cache local dos arquivos baixados do Google Drive.
- `.env.example`: variáveis de ambiente necessárias.

## Como rodar

1. Crie o ambiente virtual.
2. Instale os pacotes de `requirements.txt`.
3. Copie `.env.example` para `.env`.
4. Configure a conta de serviço do Google e a pasta do Drive.
5. Execute:

```bash
streamlit run app.py
```

## Regras do MVP

- O sistema sincroniza os arquivos suportados do Google Drive para a pasta `data/`.
- Em cada execução, calcula hash do conteúdo e substitui o arquivo local se houver atualização.
- Datasets com colunas reconhecidas de latitude/longitude são tratados como geoespaciais.
- O painel tem 3 abas: Tabela, Gráficos e Mapas.
