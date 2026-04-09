import streamlit as st
import pandas as pd

st.sidebar.title('MENU')
pagina = st.sidebar.radio(
    label='Ir para:',
    options=['Página Inicial','Análise']
)

ubs = st.selectbox("Selecione a UBS:", 
    options=[" ","Gama", "Santa Maria", "Jardins Mangueiral"])

if ubs == "Gama":
    st.success("Você selecionou o Gama!")
elif ubs == "Santa Maria":
    st.success("Você selecionou o Santa Maria!")
elif ubs == "Jardins Mangueiral":  
    st.success("Você selecionou o Jardins Mangueiral!")

profissional = st.selectbox("Selecione a categoria do profissional:", 
    options=[" ","ACS", "Auxiliar Técnico", "Dentista", "Enfermeiro", "Médico", "Outro profissional", "Técnico Saúde Bucal"])

if profissional == "ACS":
    st.success("Você selecionou a ACS!")
elif profissional == "Auxiliar Técnico":
    st.success("Você selecionou o Auxiliar Técnico!")
elif profissional == "Dentista":
    st.success("Você selecionou o Dentista!")
elif profissional == "Enfermeiro":
    st.success("Você selecionou o Enfermeiro!")
elif profissional == "Médico":
    st.success("Você selecionou o Médico!")
elif profissional == "Outro profissional":
    st.success("Você selecionou o Outro profissional!") 
elif profissional == "Técnico Saúde Bucal":
    st.success("Você selecionou o Técnico Saúde Bucal!")
    
upload = st.file_uploader(
    label='Faça o upload do arquivo CSV', 
    type='csv')

# Verificar se o arquivo foi enviado #
if upload is not None:
    upload.seek(0)  # Voltar para o início do arquivo
    linhas = upload.readlines()
    linha_12 = linhas[11].decode('latin-1') # A linha 12 é a de índice 11

    is_acs = 'ACS' in linha_12

    upload.seek(0)  # Voltar para o início do arquivo novamente
    df = pd.read_csv(upload, encoding='latin-1', sep=';', skiprows=18)
    df = df.loc[:, ~df.columns.str.contains('^Unnamed')]

    df_linha44 = df.iloc[26:]  # (44 - 18 = 26, ajuste correto)

    if is_acs:
        dfcadastro = df[df['Tipo'] == 'Cadastro individual']
        df = pd.concat([dfcadastro, df_linha44])
    else:
        df = df_linha44
        df['UBS'] = ubs
        df['Categoria'] = profissional
    
    df['UBS'] = ubs
    df['Categoria'] = profissional
    
    colunas = ['UBS', 'Categoria'] + [c for c in df.columns if c not in ['UBS', 'Categoria']]
    df = df[colunas]

    st.success('Dados carregados com sucesso!')
    st.dataframe(df)





# python -m streamlit run obter_data.py #