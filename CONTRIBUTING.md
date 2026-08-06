# Como contribuir

Obrigado por olhar o projeto. Ele é aberto porque **capacidade de Fabric é um problema
que a comunidade conhece melhor do que qualquer empresa sozinha** — cada capacidade tem
um padrão de uso diferente, e o que aprendemos num cliente não cobre o seu.

## O que ajuda mais (por ordem)

1. **Rodar num Fabric real e contar o que aconteceu.** É a contribuição mais valiosa hoje.
   O modelo semântico do Capacity Metrics App é *não suportado para consumo externo* e
   muda entre versões — só rodando em capacidades diferentes descobrimos onde a leitura
   quebra. Abra uma issue com: versão do app, SKU, o que saiu e o que você esperava.
   **Não cole dados da sua capacidade**: nomes de item e IDs são informação da sua
   empresa. Descreva o comportamento, não o conteúdo.

2. **Nomes de tabela/medida de outras versões do app.** Se `validar_schema` acusou
   incompatibilidade, mande a saída de `EVALUATE INFO.TABLES()` **sem os dados** — só a
   lista de nomes. Isso melhora a descoberta para todo mundo.

3. **Regras de interpretação.** A parte que dá valor não é ler o número, é concluir algo
   dele. Se você discorda de um limiar (o gate de cronicidade de 2 dias, a escada de
   remédios antes de subir SKU), abra uma issue **com o raciocínio** — limiar sem
   justificativa é chute, e chute é o que este projeto evita.

4. **Correções e testes.** Toda regra de interpretação tem prova em `tests/`. PR que muda
   comportamento precisa de teste que falhe antes e passe depois.

## Princípios do projeto (o que não vai ser aceito)

- **Nada de número inventado.** Se a ferramenta não consegue medir, ela diz que não
  consegue. Preferimos "inconclusivo" a um valor bonito e errado — o público é técnico e
  detecta na hora.
- **Não reproduzir o app nativo.** Gráfico de CU o Capacity Metrics já faz, de graça e
  melhor. O que falta é a **conclusão**.
- **Limites declarados.** Toda estimativa diz o que ela não cobre. Se o seu PR adiciona
  uma leitura nova, adicione junto a limitação dela.
- **Read-only.** A ferramenta nunca escreve na capacidade nem muda configuração.

## Rodando os testes

```bash
python tests/test_interpretacao.py
```

A camada de interpretação é Python puro e **não precisa de Fabric** para ser testada —
foi desenhada assim justamente para receber contribuição de quem não tem uma capacidade
à mão.

## Código de conduta

Seja direto e respeitoso. Crítica técnica dura é bem-vinda; ataque pessoal não.

## Licença

Ao contribuir, você concorda que sua contribuição é licenciada sob a
[Apache License 2.0](LICENSE), como o resto do projeto.
