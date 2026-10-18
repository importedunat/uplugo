# Contribuir

Execute os testes indicados no README antes de propor alterações. Use dados
fictícios em capturas e fixtures. Não envie MACs, caminhos pessoais, configurações,
logs completos de sessão ou dumps de firmware.

Mudanças de interface devem preservar os modos em execução e confirmar ações
com o estado real. Mudanças no helper precisam validar argumentos, limites dos
relatórios e liberação do hardware ao encerrar. Não adicione permissões genéricas
ou acesso administrativo a scripts editáveis durante a execução do helper.

Inclua a distribuição, ambiente gráfico e versão do kernel nos resultados de
teste. Hardware não disponível deve constar como não testado. O projeto recebe
contribuições de código sob GPL-3.0-only; novos recursos visuais precisam ter
licença e atribuição registradas em THIRD_PARTY.md.
