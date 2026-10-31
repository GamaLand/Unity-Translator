# Guia de uso do UnityTranslator

## Área de trabalho

A barra lateral agrupa preparação, tradução/revisão e entrega. Arraste os divisores para ajustar a lista e os editores identificados de origem/tradução. Embaixo, alterne entre **Comparação de textos** e **Referências e verificações**; os avisos continuam visíveis. **Ferramentas do registro** contém histórico, novos candidatos, plurais e remoção do rascunho. **Ações em lote** contém operações de página/filtro/projeto com suas prévias e confirmações. Salvar e aprovar continuam sendo etapas separadas. Os formulários rolam em janelas menores (mínimo 900 × 740).

## Contexto de diálogo verificado

A preparação do piloto mostra a etapa de registros ou contexto antes das solicitações ao modelo. Projetos grandes podem precisar de uma verificação inicial do contexto. Cancelar interrompe a preparação com segurança; o fechamento aguarda a limpeza. Retome o piloto salvo com Continuar, sem recriar o projeto.

Nos ajustes avançados do modelo, **Usar falas vizinhas verificadas** é opcional e vem desativado. Segmentos Ren’Py compatíveis mostram a ordem de origem e fornecem até duas falas anteriores e posteriores. Escolhas, condições, saltos, chamadas, sintaxe desconhecida e limites de arquivos interrompem a janela; modelos de tradução só ligam falas do mesmo bloco. Tabelas de termos Unity e fontes sem ordem comprovada continuam isoladas. A revisão mostra referências que podem diminuir conforme o limite da solicitação. Mudar o modo exige um piloto revisado correspondente. Tarefas, traduções, rascunhos e aprovações existentes são preservados; maior naturalidade não é garantida.

## Instalação e idioma

No Windows x64, extraia **todo** o ZIP do aplicativo em uma pasta separada e abra
`UnityTranslator.exe`. O pacote pronto não exige Python. Para executar pelo código-fonte:

```powershell
uv sync --locked --extra ui
uv run --extra ui unitytranslator gui
```

O idioma padrão é inglês. O menu **Language**, ao lado de **Help**, oferece oito idiomas.
A escolha entra em vigor ao reabrir o aplicativo e não altera os idiomas de origem e
destino do projeto.

## Tradução

1. **Projeto:** selecione a pasta do jogo, uma pasta separada para o projeto e os códigos
   dos idiomas. Abra um projeto existente para continuar de onde parou.
2. **Textos:** verifique a compatibilidade, escolha uma fonte compatível e extraia os textos.
   O suporte à extração é verificado separadamente do suporte à instalação.
3. **Modelo:** inicie o LM Studio ou llama-server e carregue o modelo por conta própria.
   Informe o endereço local e o identificador do modelo e teste a conexão.
4. **Glossário:** adicione, se desejar, nomes preservados, termos preferidos e regras de estilo.
5. **Traduzir:** execute e revise primeiro um piloto representativo; depois inicie o lote.
   Escolha de 1 a 36 solicitações paralelas conforme o servidor. Minimizar a janela não
   interrompe a tradução. Pausar espera as solicitações em andamento; cancelar interrompe
   as tarefas do cliente.
6. **Revisão:** compare, edite, salve e aprove. Salvar um rascunho não é aprová-lo.
   A aprovação por página inclui apenas os registros aptos selecionados. Para aprovar
   todas as traduções, confirme primeiro a quantidade e os avisos; depois digite exatamente
   a frase exibida e pressione o botão final. É possível cancelar nas duas etapas.
   Rascunhos e erros de formato ficam de fora; mudanças na lista impedem aprovação parcial.

## Backup, instalação e compartilhamento

Exporte JSON ou faça um backup dos dados. Feche o jogo antes de preparar o plano de
instalação. Confira os novos arquivos e aprove a instalação separadamente. Abra o jogo
você mesmo para verificar caracteres, disposição e significado. A integração é experimental.

Remova os arquivos adicionados pelo projeto que os instalou. Não sobrescreva nem apague
`winhttp.dll`/`doorstop_config.ini` sem verificar a propriedade, e não redefina o inventário
original. Consulte o [guia de desenvolvimento](../docs/installation.md).

O destinatário de um ZIP compartilhável usa `Kur.cmd` para selecionar a pasta da versão
correspondente do jogo e `Kaldir.cmd` para remover apenas os arquivos próprios sem alterações.
Ele não precisa do modelo nem do UnityTranslator. Preserve as licenças e fontes incluídas.
Nem todo jogo Unity é compatível; verificações automáticas não garantem qualidade.
Alguns diagnósticos técnicos mantêm o idioma original.


Os idiomas de origem e destino do jogo são independentes do idioma da interface. Use ja para japonês, it para italiano ou pt-BR para português brasileiro; outros códigos também podem ser digitados. O idioma de origem deve existir no jogo. Colunas ausentes ou ambíguas são rejeitadas. O modelo deve oferecer suporte ao par. Os idiomas, aprovações e estilos dos projetos existentes são preservados; revise regras antigas específicas de um idioma. Confira fontes, layout RTL e plurais com um patch pequeno antes de compartilhar. O inglês também pode ser o idioma de destino.

## Krypta FM

Para a versão compatível de Krypta FM, escolha origem `en` e destino `tr`. O perfil 2 abrange 449 campos em 34 TextAssets e uma grade do diário; duas fontes e outros textos de interface ou imagens ficam de fora. Identidades e aprovações são preservadas.

