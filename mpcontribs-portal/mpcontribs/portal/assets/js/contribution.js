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
});
