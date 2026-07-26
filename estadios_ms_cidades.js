/*
  Fallback por mandante para o Sul-Mato-Grossense Série B (fonte="FFMS" no
  scrap_sofascore_estaduais.py).

  O SofaScore não traz nome de estádio nem cidade para esses jogos (só os
  nomes dos times), então usa-se a cidade-sede conhecida de cada clube como
  aproximação -- mesma convenção do ESTADIO_MANDANTE_PADRAO_FES em
  estadios_es_cidades.js. Coordenadas: centro do município (fonte IBGE, via
  kelvins/municipios-brasileiros).
*/
window.ESTADIO_MANDANTE_PADRAO_FFMS = {
  "ec campo grande": { nome: "Campo Grande (aproximado)", cidade: "Campo Grande", regiao: "Mato Grosso do Sul", lat: -20.4486, lng: -54.6295 },
  "comercial ms": { nome: "Estádio Moreninhas (aproximado)", cidade: "Campo Grande", regiao: "Mato Grosso do Sul", lat: -20.4486, lng: -54.6295 },
  "uniao abc": { nome: "Estádio Moreninhas (aproximado)", cidade: "Campo Grande", regiao: "Mato Grosso do Sul", lat: -20.4486, lng: -54.6295 },
  "ec taveiropolis": { nome: "Estádio Elias Gadia (aproximado)", cidade: "Campo Grande", regiao: "Mato Grosso do Sul", lat: -20.4486, lng: -54.6295 },
  "aquidauanense": { nome: "Aquidauana (aproximado)", cidade: "Aquidauana", regiao: "Mato Grosso do Sul", lat: -20.4666, lng: -55.7868 },
  "sao gabriel ec": { nome: "São Gabriel do Oeste (aproximado)", cidade: "São Gabriel do Oeste", regiao: "Mato Grosso do Sul", lat: -19.3889, lng: -54.5507 },
  "misto ec": { nome: "Três Lagoas (aproximado)", cidade: "Três Lagoas", regiao: "Mato Grosso do Sul", lat: -20.7849, lng: -51.7007 },
  "sete de setembro ms": { nome: "Estádio Douradão (aproximado)", cidade: "Dourados", regiao: "Mato Grosso do Sul", lat: -22.2231, lng: -54.8120 },
};
