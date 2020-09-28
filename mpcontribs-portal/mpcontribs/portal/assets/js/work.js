$(document).ready(function () {
    var li = $('#work-toggle').parent();
    li.siblings().removeClass('is-active');
    li.addClass('is-active');

    $('a[name=nb_show]').click(function(e) {
        e.preventDefault();
        $('a[name=nb_show]').removeClass('is-active');
        $('#nb_content').load('notebooks/' + $(this).html() + '.html');
        $(this).addClass('is-active');
    });
    $('#get_started').click();
});
