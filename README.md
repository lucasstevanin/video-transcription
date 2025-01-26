
## Pré-requisitos

Para rodar o programa na sua máquina será necessario realizar alguns passos.

### Passo 0:
Crie e ative seu ambiente virtual (opcional, porém recomendado):

Criar um ambiente virtual:
```bash
  python -m venv env
```

Ativar o ambiente virtual:
```bash
  .\env\Scripts\activate - Windows
```

```bash
  source env/bin/activate - Linux/Mac
```

### Passo 1:
Instalar todas as dependências:
```bash
  pip install -r requirements.txt
```

### Passo 2:
Vá até o site da IA Groq (clicando no link ao lado) e gere sua API Key:
[Gerar API Key](https://console.groq.com/keys)

### Passo 3:
Crie o arquivo .env no diretório principal e adicione essa variável dentro dele (já passando a chave API):
```bash
  GROQ_API_KEY="<sua chave aqui>"
```

### Passo 4:
Crie uma pasta chamada "ffmpeg" no diretório principal e baixe o arquivo abaixo (extraia se necessario) e coloque o arquivo ffmpeg.exe dentro da pasta:
[Baixe aqui o arquivo ffmpeg.exe](https://www.ffmpeg.org/download.html)

#

Após todos os passos, acredito que ao executar o comando:
```bash
  python transcription.py
```
Seu programa irá rodar tranquilamente.




