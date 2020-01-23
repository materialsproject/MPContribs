import("css/highlight.css");
import 'toggle';

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

    if ($('#alert').length) { poll(); }

    $('.anchor-link').each(function(index, anchor) {
        var href = $(anchor).attr('href');
        var text = href.substring(1).split('-').slice(0, 2).join(' ');
        $('#anchors').append('<li><a href="'+href+'">'+text+'</a><li>');
    });

    function toggle_divs(name) {
        var divs = document.getElementsByName(name);
        for (var j=0; j<divs.length; j++) {
            if ($(divs[j]).is(":visible")) { $(divs[j]).hide(); }
            else { $(divs[j]).show(); }
        }
    };

    $('#toggle_inputs').change(function () { toggle_divs("Code"); });
    $('#toggle_trees').change(function () { toggle_divs("HData"); });
    $('#toggle_tables').change(function () { toggle_divs("Table"); });
    $('#toggle_graphs').change(function () { toggle_divs("Graph"); });
    $('#toggle_structures').change(function () { toggle_divs("Structure"); });

    var width = 90;

    $('#toggle_inputs').bootstrapToggle({on:"Code", off:"Code", size:"small", width:width});
    $('#toggle_trees').bootstrapToggle({on:"HData", off:"HData", size:"small", width:width});
    $('#toggle_tables').bootstrapToggle({on:"Tables", off:"Tables", size:"small", width:width});
    $('#toggle_graphs').bootstrapToggle({on:"Graphs", off:"Graphs", size:"small", width:width});
    $('#toggle_structures').bootstrapToggle({on:"Structures", off:"Structures", size:"small", width:width});
});
