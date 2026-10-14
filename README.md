# Publicação automática – Apadrinhe a Educação (@osoconsolador)

Todo dia às 18h de Brasília, o GitHub publica no Instagram o post do dia, com a legenda certa.

- `posts/`: as imagens (JPEG) e as legendas (`posts/legendas.md`)
- `calendario.json`: o calendário, montado automaticamente a partir das imagens e das legendas
- `publicados.json`: o que já foi publicado, com o ID do post, o link e o horário
- `log.txt`: o histórico de cada tentativa, incluindo as falhas
- `pausar.txt`: datas que não devem sair

Nenhum token fica neste repositório. Ele está em **Settings → Secrets and variables → Actions** (`IG_TOKEN` e `IG_USER_ID`).

## Ver o que já foi publicado

- Abra o `publicados.json` no GitHub.
- Ou abra a aba **Actions**, clique na execução do dia e depois em "Publicar".

Se algo falhar, o GitHub manda um e-mail, e a execução fica com um ❌ vermelho na aba Actions. Os avisos (por exemplo, "data passou" ou "token expirando") aparecem em amarelo no resumo da execução.

## Pausar

- **Tudo:** em Settings → Secrets and variables → Actions → aba **Variables**, mude `AGENDAMENTO_ATIVO` para `nao`. Para voltar, mude para `sim`.
- **Só um dia:** escreva a data (ex.: `2026-10-23`) numa linha do `pausar.txt` e salve.

## Adiantar ou atrasar um post

- **Adiantar (publicar agora):** em Actions → "Publicar no Instagram" → **Run workflow**, preencha a data (ex.: `2026-10-16`) e confirme.
- **Mudar de dia:** renomeie as imagens trocando a data do começo do nome (ex.: `2026-10-23_...` → `2026-10-24_...`). Depois troque a data no título da legenda em `posts/legendas.md` (`## 23/10 – ...` → `## 24/10 – ...`).

Datas que já passaram nunca são publicadas sozinhas. O sistema só avisa.

## Trocar uma imagem ou uma legenda

- **Legenda:** edite o texto embaixo do título `## DD/MM – ...` em `posts/legendas.md`. O texto vai exatamente como está escrito.
- **Imagem:** no Mac, coloque o PNG novo numa pasta (com o mesmo nome do arquivo antigo) e rode `python3 publicar.py --converter CAMINHO_DA_PASTA`. Ele gera o JPEG em `posts/` sem cortar nem redimensionar.
- **Carrossel:** os arquivos com a mesma data e `_slide1`, `_slide2`... formam um carrossel, nessa ordem.

Depois de qualquer mudança, rode `python3 publicar.py --dry-run` para conferir e envie (push) pelo GitHub Desktop.

## Token

O `IG_TOKEN` é um token de **Página do Facebook** gerado a partir de um token de usuário de longa duração. Esse tipo de token **não expira** sozinho. Ele só deixa de valer se a senha do Facebook for trocada, se o app perder a permissão ou se a pessoa sair da Página.

Todo dia o sistema confere o token antes de publicar. Se o token parar de funcionar, a execução falha e chega um e-mail. Se algum dia o token tiver data de validade, o sistema avisa 15 dias antes. Para trocar o token: gere um novo e atualize o Secret `IG_TOKEN`. Não precisa mexer no código.
