// Medición de Google Ads (etiqueta AW + conversiones). Se carga en todas las páginas.
// Para activar una conversión, pega su etiqueta (lo que va después de "AW-.../") en CONVERSIONES.
(function(){
  var AW_ID = 'AW-17524585022';
  var CONVERSIONES = {
    cotizacion: 'HA32CO6BjbgbEL7kr6RB', // "Solicitar cotización": formulario enviado (WhatsApp o correo)
    whatsapp:   'D-JvCPGBjbgbEL7kr6RB', // "Contacto": clic en cualquier botón de WhatsApp
    llamada:    'SgacCJGHwYwdEL7kr6RB'  // "Clic en Llamar": clic en "Llamar" (tel:)
  };

  var s = document.createElement('script');
  s.async = true;
  s.src = 'https://www.googletagmanager.com/gtag/js?id=' + AW_ID;
  document.head.appendChild(s);

  window.dataLayer = window.dataLayer || [];
  window.gtag = function(){ dataLayer.push(arguments); };
  gtag('js', new Date());
  gtag('config', AW_ID);

  window.arlConversion = function(tipo){
    var label = CONVERSIONES[tipo];
    if (!label) return;
    gtag('event', 'conversion', { send_to: AW_ID + '/' + label, transport_type: 'beacon' });
  };

  document.addEventListener('click', function(e){
    var a = e.target.closest && e.target.closest('a[href]');
    if (!a) return;
    var href = a.getAttribute('href');
    if (/^https:\/\/(wa\.me|api\.whatsapp\.com)\//.test(href)) arlConversion('whatsapp');
    else if (/^tel:/.test(href)) arlConversion('llamada');
  }, true);
})();
