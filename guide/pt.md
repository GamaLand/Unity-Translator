# Guia de uso do UnityTranslator

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
   Escolha de 1 a 16 solicitações paralelas conforme o servidor. Minimizar a janela não
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

Na versão verificada, selecione `en` como idioma de origem e extraia os textos normalmente. O perfil lê três contêineres juntos: 34 TextAssets com 442 campos. Duas fontes são explicitamente excluídas; outros textos ficam fora do perfil. Após traduzir, revisar e aprovar, exporte os textos TextAsset aprovados. Arquivos de texto preparados e um manifesto são criados no projeto; campos não aprovados mantêm o texto original. Nenhum arquivo Unity é alterado e nenhuma tradução é instalada no jogo. A instalação não é compatível com este perfil. Feche as versões anteriores antes de abrir um projeto de esquema 5.

Nas configurações avançadas, é possível desativar opcionalmente o raciocínio nas solicitações do LM Studio. Isso pode reservar mais tokens de saída para a tradução. O suporte depende do modelo e servidor; uma opção incompatível pode interromper o trabalho. Os padrões e as configurações globais do servidor são preservados.

A revisão 2 também lê sete objetivos em inglês do diário nos metadados estáticos. São 449 campos em 34 TextAssets e uma matriz do diário; as identidades e aprovações anteriores são preservadas. O novo hook do diário tem apenas verificações de compilação e sintéticas; o piloto anterior de três rótulos foi observado no jogo. A instalação normal de Krypta pela interface ainda não é suportada.
