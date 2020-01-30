//import 'toggle';

var dots = '<span class="loader__dot">.</span><span class="loader__dot">.</span><span class="loader__dot">.</span>';

function poll() {
    setTimeout(function() {
        var cid = window.location.pathname.replace('/', '');
        var indexes = $('#notebook').data('indexes');
        var fields = $.map(indexes, function(el) { return 'cells.' + el + '.outputs'; });
        console.log('poll notebook ' + cid);
        $.get({
            url: window.api['host'] + 'notebooks/' + cid + '/',
            headers: window.api['headers'],
            data: {'_fields': fields.join(',')}
        }).done(function(response) {
            var ncells = response['cells'].length;
            var last_completed = -1;
            for (var i = indexes.length-1; i >= 0; i--) {
                var has_outputs = response['cells'][indexes[i]]['outputs'].length;
                if (has_outputs) {
                    last_completed = indexes[i];
                    break;
                }
            }
            console.log('last_completed: ' + last_completed)
            if (last_completed != ncells-1) {
                $('#alert').html('cell #' + last_completed + ' done ' + dots)
                poll();
            } else {
                $('#alert').html('Detail page ready, reloading ' + dots);
                window.location.reload();
            }
        });
    }, 10000);
}

$(document).ready(function () {

    //if ($('#alert').length) { poll(); }

    $('h2').addClass('title');

    $('.anchor-link').each(function(index, anchor) {
        var href = $(anchor).attr('href');
        var text = href.substring(1).split('-')[0];
        var a = $('<a/>', {'href': href, 'text': text, 'class': 'button is-white'});
        var item = $('<div/>', {'class': 'level-item', 'html': a});
        $('#anchors').append(item);
        $('#toggle_' + text).removeClass('is-hidden');
    });

    $('input[name=toggles]').change(function() {
        var toggle = '[name=' + $(this).attr('id').split('_')[1] + ']';
        $(toggle).toggleClass('is-hidden');
    });
});
