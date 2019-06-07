var prefix = '';
if ( location.pathname.startsWith('/user') ) {
    var user = location.pathname.split('/')[2];
    prefix = '/user/' + user;
}
var mpcontribs = require([prefix + '/custom/js/mpcontribs.var.js']);
