# Atualização do scraper

Substitua o arquivo da raiz do repositório:

- atualizar_jogos_chile.py

Opcionalmente, substitua também:

- .github/workflows/atualizar-jogos.yml

Principais mudanças:
- Adicionados os slugs atuais:
  - segunda-la-liga-2d
  - campeonato-femenino
  - copa-de-la-liga
  - ascenso-femenino
- Descoberta automática de links /ligas/ no Campeonato Chileno.
- Janela padrão sugerida no workflow: 120 dias.
- Opção --incluir-passados para testar todos os jogos listados nas páginas.
