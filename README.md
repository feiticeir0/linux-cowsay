# cowsay-image-to-bluesky

Bot Linux para publicar no Bluesky uma imagem PNG gerada a partir de:

```bash
fortune | cowsay | lolcat
```

O script:
- gera ASCII colorido com ANSI (`lolcat`);
- renderiza esse ANSI para PNG com fonte monoespaçada;
- faz upload da imagem no Bluesky;
- publica o post com `embed.images`;
- usa o texto sem ANSI como `alt` da imagem.

## Requisitos

- Linux com `systemd --user`
- Python 3.10+
- `fortune`, `cowsay`, `lolcat`
- dependências Python de `requirements.txt`

Exemplo Debian/Ubuntu:

```bash
sudo apt update
sudo apt install -y fortune cowsay lolcat python3-pip
python3 -m pip install -r requirements.txt
```

## Quickstart

```bash
cp .env.example .env
$EDITOR .env
chmod +x post_cowsay.py install_systemd.sh
./post_cowsay.py
```

Se estiver tudo correto, vai aparecer:

```text
Posted successfully: at://...
```

E o arquivo `last_cowsay.png` ficará salvo localmente para debug.

## Configuração (`.env`)

Obrigatórios:
- `BSKY_IDENTIFIER`: handle ou email da conta Bluesky
- `BSKY_APP_PASSWORD`: app password (não use a password normal)

Opcionais:
- `BSKY_PDS_HOST`: por padrão `https://bsky.social`
- `BSKY_POST_TEXT`: texto da legenda do post
- `COWSAY_GENERATOR`: pipeline de geração (default força `lolcat -f`)
- `BSKY_FONT_PATH`: caminho de fonte monoespaçada TTF
- `BSKY_FONT_SIZE`: tamanho da fonte no PNG

## Agendamento com systemd timer

Para postar a cada 60 minutos:

```bash
./install_systemd.sh 60
```

Comandos úteis:

```bash
systemctl --user status cowsay-bluesky.timer
systemctl --user list-timers | rg cowsay-bluesky
systemctl --user start cowsay-bluesky.service
journalctl --user -u cowsay-bluesky.service -n 50 --no-pager
```

## Troubleshooting

- Sem cores no PNG:
  - confirme que `lolcat` está instalado;
  - mantenha `COWSAY_GENERATOR` com `lolcat` (o script injeta `-f` automaticamente).
- ASCII distorcido:
  - ajuste `BSKY_FONT_SIZE`;
  - defina `BSKY_FONT_PATH` para uma fonte monoespaçada TTF existente.
- Erro de autenticação Bluesky:
  - gere um novo app password e atualize `BSKY_APP_PASSWORD`.

## Segurança

- `.env` está no `.gitignore` para evitar leak de credenciais.
- Nunca commite app password no repositório.
