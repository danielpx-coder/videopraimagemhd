# Vídeo para Imagem HD

Aplicativo desktop em Python para escolher um quadro de um vídeo e exportá-lo como **JPG** ou **WebP**. A interface permite pré-visualizar o instante escolhido, ajustar a qualidade e, opcionalmente, definir uma nova largura.

Por padrão, a imagem é exportada na **resolução original do vídeo**. O aumento de tamanho é opcional e não recupera detalhes que não existiam no vídeo.

## Requisitos

- Python 3.10 ou superior.
- Tkinter, usado pela interface gráfica. Ele já vem com muitas instalações do Python; no Linux pode ser necessário instalar o pacote do sistema (`python3-tk`).
- FFmpeg. O aplicativo procura primeiro uma instalação no `PATH`. Se não encontrar, usa o FFmpeg portátil instalado pelo pacote `imageio-ffmpeg` abaixo.

## Instalação e execução

Na pasta do projeto, execute:

```bash
python -m pip install -r requirements.txt
python app.py
```

No Windows, use `py -m pip install -r requirements.txt` e depois `py app.py`, se o comando `python` não estiver configurado.

No Ubuntu/Debian, caso o Python não tenha Tkinter:

```bash
sudo apt install python3-tk
```

## Como usar

1. Clique em **Selecionar vídeo**.
2. Informe o instante em segundos (`12.5`) ou no formato `HH:MM:SS.mmm` (`00:00:12.500`) e clique em **Pré-visualizar**.
3. Escolha JPEG ou WebP e ajuste a qualidade.
4. Deixe a largura vazia para manter a resolução original. Se informar uma largura, a altura é calculada mantendo a proporção.
5. Escolha o destino, se quiser alterar a sugestão automática, e clique em **Exportar quadro**.

O aplicativo trabalha localmente: o vídeo não é enviado a nenhum serviço. Os formatos de entrada aceitos dependem dos codecs disponíveis no FFmpeg.

## Testes

Os testes das funções de tempo e leitura de metadados usam apenas a biblioteca padrão:

```bash
python -m unittest discover -s tests -v
```
