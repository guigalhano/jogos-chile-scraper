/*
  Estadios/sedes dos clubes filiados a FERJ (Rio de Janeiro), obtidos via
  scrap_fferj_estadios.py a partir de servicos.fferj.com.br/ClubesLigas.

  window.ESTADIOS_FERJ_RJ: lista de estadios/sedes com coordenadas.
  window.ESTADIO_MANDANTE_PADRAO_FFERJ: nome do clube (normalizado) -> objeto
  de estadio/sede correspondente, usado como fallback em enrichGames() quando
  o card de um jogo da FFERJ nao informa o nome do estadio.
*/

window.ESTADIOS_FERJ_RJ = [
];

window.ESTADIO_MANDANTE_PADRAO_FFERJ = {
};