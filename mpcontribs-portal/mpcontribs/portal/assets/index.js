import 'bootstrap';

function importAll(r) { return r.keys().map(r); }
importAll(require.context('./images/', false, /\.(png|jpe?g|svg)$/));
importAll(require.context('../../../mpcontribs-users/mpcontribs/users/', true, /\.(png|jpe?g|svg)$/));

$(document).ready(function() {
  $('.btn-link').tooltip();
});
