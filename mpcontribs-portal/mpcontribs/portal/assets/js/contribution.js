$(document).ready(function () {

    $('h2').addClass('title');

    $('.anchor-link').each(function(index, anchor) {
        var href = $(anchor).attr('href');
        var text = href.substring(1).split('-')[0];
        var a = $('<a/>', {'href': href, 'text': text, 'class': 'button is-white'});
        var item = $('<div/>', {'class': 'level-item', 'html': a});
        $('#anchors').append(item);
        $('#item_' + text).removeClass('is-hidden');
        if (text === 'Tables') { $('#item_Graphs').removeClass('is-hidden'); }
    });

    $('input[name=toggles]').change(function() {
        var name = $(this).attr('id').split('_')[1];
        var toggle = '[name=' + name + ']';
        $(toggle).toggleClass('is-hidden');
    });
    $('#toggle_Code').click();

    if ($('#alert').length) {
        var dots = '<span class="loader__dot">.</span><span class="loader__dot">.</span><span class="loader__dot">.</span>';
        var source = new EventSource(window.api['host'] + 'stream');
        var ncells = $('#notebook').data('ncells');
        source.addEventListener('greeting', function(event) {
            var data = JSON.parse(event.data);
            if (data.message < 0) {
                $('#alert').html('Detail page ready, reloading ' + dots);
                window.location.reload();
            } else {
                $('#alert').html('cell ' + data.message + ' of ' + ncells + ' done ' + dots);
            }
        }, false);
        source.addEventListener('error', function(event) {
            $('#alert').html("Failed to connect to event stream. Is Redis running?")
        }, false);
    }
});
