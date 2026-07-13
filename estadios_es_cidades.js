/*
  Coordenadas de cidades do Espírito Santo (fallback por cidade).

  Os jogos da FES (Federação de Futebol do Estado do Espírito Santo,
  futebolcapixaba.com) acontecem em estádios/campos pequenos de dezenas de
  cidades do interior do ES que não têm um estádio "profissional" na base
  estadios_brasil.js (essa cobre só clubes de Série A/B/C/D + Copa do
  Brasil). Quando não há correspondência de estádio, usamos o centro da
  cidade como aproximação razoável — melhor que não aparecer no mapa.

  Cobre os 78 municípios oficiais do Espírito Santo (lista/coordenadas do
  IBGE), não só os que já apareceram nos jogos coletados até agora, para não
  precisar voltar aqui toda vez que a FES adicionar um clube de uma cidade
  nova.

  Chaves: nome da cidade normalizado (minúsculo, sem acento), igual à
  função normalize() do script.js.
*/

window.CIDADES_ES = {
  "afonso claudio": { lat: -20.077841, lng: -41.126060 },
  "agua doce do norte": { lat: -18.548220, lng: -40.985411 },
  "aguia branca": { lat: -18.984588, lng: -40.743690 },
  "alegre": { lat: -20.758041, lng: -41.538237 },
  "alfredo chaves": { lat: -20.639627, lng: -40.754289 },
  "alto rio novo": { lat: -19.061797, lng: -41.020909 },
  "anchieta": { lat: -20.795499, lng: -40.642545 },
  "apiaca": { lat: -21.152272, lng: -41.569297 },
  "aracruz": { lat: -19.820045, lng: -40.276441 },
  "atilio vivacqua": { lat: -20.912974, lng: -41.198576 },
  "baixo guandu": { lat: -19.521283, lng: -41.010913 },
  "barra de sao francisco": { lat: -18.754840, lng: -40.896456 },
  "boa esperanca": { lat: -18.539495, lng: -40.302521 },
  "bom jesus do norte": { lat: -21.117290, lng: -41.673129 },
  "brejetuba": { lat: -20.139489, lng: -41.295410 },
  "cachoeiro de itapemirim": { lat: -20.846212, lng: -41.119829 },
  "cariacica": { lat: -20.263202, lng: -40.416549 },
  "castelo": { lat: -20.603255, lng: -41.203133 },
  "colatina": { lat: -19.549316, lng: -40.626898 },
  "conceicao da barra": { lat: -18.588306, lng: -39.736199 },
  "conceicao do castelo": { lat: -20.363897, lng: -41.241730 },
  "divino de sao lourenco": { lat: -20.622932, lng: -41.693725 },
  "domingos martins": { lat: -20.360306, lng: -40.659425 },
  "dores do rio preto": { lat: -20.693119, lng: -41.840538 },
  "ecoporanga": { lat: -18.370231, lng: -40.835976 },
  "fundao": { lat: -19.937035, lng: -40.407759 },
  "governador lindenberg": { lat: -19.251820, lng: -40.460954 },
  "guacui": { lat: -20.766792, lng: -41.673400 },
  "guarapari": { lat: -20.677248, lng: -40.509253 },
  "ibatiba": { lat: -20.234676, lng: -41.508674 },
  "ibiracu": { lat: -19.836601, lng: -40.373182 },
  "ibitirama": { lat: -20.546619, lng: -41.666718 },
  "iconha": { lat: -20.791287, lng: -40.813200 },
  "irupi": { lat: -20.350122, lng: -41.644359 },
  "itaguacu": { lat: -19.801786, lng: -40.860135 },
  "itapemirim": { lat: -21.009512, lng: -40.830669 },
  "itarana": { lat: -19.875009, lng: -40.875264 },
  "iuna": { lat: -20.353135, lng: -41.533440 },
  "jaguare": { lat: -18.907006, lng: -40.075900 },
  "jeronimo monteiro": { lat: -20.799359, lng: -41.394848 },
  "joao neiva": { lat: -19.757707, lng: -40.385951 },
  "laranja da terra": { lat: -19.899399, lng: -41.062141 },
  "linhares": { lat: -19.394642, lng: -40.064277 },
  "mantenopolis": { lat: -18.859428, lng: -41.124005 },
  "marataizes": { lat: -21.039813, lng: -40.838436 },
  "marechal floriano": { lat: -20.415889, lng: -40.669998 },
  "marilandia": { lat: -19.411358, lng: -40.545648 },
  "mimoso do sul": { lat: -21.062777, lng: -41.361529 },
  "montanha": { lat: -18.130287, lng: -40.366781 },
  "mucurici": { lat: -18.096516, lng: -40.519975 },
  "muniz freire": { lat: -20.465187, lng: -41.415630 },
  "muqui": { lat: -20.950859, lng: -41.345994 },
  "nova venecia": { lat: -18.715017, lng: -40.405273 },
  "pancas": { lat: -19.222940, lng: -40.853444 },
  "pedro canario": { lat: -18.300418, lng: -39.957365 },
  "pinheiros": { lat: -18.414068, lng: -40.217142 },
  "piuma": { lat: -20.833433, lng: -40.726813 },
  "ponto belo": { lat: -18.125318, lng: -40.545801 },
  "presidente kennedy": { lat: -21.096358, lng: -41.046800 },
  "rio bananal": { lat: -19.271889, lng: -40.336605 },
  "rio novo do sul": { lat: -20.855619, lng: -40.938761 },
  "santa leopoldina": { lat: -20.099914, lng: -40.526998 },
  "santa maria de jetiba": { lat: -20.025296, lng: -40.743931 },
  "santa teresa": { lat: -19.936339, lng: -40.597945 },
  "serra": { lat: -20.121032, lng: -40.307408 },
  "sooretama": { lat: -19.189695, lng: -40.097351 },
  "sao domingos do norte": { lat: -19.145213, lng: -40.628120 },
  "sao gabriel da palha": { lat: -19.018190, lng: -40.536487 },
  "sao jose do calcado": { lat: -21.027442, lng: -41.663627 },
  "sao mateus": { lat: -18.721407, lng: -39.857935 },
  "sao roque do canaa": { lat: -19.741145, lng: -40.652580 },
  "vargem alta": { lat: -20.669019, lng: -41.017922 },
  "venda nova do imigrante": { lat: -20.327017, lng: -41.135545 },
  "viana": { lat: -20.382503, lng: -40.493292 },
  "vila pavao": { lat: -18.609087, lng: -40.608992 },
  "vila valerio": { lat: -18.995766, lng: -40.384913 },
  "vila velha": { lat: -20.341705, lng: -40.287458 },
  "vitoria": { lat: -20.315472, lng: -40.312806 },
};
