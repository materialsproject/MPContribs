console.log('custom.js ...');
define([
    'base/js/namespace',
    'base/js/promises'
], function(Jupyter, promises) {
    promises.app_initialized.then(function(appname) {
        if (appname === 'NotebookApp') {
            var prefix = '';
            if ( location.pathname.startsWith('/user') ) {
                var user = location.pathname.split('/')[2];
                prefix = '/user/' + user;
            }
            console.log(prefix);
            require([prefix + '/custom/js/mpcontribs.var.js']);
            console.log('MPContribs loaded.')
        }
    });
});
