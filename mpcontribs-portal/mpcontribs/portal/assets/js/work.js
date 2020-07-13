$(document).ready(function () {
    //var api_key = $('#api_key').val();
    //var nb_url = api_key !== '' ? 'https://jhub.mpcontribs.org' : 'http://localhost:8000';
    //nb_url += '/hub/user-redirect/tree/binder/notebooks/';
    //$('a[name=launch]').each(function() {
    //    $(this).attr('href', nb_url + $(this).attr('id') + '.ipynb');
    //});

    $('a[name=nb_show]').click(function(e) {
        e.preventDefault();
        $('a[name=nb_show]').removeClass('is-active');
        $('#nb_content').load('notebooks/' + $(this).html() + '.html');
        $(this).addClass('is-active');
    });
    $('#get_started').click();
});
