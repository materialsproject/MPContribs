import 'bootstrap';

function importAll(r) { return r.keys().map(r); }
importAll(require.context('./images/', false, /\.(png|jpe?g|svg)$/));

$(document).ready(function() {
  $('.btn-link').tooltip();
});
