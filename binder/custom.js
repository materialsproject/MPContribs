define([
    'base/js/namespace',
    'base/js/events'
], function(IPython, events) {
    events.on('app_initialized.NotebookApp', function() {
        if ( location.pathname.indexOf('MPContribs') !== -1 ) {
            var prefix = '';
            if ( location.pathname.startsWith('/user') ) {
                var user = location.pathname.split('/')[2];
                prefix = '/user/' + user;
            }
            var mpcontribs = require([prefix + '/custom/js/mpcontribs.var.js']);
            console.log('MPContribs loaded.')
        }
    });
});
