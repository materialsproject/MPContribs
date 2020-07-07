$(document).ready(function () {

    $('h2').addClass('title');

    $('.anchor-link').each(function(index, anchor) {
        var href = $(anchor).attr('href');
        var text = href.substring(1).split('-')[0];
        var a = $('<a/>', {'href': href, 'text': text, 'class': 'button is-white'});
        var item = $('<div/>', {'class': 'level-item', 'html': a});
        $('#anchors').append(item);
        $('#item_' + text).removeClass('is-hidden');
    });

    if ($('#alert').length) {
        var cid = window.location.pathname.replace('/', '');
        var source = new EventSource(window.api['host'] + 'stream?channel=' + cid);
        var ncells = $('#notebook').data('ncells');
        var pbar = $('<progress/>', {'class': 'progress', 'max': ncells});
        $('#alert').append(pbar);

        source.addEventListener('notebook', function(event) {
            var data = JSON.parse(event.data);
            if (data.message === 0) {
                var dots = '<span class="loader__dot">.</span><span class="loader__dot">.</span><span class="loader__dot">.</span>';
                $('#alert').html('Detail page ready, reloading ' + dots);
                window.location.reload();
            } else if (data.message >= 0) {
                pbar.attr('value', data.message);
            } else {
                $('#alert').html('Something went wrong.');
            }
        }, false);

        source.addEventListener('error', function(event) {
            $('#alert').html("Failed to connect to event stream. Is Redis running?")
        }, false);
    }
});