Após revisar e aprovar, feche o jogo e confira em «Aplicar ao jogo» o plano dos dois arquivos novos: `winhttp.dll` e `doorstop_config.ini`. O runtime experimental fica no projeto separado; arquivos originais não são substituídos. Remova os acréscimos pelo mesmo projeto. A exportação de textos não é um instalador; ZIPs de instalação também aceitam a versão Krypta en→tr correspondente. O destinatário executa Install.cmd, revisa o plano e digita INSTALL; Uninstall.cmd remove apenas os acréscimos próprios sem alterações. A combinação portátil tem testes sintéticos; seu teste específico no jogo continua pendente. Foram observados início/menu, opções, entrada no jogo, pausa e legendas. Outras telas, troca de idioma e layout exigem revisão manual; um rótulo longo pode se sobrepor à explicação.

Nas configurações avançadas, é possível desativar opcionalmente o raciocínio nas solicitações do LM Studio. Isso pode reservar mais tokens de saída para a tradução. O suporte depende do modelo e servidor; uma opção incompatível pode interromper o trabalho. Os padrões e as configurações globais do servidor são preservados.

## Tradução Ren'Py

Em Textos, escolha o motor e examine o jogo. Um arquivo
`game/tl/<idioma>/*.rpy` lê toda a pasta do idioma. `.rpy` originais, `_ren.py`
verificados e RPA-3.0 com fontes são conferidos por contratos de comportamento
comparados com Ren'Py 8.1.2 e 8.3.6; a versão sozinha não garante suporte.
Conjuntos grandes e contêineres sem sobreposição são aceitos; caminhos ou nomes
base de fontes coincidentes são recusados. São cobertos diálogos de uma linha com
atributos de personagem e temporários `@`, `nointeract`, chaves explícitas `_()` e
textos de menus. O diálogo do menu deve preceder as opções e não pode se misturar
com títulos. Grupos voice/nvl, diálogos multilinha, texto dinâmico, scripts apenas
compilados e textos em imagens continuam excluídos. Confira as exclusões informadas.
A extração não executa código do jogo. Exportações grandes podem conter arquivos
numerados; mantenha toda a árvore exportada junta.

O ZIP de instalação continua limitado ao Ren'Py `8.1.2.23090503`; metadados privados de repositórios, ferramentas de IA ou credenciais bloqueiam o pacote da cópia.

Use o modelo, piloto, rascunhos e revisão humana existentes. Traduções antigas dos
modelos ficam somente para leitura no histórico. Após aprovar, informe um identificador
Ren'Py de destino, como `turkish`; o código do idioma não é convertido automaticamente.
Conclua ou descarte os rascunhos. A exportação nativa prepara arquivos no projeto;
traduções aprovadas conflitantes de uma chave global bloqueiam a exportação.

**Criar ZIP de instalação Ren'Py** empacota traduções aprovadas para a versão correspondente com um EXE na raiz. Extraia o ZIP fora do jogo e execute `Install.cmd`. Escolha uma vez a pasta original, revise o plano e digite `INSTALL`. O jogo não é copiado e arquivos existentes não são substituídos; conflitos interrompem a instalação. Só traduções, `Play-Translated.cmd` e pequenos recibos são adicionados. Não é preciso backup dos originais.

`Play-Translated.cmd` na pasta do jogo seleciona o idioma traduzido. Os dados salvos normais são usados. Jogar pode alterar saves, caches, logs e bytecode; remover não restaura progresso anterior.

Guarde o ZIP para `Remove.cmd`. Feche o jogo e escolha a mesma pasta. Só adições próprias sem alterações são removidas; arquivos modificados/vinculados/desconhecidos e recibos permanecem. Se forem gerados `.rpyc` da tradução, a remoção para antes de apagar qualquer arquivo: revise/remova manualmente apenas os indicados e tente novamente. Não apague outros `.rpyc` do jogo. ZIPs antigos mantêm a cópia completa.

CLI: `export-renpy-zip --game ... --project ... --language turkish`. Revise fontes, layout e outras cenas.

Se o relatório do piloto ainda mostrar um trabalho em andamento, atualize-o após a parada. Um piloto cancelado pode ser avaliado se toda a amostra necessária foi tentada e existem resultados concluídos. A avaliação libera o trabalho completo com as mesmas configurações e fontes; não aprova traduções.

Após avaliar o piloto, alterações salvas de glossário/estilo passam a valer para novas solicitações sem outro piloto. As solicitações em andamento mantêm as regras originais; as traduções existentes não mudam. Revise os registros afetados e solicite explicitamente nova tradução se necessário. Usar configurações do piloto avaliado restaura modelo e geração, mantendo o glossário/estilo atual.

Em Revisão, Retraduzir os registros desta página envia até 200 registros da página filtrada visível à fila compartilhada com o modelo atual e o glossário/estilo salvo. É necessário um piloto avaliado com as mesmas configurações. Rascunhos e registros em processamento são excluídos. O texto aprovado continua selecionado; os novos candidatos aparecem no histórico. A aba Traduzir mostra o progresso.

Em Revisão, **Ações em lote** permite aprovar traduções não vazias exatamente idênticas à origem ou retornar traduções vazias para Pendente. Abrange todas as páginas dos filtros atuais, com contagem e exemplos antes de confirmar. Limpe os filtros para abranger todo o projeto. Rascunhos, registros em fila/em processamento e aprovações existentes são excluídos. Uma cópia pode ser uma frase não traduzida: aprovar é sua decisão explícita. Retornar vazios preserva o histórico e não envia solicitações ao modelo; depois inicie um trabalho em Traduzir com o piloto revisado habitual.

Ao retornar traduções vazias para Pendente, entradas de trabalhos pausados são permitidas. A prévia mostra a contagem; ao retomar, as entradas antigas serão ignoradas porque a versão do registro muda. O histórico é preservado. Outras entradas em fila/em processamento ainda bloqueiam a ação; correspondências excluídas são diferenciadas da ausência de correspondências.
